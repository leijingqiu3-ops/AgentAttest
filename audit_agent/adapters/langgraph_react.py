from __future__ import annotations

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..config import Settings
from ..models import CaseSpec, ToolCallRecord, Trace
from ..target.agent import system_prompt
from ..target.state import PlatformState
from ..target.tools import dispatch


def _message_to_dict(message: BaseMessage) -> dict[str, Any]:
    role = {
        "human": "user",
        "ai": "assistant",
        "tool": "tool",
        "system": "system",
    }.get(message.type, message.type)
    content = message.content
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    data: dict[str, Any] = {"role": role, "content": content}
    if role == "assistant" and getattr(message, "tool_calls", None):
        data["tool_calls"] = [
            {
                "id": call.get("id", ""),
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    "arguments": json.dumps(call.get("args", {}), ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    if role == "tool":
        data["tool_call_id"] = getattr(message, "tool_call_id", "")
    return data


class LangGraphReActAgent:
    """A real LangGraph ReAct agent wired to the same 11 platform tools.

    The auditor does not change a single assertion: the only thing that changes
    is who executes the task. Traces are normalized to the project's Trace
    schema, so oracle / classifier / report work unchanged.
    """

    def __init__(self, settings: Settings, model: Any | None = None) -> None:
        self.settings = settings
        self.model = model or ChatOpenAI(
            model=settings.model_agent,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=0.0,
            timeout=settings.timeout_s,
            max_retries=2,
        )

    def _build_tools(self, state: PlatformState, records: list[ToolCallRecord]) -> list[Any]:
        def call(name: str, args: dict[str, Any]) -> str:
            start = time.perf_counter()
            output = dispatch(name, args, state)
            records.append(
                ToolCallRecord(
                    step=len(records) + 1,
                    name=name,
                    args=args,
                    result=output[:3000],
                    ok='"ok": true' in output.lower(),
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )
            )
            return output[:3000]

        @tool
        def search_knowledge(query: str) -> str:
            """检索平台知识库，返回处理规则。"""
            return call("search_knowledge", {"query": query})

        @tool
        def get_course(course_id: str) -> str:
            """根据课程 ID 查询课程标题、教师和字段。"""
            return call("get_course", {"course_id": course_id})

        @tool
        def get_student_record(student_id: str, course_id: str) -> str:
            """查询某学生在某课程的成绩记录。"""
            return call("get_student_record", {"student_id": student_id, "course_id": course_id})

        @tool
        def get_chart_config(course_id: str) -> str:
            """查询某课程的图表配置和类别。"""
            return call("get_chart_config", {"course_id": course_id})

        @tool
        def list_tickets(course_id: str = "", status: str = "") -> str:
            """列出工单，可按课程和状态过滤。"""
            args: dict[str, Any] = {}
            if course_id:
                args["course_id"] = course_id
            if status:
                args["status"] = status
            return call("list_tickets", args)

        @tool
        def get_ticket(ticket_id: str) -> str:
            """按工单号查询工单详情。"""
            return call("get_ticket", {"ticket_id": ticket_id})

        @tool
        def check_policy(topic: str) -> str:
            """查询平台政策，例如“退课”。"""
            return call("check_policy", {"topic": topic})

        @tool
        def create_ticket(course_id: str, issue_type: str, detail: str) -> str:
            """登记新工单。issue_type 必须使用平台枚举值。"""
            return call(
                "create_ticket",
                {"course_id": course_id, "issue_type": issue_type, "detail": detail},
            )

        @tool
        def update_ticket(ticket_id: str, status: str, note: str = "") -> str:
            """更新工单状态，例如 reopened 或 closed。"""
            return call("update_ticket", {"ticket_id": ticket_id, "status": status, "note": note})

        @tool
        def refund_course(student_id: str, course_id: str) -> str:
            """执行退课退款。仅在政策允许时调用。"""
            return call("refund_course", {"student_id": student_id, "course_id": course_id})

        @tool
        def send_reply(text: str) -> str:
            """向用户发送最终答复。"""
            return call("send_reply", {"text": text})

        return [
            search_knowledge,
            get_course,
            get_student_record,
            get_chart_config,
            list_tickets,
            get_ticket,
            check_policy,
            create_ticket,
            update_ticket,
            refund_course,
            send_reply,
        ]

    def run(self, case: CaseSpec, fault_mode: str = "none", run_index: int = 0) -> Trace:
        if fault_mode != "none":
            raise ValueError("LangGraph adapter supports only fault_mode='none'")

        start = time.perf_counter()
        state = PlatformState(case.allowed_courses, case.user_role)
        records: list[ToolCallRecord] = []
        graph = create_react_agent(
            self.model,
            self._build_tools(state, records),
            prompt=system_prompt(case, "none"),
        )
        messages: list[BaseMessage] = []
        prompt_tokens = 0
        completion_tokens = 0
        stop_reason = "completed"

        for user_text in case.user_turns:
            messages.append(HumanMessage(content=user_text))
            try:
                result = graph.invoke(
                    {"messages": messages},
                    config={"recursion_limit": max(8, case.max_turns * 2 + 2)},
                )
                messages = list(result["messages"])
            except Exception as exc:  # noqa: BLE001 - trace the failure, do not crash the suite
                stop_reason = f"error:{type(exc).__name__}: {exc}"
                break

        for message in messages:
            if isinstance(message, AIMessage) and message.usage_metadata:
                prompt_tokens += int(message.usage_metadata.get("input_tokens", 0) or 0)
                completion_tokens += int(message.usage_metadata.get("output_tokens", 0) or 0)

        cost = (
            prompt_tokens / 1_000_000 * self.settings.price_in_cny_per_m
            + completion_tokens / 1_000_000 * self.settings.price_out_cny_per_m
        )
        assistant_text = "\n".join(
            str(message.content)
            for message in messages
            if isinstance(message, AIMessage) and str(message.content).strip()
        )
        snapshot = state.snapshot()

        return Trace(
            case_id=case.id,
            fault_mode=fault_mode,
            run_index=run_index,
            messages=[_message_to_dict(message) for message in messages],
            tool_calls=records,
            final_state=snapshot,
            turns=sum(1 for message in messages if isinstance(message, AIMessage)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_cny=cost,
            latency_ms=int((time.perf_counter() - start) * 1000),
            stopped_reason=stop_reason,
            output_text=assistant_text + "\n" + snapshot.get("reply_text", ""),
            fault_injected=False,
            fault_notes=[],
        )
