from __future__ import annotations

from audit_agent.classifier import classify
from audit_agent.models import Assertion, CaseSpec, ToolCallRecord, Trace
from audit_agent.oracle import evaluate
from audit_agent.oracle_integrity import run_oracle_integrity
from audit_agent.runner import _injected, build_verdict

from test_oracle import make_case, make_trace


def test_clarification_beats_wrong_argument() -> None:
    case = make_case()
    case.expected["clarification_before_tool"] = "get_student_record"
    case.expected["tool_arg_constraints"] = [
        {"tool": "get_student_record", "arg": "student_id", "allowed": ["S001"]}
    ]
    trace = make_trace(
        tool_calls=[ToolCallRecord(step=1, name="get_student_record", args={"student_id": "S009"})],
        messages=[{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_student_record"}}]}],
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "context"


def test_early_stop_is_planning_not_missing_tool() -> None:
    case = make_case()
    trace = make_trace(
        stopped_reason="injected_early_stop",
        tool_calls=[ToolCallRecord(step=1, name="search_knowledge", args={"query": "x"})],
        final_state={"ticket_count": 0, "last_ticket": None, "violation_count": 0, "violations": [], "reply_text": ""},
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "planning"


def test_wrong_argument_beats_forbidden_fallback() -> None:
    case = make_case()
    case.expected["tool_arg_constraints"] = [
        {"tool": "update_ticket", "arg": "ticket_id", "allowed": ["T-1"]}
    ]
    trace = make_trace(
        tool_calls=[
            ToolCallRecord(step=1, name="update_ticket", args={"ticket_id": "T-2"}),
            ToolCallRecord(step=2, name="create_ticket", args={"course_id": "C001"}),
        ]
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "parameter"


def test_context_drop_is_context() -> None:
    case = make_case()
    trace = make_trace(
        messages=[
            {"role": "user", "content": "（上一条用户消息在上下文中丢失，请基于已有信息继续处理。）"},
            {"role": "assistant", "content": "已处理"},
        ],
        final_state={"ticket_count": 0, "last_ticket": None, "violation_count": 0, "violations": [], "reply_text": ""},
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "context"


def test_advisory_cost_does_not_fail_case() -> None:
    case = make_case()
    case.max_cost_cny = 0.01
    trace = make_trace(cost_cny=0.5)
    assertions = evaluate(case, trace, cost_severity="advisory")
    cost = next(item for item in assertions if item.name == "max_cost")
    assert cost.severity == "advisory"
    assert cost.passed is False
    verdict = build_verdict(case, trace, "advisory")
    assert verdict.passed is True
    assert verdict.failure_class is None


def test_skip_clarify_compliance_is_evidence_based() -> None:
    case = CaseSpec(
        id="CLARIFY-1",
        family="missing_grade",
        title="needs student id",
        allowed_courses=["C001"],
        user_turns=["查一下成绩"],
        expected={"clarification_before_tool": "get_student_record"},
    )
    asked = make_trace(
        case_id="CLARIFY-1",
        messages=[
            {"role": "assistant", "content": "请问学号是多少？"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_student_record"}}]},
        ],
        fault_mode="skip_clarify",
        fault_injected=None,
    )
    guessed = make_trace(
        case_id="CLARIFY-1",
        messages=[{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_student_record"}}]}],
        fault_mode="skip_clarify",
        fault_injected=None,
    )
    assert _injected(asked, case) is False
    assert _injected(guessed, case) is True


def test_oracle_integrity_passes() -> None:
    result = run_oracle_integrity()
    assert result["checks_passed"] == result["checks_total"], result["checks"]
    assert result["mutants_detected"] == result["mutants_total"], result["mutants"]