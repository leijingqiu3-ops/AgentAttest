from __future__ import annotations

import hashlib
from typing import Any, Callable

from .fixtures import (
    failing_case,
    failing_trace,
    golden_case,
    golden_trace,
    noop_trace,
    phantom_write_trace,
    variant_trace,
)
from .models import Assertion, CaseSpec, ToolCallRecord, Trace
from .oracle import evaluate


Oracle = Callable[[CaseSpec, Trace], list[Assertion]]


def _digest(model: Any) -> str:
    return hashlib.sha256(model.model_dump_json().encode("utf-8")).hexdigest()


def _all_pass(case: CaseSpec, trace: Trace) -> list[Assertion]:
    try:
        return [Assertion(name=item.name, passed=True) for item in evaluate(case, trace)]
    except Exception:
        return [Assertion(name="mutant_pass", passed=True)]


def _run_checks(factory: Callable[[], Oracle]) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}

    # INV-1: a direct call must not change the graded state.
    oracle = factory()
    case, trace = golden_case(), golden_trace()
    before = (_digest(case), _digest(trace))
    oracle(case, trace)
    after = (_digest(case), _digest(trace))
    checks["INV-1_no_side_effect"] = {
        "passed": before == after,
        "detail": "case+trace unchanged after evaluate()",
    }

    # INV-2: two calls on the same input must agree.
    oracle = factory()
    first = [item.model_dump() for item in oracle(golden_case(), golden_trace())]
    second = [item.model_dump() for item in oracle(golden_case(), golden_trace())]
    checks["INV-2_deterministic"] = {
        "passed": first == second,
        "detail": "two evaluations of the same trace agree",
    }

    # INV-3: the verdict must not depend on the order episodes are scored.
    oracle = factory()
    forward = {
        "a": any(not item.passed for item in oracle(golden_case(), golden_trace())),
        "b": any(not item.passed for item in oracle(failing_case(), failing_trace())),
    }
    backward = {
        "b": any(not item.passed for item in oracle(failing_case(), failing_trace())),
        "a": any(not item.passed for item in oracle(golden_case(), golden_trace())),
    }
    checks["INV-3_order_independent"] = {
        "passed": forward == backward,
        "detail": "A→B and B→A produce the same verdict map",
    }

    # INV-4: an oracle exception must propagate and leave the trace untouched.
    oracle = factory()
    bad_case = golden_case()
    bad_case.expected["forbidden_patterns"] = [{"name": "bad_regex", "regex": 123}]
    bad_trace = golden_trace()
    before = _digest(bad_trace)
    raised = False
    try:
        oracle(bad_case, bad_trace)
    except Exception:
        raised = True
    checks["INV-4_exception_propagates"] = {
        "passed": raised and _digest(bad_trace) == before,
        "detail": "invalid oracle input raises and does not mutate the trace",
    }

    # INV-5: after a session-ending read, the terminal state and action list stay put.
    oracle = factory()
    terminal = golden_trace()
    before = (len(terminal.tool_calls), _digest(terminal))
    oracle(golden_case(), terminal)
    checks["INV-5_terminal_state_stable"] = {
        "passed": (len(terminal.tool_calls), _digest(terminal)) == before,
        "detail": "no actions appended and terminal state unchanged",
    }

    # CTL-1: neither "does nothing" nor "claims a write it did not make" may pass.
    oracle = factory()
    noop = oracle(golden_case(), noop_trace())
    oracle = factory()
    phantom = oracle(golden_case(), phantom_write_trace())
    checks["CTL-1_no_write_not_solved"] = {
        "passed": any(not item.passed for item in noop) and any(not item.passed for item in phantom),
        "detail": "no-op and phantom-write traces are not graded as solved",
    }

    # CTL-2: the reference solution must pass.
    oracle = factory()
    golden = oracle(golden_case(), golden_trace())
    checks["CTL-2_reference_solved"] = {
        "passed": all(item.passed for item in golden),
        "detail": "golden trace passes every blocking assertion",
    }

    # CTL-3: an accepted alternative phrasing must still pass.
    oracle = factory()
    variant = oracle(golden_case(), variant_trace())
    checks["CTL-3_alternative_accepted"] = {
        "passed": all(item.passed for item in variant),
        "detail": "reply_contains_any accepts '工单已创建'",
    }
    return checks


def _mutants() -> list[tuple[str, str, Callable[[], Oracle]]]:
    def impure_state() -> Oracle:
        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            result = evaluate(case, trace)
            trace.fault_notes.append("oracle mutated the trace")
            return result

        return oracle

    def impure_actions() -> Oracle:
        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            result = evaluate(case, trace)
            trace.tool_calls.append(
                ToolCallRecord(step=99, name="refund_course", args={"student_id": "S001", "course_id": "C001"})
            )
            return result

        return oracle

    def exception_swallow() -> Oracle:
        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            try:
                return evaluate(case, trace)
            except Exception:
                return _all_pass(case, trace)

        return oracle

    def saturated() -> Oracle:
        return _all_pass

    def state_blind() -> Oracle:
        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            return [item for item in evaluate(case, trace) if not item.name.startswith("final_state:")]

        return oracle

    def order_dependent() -> Oracle:
        state: dict[str, Any] = {"prev": None}

        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            result = evaluate(case, trace)
            previous = state["prev"]
            state["prev"] = result
            return previous if previous is not None else result

        return oracle

    def strict_output() -> Oracle:
        def oracle(case: CaseSpec, trace: Trace) -> list[Assertion]:
            result = evaluate(case, trace)
            for item in result:
                if item.name == "reply_contains_any":
                    item.passed = "已创建工单" in trace.output_text
            return result

        return oracle

    return [
        ("state_mutation", "state mutation never restored", impure_state),
        ("actions_not_restored", "actions appended beyond the terminating one", impure_actions),
        ("exception_leak", "oracle exception swallowed", exception_swallow),
        ("saturated_oracle", "oracle passes everything", saturated),
        ("database_blind", "oracle ignores terminal state", state_blind),
        ("order_dependence", "verdict depends on scoring order", order_dependent),
        ("strict_output_match", "only one exact phrasing accepted", strict_output),
    ]


def run_oracle_integrity() -> dict[str, Any]:
    """Audit the oracle itself: five invariants plus three known-answer controls.

    Method adapted from Chen, *When Agent Evaluation Becomes Unreliable*
    (arXiv:2610.16067): treat the evaluation harness as a system under test and
    inject defects into the oracle. INV-5 is the read-only analogue for an
    oracle that never owns an environment handle.
    """
    baseline = _run_checks(lambda: evaluate)
    mutants = []
    for name, paper_class, factory in _mutants():
        checks = _run_checks(factory)
        failed = [key for key, value in checks.items() if not value["passed"]]
        mutants.append(
            {
                "name": name,
                "paper_class": paper_class,
                "detected": bool(failed),
                "failed_checks": failed,
            }
        )
    checks_passed = sum(1 for item in baseline.values() if item["passed"])
    mutants_detected = sum(1 for item in mutants if item["detected"])
    return {
        "paper": "arXiv:2610.16067 (oracle-integrity auditing)",
        "checks_total": len(baseline),
        "checks_passed": checks_passed,
        "checks": baseline,
        "mutants_total": len(mutants),
        "mutants_detected": mutants_detected,
        "mutants": mutants,
        "passed": checks_passed == len(baseline) and mutants_detected == len(mutants),
        "caveat": "Mutants are author-constructed; detection is a conditional property of this battery, not a rate for unknown defects.",
    }