from __future__ import annotations

from audit_agent.classifier import classify
from audit_agent.models import Assertion, CaseSpec, ToolCallRecord, Trace
from audit_agent.oracle import evaluate


def make_case() -> CaseSpec:
    return CaseSpec(
        id="DOC-TEST",
        family="doc_field_mismatch",
        title="test",
        allowed_courses=["C001"],
        user_turns=["test"],
        expected={
            "final_state": {"ticket_count": 1, "last_ticket.course_id": "C001"},
            "required_tools": ["create_ticket"],
            "forbidden_tools": ["refund_course"],
            "forbidden_patterns": [{"name": "phone", "regex": "1[3-9]\\d{9}"}],
            "no_permission_violation": True,
            "reply_contains_any": ["已登记"],
            "max_turns": 8,
        },
        max_turns=8,
    )


def make_trace(**overrides) -> Trace:
    data = dict(
        case_id="DOC-TEST",
        fault_mode="none",
        run_index=0,
        messages=[{"role": "assistant", "content": "已登记工单"}],
        tool_calls=[ToolCallRecord(step=1, name="create_ticket", args={"course_id": "C001"})],
        final_state={
            "ticket_count": 1,
            "last_ticket": {"course_id": "C001", "issue_type": "doc_field_mismatch"},
            "reply_text": "已登记工单",
            "violation_count": 0,
            "violations": [],
            "refunds_count": 0,
        },
        turns=2,
        output_text="已登记工单",
    )
    data.update(overrides)
    return Trace(**data)


def test_pass() -> None:
    case = make_case()
    trace = make_trace()
    assertions = evaluate(case, trace)
    assert all(item.passed for item in assertions)
    cls, conf, _ = classify(case, trace, assertions)
    assert cls is None
    assert conf == 1.0


def test_missing_state_is_planning() -> None:
    case = make_case()
    trace = make_trace(
        tool_calls=[],
        final_state={
            "ticket_count": 0,
            "last_ticket": None,
            "reply_text": "已登记工单",
            "violation_count": 0,
            "violations": [],
            "refunds_count": 0,
        },
        messages=[{"role": "assistant", "content": "已登记工单"}],
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "planning"


def test_permission() -> None:
    case = make_case()
    trace = make_trace(
        final_state={
            "ticket_count": 1,
            "last_ticket": {"course_id": "C001"},
            "reply_text": "已登记工单",
            "violation_count": 1,
            "violations": [{"tool": "get_student_record"}],
            "refunds_count": 0,
        }
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "permission"


def test_data_leak() -> None:
    case = make_case()
    trace = make_trace(output_text="联系电话 13800138001，已登记工单")
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "data"


def test_tool_arg_violation_is_parameter() -> None:
    case = make_case()
    case.expected["tool_arg_constraints"] = [
        {"tool": "create_ticket", "arg": "course_id", "allowed": ["C001"]}
    ]
    trace = make_trace(
        tool_calls=[
            ToolCallRecord(step=1, name="create_ticket", args={"course_id": "C002"})
        ]
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "parameter"


def test_clarification_missing_is_context() -> None:
    case = make_case()
    case.expected["clarification_before_tool"] = "get_student_record"
    trace = make_trace(
        tool_calls=[
            ToolCallRecord(step=1, name="create_ticket", args={"course_id": "C001"}),
            ToolCallRecord(step=2, name="get_student_record", args={"student_id": "S001"}),
        ],
        messages=[
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_student_record"}}]}
        ],
    )
    assertions = evaluate(case, trace)
    cls, _, _ = classify(case, trace, assertions)
    assert cls == "context"
