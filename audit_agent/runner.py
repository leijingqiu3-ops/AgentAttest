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
from .models import CaseSpec, Trace, Verdict
from .oracle import evaluate
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

TRACE_SCHEMA_VERSION = 2


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


def _injected(trace: Trace) -> bool:
    """是否真的触发了故障注入。None 表示为旧 trace，按可推断的规则回退。"""
    if trace.fault_mode == "none":
        return False
    if trace.fault_injected is not None:
        return trace.fault_injected
    if trace.fault_mode == "skip_clarify":
        return True
    if trace.fault_mode == "early_stop":
        return trace.stopped_reason == "injected_early_stop"
    if trace.fault_mode in ("pii_leak", "policy_ignore"):
        return "（故障注入）" in trace.output_text
    if trace.fault_mode == "context_drop":
        return any("上下文中丢失" in str(message.get("content", "")) for message in trace.messages)
    return True


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
        injected_runs = sum(1 for trace in relevant_traces if _injected(trace))
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
            if _injected(trace_map[(verdict.case_id, verdict.fault_mode, verdict.run_index)])
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
                    if _injected(trace_map[(item.case_id, item.fault_mode, item.run_index)])
                ]
                if not items:
                    continue
            detection = _rate(not item.passed for item in items) if fault != "none" else _rate(item.passed for item in items)
            family_matrix[family][fault] = detection

    total_cost = sum(trace.cost_cny for trace in traces)
    none_cost = sum(trace.cost_cny for trace in traces if trace.fault_mode == "none")
    actual_cost = None
    if balance_before is not None and balance_after is not None:
        actual_cost = round(balance_before - balance_after, 4)

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
            "cost_cny_actual": actual_cost,
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
        "by_family": family_matrix,
        "case_results": case_results,
    }


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

    verdicts: list[Verdict] = []
    traces: list[Trace] = []
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
                assertions = evaluate(case, trace)
                if trace.stopped_reason.startswith("error:"):
                    from .models import Assertion

                    assertions.append(
                        Assertion(name="runner_error", passed=False, detail=trace.stopped_reason)
                    )
                failure_class, confidence, rationale = classify(case, trace, assertions)
                verdict = Verdict(
                    case_id=case.id,
                    fault_mode=fault,
                    run_index=run_index,
                    passed=all(item.passed for item in assertions),
                    assertions=assertions,
                    failure_class=failure_class,
                    confidence=confidence,
                    rationale=rationale,
                )
                trace_path = traces_dir / f"{case.id}__{fault}__r{run_index}.json"
                trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
                verdict.trace_path = str(trace_path)
                verdicts.append(verdict)
                traces.append(trace)
                status = "PASS" if verdict.passed else f"FAIL:{failure_class}"
                print(f"[{index}/{total}] {case.id} {fault} r{run_index} -> {status}", flush=True)

    balance_after = balance_cny(settings)
    summary = build_summary(
        cases, verdicts, traces, faults, k, settings,
        started_at, time.perf_counter() - start, balance_before, balance_after, agent_name,
    )
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "verdicts.jsonl").write_text(
        "\n".join(verdict.model_dump_json() for verdict in verdicts), encoding="utf-8"
    )
    return summary
