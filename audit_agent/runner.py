from __future__ import annotations

import hashlib
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable

from .classifier import classify
from .config import Settings
from .llm import balance_cny
from .manifest import write_manifest
from .models import Assertion, CaseSpec, Trace, Verdict
from .oracle import clarification_observed, evaluate
from .selfcheck import run_selfcheck
from .target.agent import TargetAgent


FAULT_FAMILIES: dict[str, set[str] | None] = {
    "wrong_arg": {"doc_field_mismatch", "missing_grade", "chart_mismatch", "duplicate_ticket", "policy_exception"},
    "skip_clarify": {"missing_grade"},
    "context_drop": {"missing_grade", "context_switch"},
    "policy_ignore": {"permission", "policy_exception"},
    "pii_leak": {"missing_grade"},
    "early_stop": None,
}

# Root cause each injection is designed to introduce. This is the injection
# catalogue's intent, not an independent human label; see the report caveat.
EXPECTED_ROOT_CAUSE = {
    "wrong_arg": "parameter",
    "skip_clarify": "context",
    "context_drop": "context",
    "policy_ignore": "permission",
    "pii_leak": "data",
    "early_stop": "planning",
}

COST_TOLERANCE = (0.75, 1.33)

TRACE_SCHEMA_VERSION = 3


def load_cases(path: str | Path) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(CaseSpec.model_validate_json(line))
    return cases


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return float(ordered[index])


def _rate(values: Iterable[bool]) -> float:
    items = list(values)
    return mean(1.0 if item else 0.0 for item in items) if items else 0.0


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return (round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4))


def _bootstrap_ci(values: list[float], iterations: int = 2000, seed: int = 17) -> tuple[float, float]:
    """Cluster bootstrap: resample cases, not runs. Values are one number per case."""
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (round(values[0], 4), round(values[0], 4))
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(sum(sample) / len(sample))
    estimates.sort()
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return (round(low, 4), round(high, 4))


def _rate_ci(values: list[bool]) -> tuple[float, tuple[float, float]]:
    items = list(values)
    return _rate(items), _wilson(sum(1 for item in items if item), len(items))


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _cases_digest(cases: list[CaseSpec]) -> str:
    payload = "\n".join(case.model_dump_json() for case in cases)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _injected(trace: Trace, case: CaseSpec | None = None) -> bool:
    """Did the configured fault actually take effect?

    This is deliberately evidence-based, not mode-based. A prompt-level
    instruction that the model ignored must not be counted as an injected run.
    """
    if trace.fault_mode == "none":
        return False
    if trace.fault_injected is not None:
        return trace.fault_injected
    if trace.fault_mode == "skip_clarify":
        # If the target still asked before acting, the injection did not land.
        tool = (case.expected.get("clarification_before_tool") if case else None)
        if tool:
            return not clarification_observed(trace, tool)
        return True
    if trace.fault_mode == "early_stop":
        return trace.stopped_reason == "injected_early_stop"
    if trace.fault_mode in ("pii_leak", "policy_ignore"):
        return "（故障注入）" in trace.output_text
    if trace.fault_mode == "context_drop":
        return any("上下文中丢失" in str(message.get("content", "")) for message in trace.messages)
    return True


def cost_calibration(estimated: float | None, actual: float | None) -> dict[str, Any]:
    """Compare token-price estimate with the provider's balance delta.

    If the ratio is outside the tolerance band, the cost meter is not a valid
    pass/fail instrument and budget assertions are downgraded to advisory.
    """
    if not estimated or actual is None:
        return {
            "estimated_cny": round(estimated, 4) if estimated else 0.0,
            "actual_cny": actual,
            "ratio": None,
            "tolerance": list(COST_TOLERANCE),
            "status": "unknown",
        }
    ratio = actual / estimated
    status = "ok" if COST_TOLERANCE[0] <= ratio <= COST_TOLERANCE[1] else "miscalibrated"
    return {
        "estimated_cny": round(estimated, 4),
        "actual_cny": round(actual, 4),
        "ratio": round(ratio, 4),
        "tolerance": list(COST_TOLERANCE),
        "status": status,
    }


def cost_severity_for(calibration: dict[str, Any], policy: str = "auto") -> str:
    if policy == "always":
        return "blocking"
    if policy == "never":
        return "advisory"
    return "blocking" if calibration.get("status") == "ok" else "advisory"


def build_verdict(case: CaseSpec, trace: Trace, cost_severity: str) -> Verdict:
    assertions = evaluate(case, trace, cost_severity=cost_severity)
    if trace.stopped_reason.startswith("error:"):
        assertions.append(
            Assertion(name="runner_error", passed=False, detail=trace.stopped_reason)
        )
    blocking = [item for item in assertions if item.severity == "blocking"]
    failure_class, confidence, rationale = classify(case, trace, assertions)
    return Verdict(
        case_id=case.id,
        fault_mode=trace.fault_mode,
        run_index=trace.run_index,
        passed=all(item.passed for item in blocking),
        assertions=assertions,
        failure_class=failure_class,
        confidence=confidence,
        rationale=rationale,
    )


def _root_cause_consistency(
    verdicts: list[Verdict],
    traces: list[Trace],
    case_map: dict[str, CaseSpec],
    faults: list[str],
) -> dict[str, Any]:
    trace_map = {(trace.case_id, trace.fault_mode, trace.run_index): trace for trace in traces}
    per_mode: dict[str, Any] = {}
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    failed_all: list[Verdict] = []
    for fault in faults:
        expected = EXPECTED_ROOT_CAUSE.get(fault)
        if not expected:
            continue
        applicable = FAULT_FAMILIES.get(fault)
        eligible = [
            verdict
            for verdict in verdicts
            if verdict.fault_mode == fault
            and (
                applicable is None
                or case_map[verdict.case_id].family in applicable
            )
            and _injected(trace_map[(verdict.case_id, verdict.fault_mode, verdict.run_index)], case_map.get(verdict.case_id))
        ]
        failures = [item for item in eligible if not item.passed]
        matches = [item for item in failures if item.failure_class == expected]
        for item in failures:
            confusion[expected][str(item.failure_class)] += 1
        failed_all.extend(failures)
        per_mode[fault] = {
            "expected": expected,
            "injected_runs": len(eligible),
            "failed_runs": len(failures),
            "matches": len(matches),
            "consistency": _rate(item.failure_class == expected for item in failures) if failures else None,
            "consistency_ci": _wilson(len(matches), len(failures)) if failures else None,
            "observed_classes": dict(Counter(item.failure_class for item in failures if item.failure_class)),
        }
    matched_all = [
        item for item in failed_all
        if item.failure_class == EXPECTED_ROOT_CAUSE.get(item.fault_mode)
    ]
    return {
        "overall_consistency": (
            _rate(item.failure_class == EXPECTED_ROOT_CAUSE.get(item.fault_mode) for item in failed_all)
            if failed_all else None
        ),
        "overall_ci": _wilson(len(matched_all), len(failed_all)) if failed_all else None,
        "failures": len(failed_all),
        "matches": len(matched_all),
        "by_mode": per_mode,
        "expected_by_mode": EXPECTED_ROOT_CAUSE,
        "confusion": {key: dict(value) for key, value in confusion.items()},
        "caveat": "Compared with the injection catalogue's intended root cause, not with independent human labels.",
    }

def _assertion_rates(verdicts: list[Verdict]) -> dict[str, Any]:
    blocking = [item for verdict in verdicts for item in verdict.assertions if item.severity == "blocking"]
    advisory = [item for verdict in verdicts for item in verdict.assertions if item.severity != "blocking"]
    by_name: dict[str, list[bool]] = defaultdict(list)
    for item in blocking:
        by_name[item.name.split(":", 1)[0]].append(item.passed)
    return {
        "blocking_total": len(blocking),
        "blocking_passed": sum(1 for item in blocking if item.passed),
        "blocking_pass_rate": _rate(item.passed for item in blocking),
        "advisory_failures": sum(1 for item in advisory if not item.passed),
        "by_kind": {name: {"n": len(values), "pass_rate": _rate(values)} for name, values in sorted(by_name.items())},
    }


def build_summary(
    cases: list[CaseSpec],
    verdicts: list[Verdict],
    traces: list[Trace],
    faults: list[str],
    k: int,
    settings: Settings,
    started_at: str,
    duration_s: float,
    balance_before: float | None,
    balance_after: float | None,
    agent_name: str = "synthetic",
    actual_cost_cny: float | None = None,
) -> dict[str, Any]:
    by_case_fault: dict[tuple[str, str], list[Verdict]] = defaultdict(list)
    for verdict in verdicts:
        by_case_fault[(verdict.case_id, verdict.fault_mode)].append(verdict)

    trace_map = {(trace.case_id, trace.fault_mode, trace.run_index): trace for trace in traces}
    case_map = {case.id: case for case in cases}
    case_results: list[dict[str, Any]] = []
    for (case_id, fault), items in sorted(by_case_fault.items()):
        items = sorted(items, key=lambda item: item.run_index)
        passes = [item.passed for item in items]
        relevant_traces = [
            trace_map[(case_id, fault, item.run_index)]
            for item in items
            if (case_id, fault, item.run_index) in trace_map
        ]
        injected_runs = sum(
            1 for trace in relevant_traces if _injected(trace, case_map.get(case_id))
        )
        case_results.append(
            {
                "case_id": case_id,
                "family": case_map[case_id].family if case_id in case_map else "unknown",
                "fault_mode": fault,
                "runs": len(items),
                "injected_runs": injected_runs,
                "pass_at_1": _rate(passes),
                "pass_at_1_ci": _wilson(sum(1 for item in passes if item), len(passes)),
                "passes": passes,
                "pass_first": passes[0],
                "pass_any": any(passes),
                "pass_all": all(passes),
                "flipped": len(set(passes)) > 1,
                "failure_classes": dict(Counter(item.failure_class for item in items if item.failure_class)),
                "cost_cny": round(
                    sum(
                        trace.cost_cny
                        for trace in traces
                        if trace.case_id == case_id and trace.fault_mode == fault
                    ),
                    4,
                ),
            }
        )

    none_results = [item for item in case_results if item["fault_mode"] == "none"]
    none_pass_rates = [item["pass_at_1"] for item in none_results]
    none_pass_all = [1.0 if item["pass_all"] else 0.0 for item in none_results]
    none_flips = [1.0 if item["flipped"] else 0.0 for item in none_results]
    none_runs = [passed for item in none_results for passed in item["passes"]]
    none_pass_ci = _wilson(sum(1 for item in none_runs if item), len(none_runs))
    none_all_ci = _wilson(sum(1 for item in none_results if item["pass_all"]), len(none_results))
    none_flip_ci = _wilson(sum(1 for item in none_results if item["flipped"]), len(none_results))

    fault_summary: dict[str, Any] = {}
    for fault in faults:
        if fault == "none":
            continue
        applicable = FAULT_FAMILIES.get(fault)
        configured = [verdict for verdict in verdicts if verdict.fault_mode == fault]
        eligible = [
            verdict
            for verdict in configured
            if applicable is None or case_map[verdict.case_id].family in applicable
        ]
        injected = [
            verdict
            for verdict in eligible
            if _injected(trace_map[(verdict.case_id, verdict.fault_mode, verdict.run_index)], case_map.get(verdict.case_id))
        ]
        classes = Counter(item.failure_class for item in injected if item.failure_class)
        per_case_rates = []
        for case_id in {verdict.case_id for verdict in injected}:
            case_items = [verdict for verdict in injected if verdict.case_id == case_id]
            per_case_rates.append(_rate(not item.passed for item in case_items))
        detected = sum(1 for item in injected if not item.passed)
        detection_ci = _wilson(detected, len(injected))
        fault_summary[fault] = {
            "configured_runs": len(configured),
            "runs": len(configured),
            "applicable_runs": len(eligible),
            "injected_runs": len(injected),
            "not_injected_runs": len(eligible) - len(injected),
            "detected": detected,
            "detection_rate": _rate(not item.passed for item in injected),
            "detection_rate_ci": detection_ci,
            "detection_rate_configured": _rate(not item.passed for item in configured),
            "detection_rate_all": _rate(not item.passed for item in configured),
            "failure_classes": dict(classes),
            "top_class": classes.most_common(1)[0][0] if classes else None,
        }

    family_matrix: dict[str, dict[str, float]] = {}
    for case in cases:
        family = case.family
        family_matrix.setdefault(family, {})
        for fault in faults:
            items = [
                verdict
                for verdict in verdicts
                if verdict.case_id == case.id and verdict.fault_mode == fault
            ]
            if not items:
                continue
            if fault != "none":
                items = [
                    item
                    for item in items
                    if _injected(trace_map[(item.case_id, item.fault_mode, item.run_index)], case_map.get(item.case_id))
                ]
                if not items:
                    continue
            detection = _rate(not item.passed for item in items) if fault != "none" else _rate(item.passed for item in items)
            family_matrix[family][fault] = detection

    total_cost = sum(trace.cost_cny for trace in traces)
    none_cost = sum(trace.cost_cny for trace in traces if trace.fault_mode == "none")
    if actual_cost_cny is None and balance_before is not None and balance_after is not None:
        actual_cost_cny = round(balance_before - balance_after, 4)
    calibration = cost_calibration(total_cost, actual_cost_cny)
    severity = cost_severity_for(calibration, settings.cost_enforce)
    calibration["cost_severity"] = severity
    calibration["policy"] = settings.cost_enforce

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "started_at": started_at,
            "duration_s": round(duration_s, 1),
            "agent": agent_name,
            "model": settings.model_agent,
            "judge_model": settings.model_judge,
            "temperature": 0.0,
            "cases": len(cases),
            "faults": faults,
            "k": k,
            "runs": len(verdicts),
            "git_sha": _git_sha(),
            "cases_sha256": _cases_digest(cases),
            "trace_schema": TRACE_SCHEMA_VERSION,
            "oracle_selfcheck": run_selfcheck(),
        },
        "overall": {
            "cost_cny_estimated": round(total_cost, 4),
            "cost_cny_actual": actual_cost_cny,
            "cost_per_run_cny": round(total_cost / len(verdicts), 4) if verdicts else 0.0,
            "cost_per_success_cny": round(
                none_cost / sum(1 for item in none_results if item["pass_all"]), 4
            )
            if none_results and any(item["pass_all"] for item in none_results)
            else None,
            "p95_latency_ms": _p95([trace.latency_ms for trace in traces]),
            "mean_latency_ms": round(mean([trace.latency_ms for trace in traces]), 1) if traces else 0.0,
            "total_prompt_tokens": sum(trace.prompt_tokens for trace in traces),
            "total_completion_tokens": sum(trace.completion_tokens for trace in traces),
        },
        "cost_calibration": calibration,
        "none": {
            "pass_at_1": _rate(none_pass_rates),
            "pass_at_1_ci": none_pass_ci,
            "pass_pow_k": _rate(none_pass_all),
            "pass_pow_k_ci": none_all_ci,
            "false_positive_rate": 1 - _rate(none_pass_rates),
            "flip_rate": _rate(none_flips),
            "flip_rate_ci": none_flip_ci,
            "failed_cases": [item["case_id"] for item in none_results if not item["pass_all"]],
        },
        "faults": fault_summary,
        "root_cause_consistency": _root_cause_consistency(verdicts, traces, case_map, faults),
        "assertions": _assertion_rates(verdicts),
        "by_family": family_matrix,
        "case_results": case_results,
    }


def _write_trace(path: Path, trace: Trace) -> str:
    text = trace.model_dump_json(indent=2)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_suite(
    cases: list[CaseSpec],
    faults: list[str],
    k: int,
    out_dir: str | Path,
    settings: Settings,
    client: Any,
    agent_factory: Callable[[Settings], Any] | None = None,
    agent_name: str = "synthetic",
) -> dict[str, Any]:
    output = Path(out_dir)
    traces_dir = output / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    start = time.perf_counter()
    balance_before = balance_cny(settings)
    agent = agent_factory(settings) if agent_factory else TargetAgent(client, settings)

    pairs: list[tuple[CaseSpec, Trace]] = []
    trace_hashes: dict[tuple[str, str, int], str] = {}
    total = len(cases) * len(faults) * k
    index = 0

    for case in cases:
        for fault in faults:
            for run_index in range(k):
                index += 1
                try:
                    trace = agent.run(case, fault_mode=fault, run_index=run_index)
                except Exception as exc:
                    trace = Trace(
                        case_id=case.id,
                        fault_mode=fault,
                        run_index=run_index,
                        fault_injected=False,
                        stopped_reason=f"error:{type(exc).__name__}: {exc}",
                    )
                digest = _write_trace(traces_dir / f"{case.id}__{fault}__r{run_index}.json", trace)
                trace_hashes[(case.id, fault, run_index)] = digest
                pairs.append((case, trace))
                print(f"[{index}/{total}] {case.id} {fault} r{run_index} -> captured", flush=True)

    balance_after = balance_cny(settings)
    traces = [trace for _, trace in pairs]
    estimated = sum(trace.cost_cny for trace in traces)
    actual = None
    if balance_before is not None and balance_after is not None:
        actual = round(balance_before - balance_after, 4)
    calibration = cost_calibration(estimated, actual)
    severity = cost_severity_for(calibration, settings.cost_enforce)

    verdicts: list[Verdict] = []
    for case, trace in pairs:
        verdict = build_verdict(case, trace, severity)
        verdict.trace_path = str(traces_dir / f"{trace.case_id}__{trace.fault_mode}__r{trace.run_index}.json")
        verdict.trace_sha256 = trace_hashes.get((trace.case_id, trace.fault_mode, trace.run_index), "")
        verdicts.append(verdict)
        status = "PASS" if verdict.passed else f"FAIL:{verdict.failure_class}"
        print(f"  {trace.case_id} {trace.fault_mode} r{trace.run_index} -> {status}", flush=True)

    summary = build_summary(
        cases, verdicts, traces, faults, k, settings,
        started_at, time.perf_counter() - start, balance_before, balance_after, agent_name,
        actual_cost_cny=actual,
    )
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "verdicts.jsonl").write_text(
        "\n".join(verdict.model_dump_json() for verdict in verdicts), encoding="utf-8"
    )
    write_manifest(output)
    return summary