from __future__ import annotations

import re
from typing import Any

from .models import Assertion, CaseSpec, Trace

# Completion claims that can be checked against the trace. Deliberately narrow:
# we only assert on claims with a concrete state-changing counterpart.
CLAIM_PATTERNS: dict[str, str] = {
    "ticket_created": r"(已|成功)(创建|登记|提交).{0,8}工单|工单.{0,8}(已|成功)(创建|登记)",
    "refund_done": r"(已|成功)(退款|退课)|退款成功|退课成功",
    "ticket_reopened": r"(已|成功)(重开|更新).{0,6}工单|工单.{0,6}(已|成功)(重开|更新)",
}
NEGATION_RE = re.compile(r"(未|没有|无法|不能|并未|不予|尚未)")


def resolve_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _asked_before_tool(trace: Trace, tool_name: str) -> tuple[bool, int | None]:
    """Did the assistant ask for missing information before calling tool_name?

    Returns (asked, index of the assistant message that asked).
    Only messages that precede the first matching tool call are considered.
    """
    asked = False
    asked_index: int | None = None
    for index, message in enumerate(trace.messages):
        if message.get("role") != "assistant":
            continue
        text = str(message.get("content") or "")
        if any(marker in text for marker in ("？", "?", "请提供", "请问", "学号")):
            asked = True
            asked_index = index
        for call in message.get("tool_calls", []) or []:
            if call.get("function", {}).get("name") == tool_name:
                return asked, asked_index
    return False, None


def clarification_observed(trace: Trace, tool_name: str) -> bool:
    """Public helper used by the runner to check prompt-level injection compliance."""
    asked, _ = _asked_before_tool(trace, tool_name)
    return asked


def _last_step_for(trace: Trace, tool_name: str) -> int | None:
    steps = [record.step for record in trace.tool_calls if record.name == tool_name]
    return steps[-1] if steps else None


def _first_step_for(trace: Trace, tool_name: str, arg: str, value: Any) -> int | None:
    for record in trace.tool_calls:
        if record.name == tool_name and str(record.args.get(arg)) == str(value):
            return record.step
    return None


def _message_index_for_text(trace: Trace, text: str) -> int | None:
    for index in range(len(trace.messages) - 1, -1, -1):
        message = trace.messages[index]
        if message.get("role") == "assistant" and text and text in str(message.get("content") or ""):
            return index
    return None


def _message_index_for_regex(trace: Trace, regex: str) -> int | None:
    if not regex:
        return None
    pattern = re.compile(regex)
    for index, message in enumerate(trace.messages):
        if message.get("role") != "assistant":
            continue
        if pattern.search(str(message.get("content") or "")):
            return index
    return None


def _last_assistant_text(trace: Trace) -> str:
    for index in range(len(trace.messages) - 1, -1, -1):
        message = trace.messages[index]
        if message.get("role") == "assistant" and str(message.get("content") or "").strip():
            return str(message.get("content"))
    return ""


def _claim_evidence(trace: Trace, kind: str) -> bool:
    names = [record.name for record in trace.tool_calls]
    state = trace.final_state
    if kind == "ticket_created":
        return "create_ticket" in names or int(state.get("ticket_count", 0) or 0) > 0
    if kind == "refund_done":
        return "refund_course" in names or int(state.get("refunds_count", 0) or 0) > 0
    if kind == "ticket_reopened":
        if any(
            record.name == "update_ticket"
            and str(record.args.get("status", "")) == "reopened"
            for record in trace.tool_calls
        ):
            return True
        return (state.get("last_updated") or {}).get("status") == "reopened"
    return True


def _claims(trace: Trace) -> list[tuple[str, str, bool]]:
    """One entry per claim kind found: (kind, matched phrase, supported)."""
    text = _last_assistant_text(trace)
    found: dict[str, tuple[str, bool]] = {}
    for kind, pattern in CLAIM_PATTERNS.items():
        for match in re.finditer(pattern, text):
            if NEGATION_RE.search(text[max(0, match.start() - 8) : match.start()]):
                continue
            supported = _claim_evidence(trace, kind)
            previous = found.get(kind)
            if previous is None or (previous[1] and not supported):
                found[kind] = (match.group(0), supported)
    return [(kind, phrase, supported) for kind, (phrase, supported) in found.items()]


def evaluate(
    case: CaseSpec,
    trace: Trace,
    *,
    cost_severity: str = "blocking",
) -> list[Assertion]:
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
                evidence_step=_first_step_for(trace, tool, arg, bad[0]) if bad else None,
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
                message_index=_message_index_for_regex(trace, regex),
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
        asked, asked_index = _asked_before_tool(trace, clarify_tool)
        assertions.append(
            Assertion(
                name=f"clarification_before_tool:{clarify_tool}",
                passed=asked,
                detail="assistant must ask for the missing identifier before calling the tool",
                evidence_step=_last_step_for(trace, clarify_tool),
                message_index=asked_index,
            )
        )

    reply_any = expected.get("reply_contains_any") or []
    if reply_any:
        text = trace.output_text
        hits = [item for item in reply_any if item in text]
        last_index = next(
            (
                index
                for index in range(len(trace.messages) - 1, -1, -1)
                if trace.messages[index].get("role") == "assistant"
                and str(trace.messages[index].get("content") or "")
            ),
            None,
        )
        assertions.append(
            Assertion(
                name="reply_contains_any",
                passed=bool(hits),
                detail=f"expected_any={reply_any}, hits={hits}",
                message_index=last_index,
            )
        )

    if expected.get("verify_claims", True):
        for kind, phrase, supported in _claims(trace):
            detail = (
                f"reply claims {phrase!r} and the trace has matching evidence"
                if supported
                else f"reply claims {phrase!r} but no matching tool call or state change"
            )
            assertions.append(
                Assertion(
                    name=f"claim_consistency:{kind}",
                    passed=supported,
                    detail=detail,
                    message_index=_message_index_for_text(trace, phrase),
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
            severity="blocking" if cost_severity == "blocking" else "advisory",
        )
    )
    return assertions