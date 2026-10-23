from __future__ import annotations

import re
from typing import Any

from .models import Assertion, CaseSpec, Trace


def resolve_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _asked_before_tool(trace: Trace, tool_name: str) -> bool:
    asked = False
    for message in trace.messages:
        if message.get("role") != "assistant":
            continue
        text = str(message.get("content") or "")
        if any(marker in text for marker in ("？", "?", "请提供", "请问", "学号")):
            asked = True
        for call in message.get("tool_calls", []) or []:
            if call.get("function", {}).get("name") == tool_name:
                return asked
    return False


def _last_step_for(trace: Trace, tool_name: str) -> int | None:
    steps = [record.step for record in trace.tool_calls if record.name == tool_name]
    return steps[-1] if steps else None


def evaluate(case: CaseSpec, trace: Trace) -> list[Assertion]:
    expected = case.expected
    state = trace.final_state
    assertions: list[Assertion] = []

    for path, want in (expected.get("final_state") or {}).items():
        got = resolve_path(state, path)
        assertions.append(
            Assertion(
                name=f"final_state:{path}",
                passed=got == want,
                detail=f"expected={want!r}, got={got!r}",
                evidence_step=_last_step_for(trace, "create_ticket")
                or _last_step_for(trace, "update_ticket")
                or _last_step_for(trace, "refund_course"),
            )
        )

    tool_names = [record.name for record in trace.tool_calls]
    for name in expected.get("required_tools") or []:
        assertions.append(
            Assertion(
                name=f"required_tool:{name}",
                passed=name in tool_names,
                detail=f"called={tool_names}",
                evidence_step=_last_step_for(trace, name),
            )
        )
    for name in expected.get("forbidden_tools") or []:
        assertions.append(
            Assertion(
                name=f"forbidden_tool:{name}",
                passed=name not in tool_names,
                detail=f"called={tool_names}",
                evidence_step=_last_step_for(trace, name),
            )
        )

    for item in expected.get("tool_arg_constraints") or []:
        tool = item.get("tool", "")
        arg = item.get("arg", "")
        allowed = {str(value) for value in item.get("allowed", [])}
        bad = [
            record.args.get(arg)
            for record in trace.tool_calls
            if record.name == tool and arg in record.args and str(record.args.get(arg)) not in allowed
        ]
        assertions.append(
            Assertion(
                name=f"tool_arg:{tool}.{arg}",
                passed=not bad,
                detail=f"allowed={sorted(allowed)}, bad_values={bad}",
            )
        )

    for item in expected.get("forbidden_patterns") or []:
        name = item.get("name", "pattern")
        regex = item.get("regex", "")
        matched = re.search(regex, trace.output_text) if regex else None
        assertions.append(
            Assertion(
                name=f"forbidden_pattern:{name}",
                passed=matched is None,
                detail=f"regex={regex!r}, match={matched.group(0) if matched else None}",
            )
        )

    if expected.get("no_permission_violation"):
        count = int(state.get("violation_count", 0))
        assertions.append(
            Assertion(
                name="no_permission_violation",
                passed=count == 0,
                detail=f"violations={state.get('violations', [])}",
            )
        )

    clarify_tool = expected.get("clarification_before_tool")
    if clarify_tool:
        assertions.append(
            Assertion(
                name=f"clarification_before_tool:{clarify_tool}",
                passed=_asked_before_tool(trace, clarify_tool),
                detail="assistant must ask for the missing identifier before calling the tool",
                evidence_step=_last_step_for(trace, clarify_tool),
            )
        )

    reply_any = expected.get("reply_contains_any") or []
    if reply_any:
        text = trace.output_text
        hits = [item for item in reply_any if item in text]
        assertions.append(
            Assertion(
                name="reply_contains_any",
                passed=bool(hits),
                detail=f"expected_any={reply_any}, hits={hits}",
            )
        )

    max_turns = int(expected.get("max_turns", case.max_turns))
    assertions.append(
        Assertion(
            name="max_turns",
            passed=trace.turns <= max_turns,
            detail=f"turns={trace.turns}, max={max_turns}",
        )
    )

    max_cost = float(expected.get("max_cost_cny", case.max_cost_cny))
    assertions.append(
        Assertion(
            name="max_cost",
            passed=trace.cost_cny <= max_cost,
            detail=f"cost_cny={trace.cost_cny:.4f}, max={max_cost:.4f}",
        )
    )
    return assertions
