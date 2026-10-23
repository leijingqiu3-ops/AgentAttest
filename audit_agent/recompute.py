from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .classifier import classify
from .config import get_settings
from .models import Assertion, Trace, Verdict
from .oracle import evaluate
from .report import render_markdown
from .runner import build_summary, load_cases


def recompute(run_dir: str | Path, suite: str | Path) -> dict[str, Any]:
    run_path = Path(run_dir)
    old = json.loads((run_path / "summary.json").read_text(encoding="utf-8"))
    cases = load_cases(suite)
    case_map = {case.id: case for case in cases}
    traces: list[Trace] = []
    verdicts: list[Verdict] = []

    for path in sorted((run_path / "traces").glob("*.json")):
        trace = Trace.model_validate_json(path.read_text(encoding="utf-8"))
        case = case_map[trace.case_id]
        assertions = evaluate(case, trace)
        if trace.stopped_reason.startswith("error:"):
            assertions.append(Assertion(name="runner_error", passed=False, detail=trace.stopped_reason))
        failure_class, confidence, rationale = classify(case, trace, assertions)
        verdicts.append(
            Verdict(
                case_id=trace.case_id,
                fault_mode=trace.fault_mode,
                run_index=trace.run_index,
                passed=all(item.passed for item in assertions),
                assertions=assertions,
                failure_class=failure_class,
                confidence=confidence,
                rationale=rationale,
                trace_path=str(path),
            )
        )
        traces.append(trace)

    settings = get_settings()
    summary = build_summary(
        cases,
        verdicts,
        traces,
        old["meta"]["faults"],
        int(old["meta"]["k"]),
        settings,
        old["meta"]["started_at"],
        float(old["meta"].get("duration_s", 0)),
        None,
        None,
        old["meta"].get("agent", "synthetic"),
    )
    old_overall = old.get("overall", {})
    if old_overall.get("cost_cny_actual") is not None:
        summary["overall"]["cost_cny_actual"] = old_overall["cost_cny_actual"]
    (run_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_path / "verdicts.jsonl").write_text(
        "\n".join(verdict.model_dump_json() for verdict in verdicts), encoding="utf-8"
    )
    render_markdown(summary, verdicts, run_path / "report.md")
    return summary
