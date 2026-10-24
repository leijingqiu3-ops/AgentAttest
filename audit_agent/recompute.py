from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import get_settings
from .manifest import write_manifest
from .models import Trace, Verdict
from .oracle import evaluate
from .report import render_markdown
from .runner import (
    build_summary,
    build_verdict,
    cost_calibration,
    cost_severity_for,
    load_cases,
)


def recompute(run_dir: str | Path, suite: str | Path) -> dict[str, Any]:
    run_path = Path(run_dir)
    old = json.loads((run_path / "summary.json").read_text(encoding="utf-8"))
    cases = load_cases(suite)
    case_map = {case.id: case for case in cases}
    traces: list[Trace] = []

    for path in sorted((run_path / "traces").glob("*.json")):
        trace = Trace.model_validate_json(path.read_text(encoding="utf-8"))
        traces.append(trace)

    settings = get_settings()
    estimated = sum(trace.cost_cny for trace in traces)
    actual = old.get("overall", {}).get("cost_cny_actual")
    calibration = cost_calibration(estimated, actual)
    severity = cost_severity_for(calibration, settings.cost_enforce)

    verdicts: list[Verdict] = []
    for trace in traces:
        case = case_map[trace.case_id]
        verdict = build_verdict(case, trace, severity)
        trace_path = run_path / "traces" / f"{trace.case_id}__{trace.fault_mode}__r{trace.run_index}.json"
        verdict.trace_path = str(trace_path)
        verdict.trace_sha256 = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        verdicts.append(verdict)

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
        actual_cost_cny=actual,
    )
    (run_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_path / "verdicts.jsonl").write_text(
        "\n".join(verdict.model_dump_json() for verdict in verdicts), encoding="utf-8"
    )
    write_manifest(run_path)
    render_markdown(summary, verdicts, run_path / "report.md")
    return summary