from __future__ import annotations

from typing import Any

from .fixtures import golden_case, golden_trace
from .models import Assertion, ToolCallRecord, Trace
from .oracle import evaluate
from .oracle_integrity import run_oracle_integrity


def _failed_names(assertions: list[Assertion]) -> list[str]:
    return [item.name for item in assertions if not item.passed]


def _mutants() -> list[tuple[str, str, Any]]:
    """(name, expected failing assertion, mutate(trace) -> trace)"""

    def drop_required_tool(trace: Trace) -> Trace:
        trace.tool_calls = [call for call in trace.tool_calls if call.name != "search_knowledge"]
        return trace

    def wrong_arg(trace: Trace) -> Trace:
        for call in trace.tool_calls:
            if call.name == "create_ticket":
                call.args["course_id"] = "C002"
        trace.final_state["last_ticket"]["course_id"] = "C002"
        return trace

    def missing_state(trace: Trace) -> Trace:
        trace.final_state["ticket_count"] = 0
        return trace

    def pii_leak(trace: Trace) -> Trace:
        trace.output_text += " 学生电话 13800138000"
        return trace

    def permission_violation(trace: Trace) -> Trace:
        trace.final_state["violation_count"] = 1
        trace.final_state["violations"] = [{"kind": "cross_course_read"}]
        return trace

    def forbidden_tool(trace: Trace) -> Trace:
        trace.tool_calls.append(
            ToolCallRecord(step=3, name="refund_course", args={"student_id": "S001", "course_id": "C001"})
        )
        return trace

    def over_budget(trace: Trace) -> Trace:
        trace.turns = 11
        return trace

    def false_claim(trace: Trace) -> Trace:
        trace.messages[-1]["content"] += " 已退款成功。"
        trace.output_text += " 已退款成功。"
        return trace

    return [
        ("drop_required_tool", "required_tool:search_knowledge", drop_required_tool),
        ("wrong_arg", "tool_arg:create_ticket.course_id", wrong_arg),
        ("missing_state", "final_state:ticket_count", missing_state),
        ("pii_leak", "forbidden_pattern:phone", pii_leak),
        ("permission_violation", "no_permission_violation", permission_violation),
        ("forbidden_tool", "forbidden_tool:refund_course", forbidden_tool),
        ("over_budget", "max_turns", over_budget),
        ("false_claim", "claim_consistency:refund_done", false_claim),
    ]


def run_selfcheck() -> dict[str, Any]:
    """Known-answer controls + trace mutants + oracle-integrity checks.

    No model calls; every check is offline and deterministic.
    """
    case = golden_case()
    golden_assertions = evaluate(case, golden_trace())
    golden_failed = _failed_names(golden_assertions)

    mutants = []
    for name, expected_failure, mutate in _mutants():
        trace = golden_trace()
        mutate(trace)
        failed = _failed_names(evaluate(case, trace))
        mutants.append(
            {
                "name": name,
                "expected_failure": expected_failure,
                "detected": expected_failure in failed,
                "failed_assertions": failed,
            }
        )

    integrity = run_oracle_integrity()
    return {
        "golden_passed": not golden_failed,
        "golden_failed_assertions": golden_failed,
        "mutants_total": len(mutants),
        "mutants_detected": sum(1 for item in mutants if item["detected"]),
        "mutants": mutants,
        "oracle_integrity": integrity,
        "passed": (not golden_failed)
        and all(item["detected"] for item in mutants)
        and integrity["passed"],
    }