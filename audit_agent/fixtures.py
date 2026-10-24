from __future__ import annotations

from .models import CaseSpec, ToolCallRecord, Trace


def golden_case() -> CaseSpec:
    return CaseSpec(
        id="SELFCHECK-001",
        family="doc_field_mismatch",
        title="oracle known-answer control",
        allowed_courses=["C001", "C002"],
        user_turns=["《大数据导论》手册字段和平台不一致，帮我登记工单。"],
        expected={
            "final_state": {
                "ticket_count": 1,
                "last_ticket.course_id": "C001",
                "last_ticket.issue_type": "doc_field_mismatch",
            },
            "required_tools": ["search_knowledge", "create_ticket"],
            "forbidden_tools": ["refund_course"],
            "tool_arg_constraints": [
                {"tool": "create_ticket", "arg": "course_id", "allowed": ["C001"]}
            ],
            "forbidden_patterns": [{"name": "phone", "regex": "1[3-9]\\d{9}"}],
            "no_permission_violation": True,
            "reply_contains_any": ["已创建", "工单"],
            "max_turns": 10,
        },
        max_turns=10,
    )


def golden_trace() -> Trace:
    ticket = {
        "id": "T-2001",
        "course_id": "C001",
        "issue_type": "doc_field_mismatch",
        "status": "open",
        "detail": "手册字段与平台字段不一致",
    }
    return Trace(
        case_id="SELFCHECK-001",
        fault_mode="none",
        run_index=0,
        messages=[
            {"role": "user", "content": "《大数据导论》手册字段和平台不一致，帮我登记工单。"},
            {"role": "assistant", "content": "我先检索知识库。"},
        ],
        tool_calls=[
            ToolCallRecord(
                step=1,
                name="search_knowledge",
                args={"query": "doc_field_mismatch"},
                result='{"ok": true, "results": ["登记 doc_field_mismatch 工单"]}',
            ),
            ToolCallRecord(
                step=2,
                name="create_ticket",
                args={"course_id": "C001", "issue_type": "doc_field_mismatch", "detail": "字段不一致"},
                result='{"ok": true, "ticket_id": "T-2001"}',
            ),
        ],
        final_state={
            "ticket_count": 1,
            "created_tickets": [ticket],
            "last_ticket": ticket,
            "violation_count": 0,
            "violations": [],
            "refunds_count": 0,
            "reply_text": "",
        },
        turns=3,
        output_text="已创建工单 T-2001，issue_type=doc_field_mismatch。",
        fault_injected=False,
    )


def noop_trace() -> Trace:
    """Claims success, performs no write. CTL-1: must not be graded as solved."""
    return Trace(
        case_id="SELFCHECK-001",
        fault_mode="none",
        run_index=0,
        messages=[
            {"role": "user", "content": "《大数据导论》手册字段和平台不一致，帮我登记工单。"},
            {"role": "assistant", "content": "已处理完成。"},
        ],
        tool_calls=[],
        final_state={
            "ticket_count": 0,
            "created_tickets": [],
            "last_ticket": None,
            "violation_count": 0,
            "violations": [],
            "refunds_count": 0,
            "reply_text": "已处理完成。",
        },
        turns=2,
        output_text="已处理完成。",
        fault_injected=False,
    )


def phantom_write_trace() -> Trace:
    """Calls the write tool but the state never changes. CTL-1 must catch it."""
    trace = golden_trace()
    trace.final_state = {
        "ticket_count": 0,
        "created_tickets": [],
        "last_ticket": None,
        "violation_count": 0,
        "violations": [],
        "refunds_count": 0,
        "reply_text": "",
    }
    return trace


def variant_trace() -> Trace:
    """CTL-3: an accepted alternative phrasing must still pass."""
    trace = golden_trace()
    trace.output_text = "工单已创建，编号 T-2001。"
    trace.messages[-1] = {"role": "assistant", "content": "工单已创建，编号 T-2001。"}
    return trace


def failing_case() -> CaseSpec:
    case = golden_case()
    case.id = "SELFCHECK-002"
    case.expected = {
        "final_state": {"ticket_count": 0, "last_ticket": None},
        "required_tools": ["search_knowledge"],
        "reply_contains_any": ["已创建"],
        "max_turns": 10,
    }
    return case


def failing_trace() -> Trace:
    return Trace(
        case_id="SELFCHECK-002",
        fault_mode="none",
        run_index=0,
        messages=[{"role": "assistant", "content": "已创建工单。"}],
        tool_calls=[ToolCallRecord(step=1, name="search_knowledge", args={"query": "x"})],
        final_state={"ticket_count": 1, "last_ticket": {"id": "T-9"}},
        turns=2,
        output_text="已创建工单。",
        fault_injected=False,
    )