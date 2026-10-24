from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dlp import screen_outbound
from .engine import AttestEngine
from .models import AttestContext


@dataclass
class TraceReplay:
    case_id: str
    fault_mode: str
    run_index: int
    passed: bool
    calls: int = 0
    first_block: dict[str, Any] | None = None
    outbound: list[str] = field(default_factory=list)
    failure_class: str | None = None

    @property
    def prevented_pre(self) -> bool:
        return self.first_block is not None

    @property
    def prevented_outbound(self) -> bool:
        return self.first_block is None and bool(self.outbound)

    @property
    def prevented(self) -> bool:
        return self.prevented_pre or self.prevented_outbound

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "fault_mode": self.fault_mode,
            "run_index": self.run_index,
            "passed": self.passed,
            "failure_class": self.failure_class,
            "calls": self.calls,
            "first_block": self.first_block,
            "outbound_findings": self.outbound,
            "prevented_pre": self.prevented_pre,
            "prevented_outbound": self.prevented_outbound,
            "prevented": self.prevented,
        }


def _load_cases(suite: Path) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for line in suite.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            cases[case["id"]] = case
    return cases


def replay_run(run_dir: str | Path, suite: str | Path) -> dict[str, Any]:
    """Replay stored tool calls through the attest layer. No model calls.

    This is a counterfactual: we know what the agent called, not what it would
    have done after a denial. A block therefore means "this call never reached
    the tool", not "the task would have succeeded".
    """
    run = Path(run_dir)
    cases = _load_cases(Path(suite))
    engine = AttestEngine()
    verdicts = [
        json.loads(line)
        for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    results: list[TraceReplay] = []
    for verdict in verdicts:
        case_id = verdict["case_id"]
        case = cases.get(case_id)
        if case is None:
            continue
        trace_path = Path(verdict["trace_path"])
        if not trace_path.exists():
            trace_path = run / "traces" / trace_path.name
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        ctx = AttestContext.from_case(case)
        item = TraceReplay(
            case_id=case_id,
            fault_mode=verdict["fault_mode"],
            run_index=verdict["run_index"],
            passed=bool(verdict["passed"]),
            failure_class=verdict.get("failure_class"),
        )
        for call in trace.get("tool_calls") or ():
            item.calls += 1
            decision = engine.check(call["name"], call.get("args") or {}, ctx)
            if not decision.allow and item.first_block is None:
                item.first_block = {
                    "step": call.get("step"),
                    "tool": call["name"],
                    "args": call.get("args") or {},
                    "blocked_by": decision.blocked_by,
                    "reasons": decision.reasons,
                }
        outbound = screen_outbound(trace.get("output_text") or "")
        if outbound.leaked:
            item.outbound = list(outbound.findings)
        results.append(item)

    by_mode: dict[str, Counter[str]] = defaultdict(Counter)
    blocked_by: Counter[str] = Counter()
    prevented_preventable: Counter[str] = Counter()
    false_positives: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []

    for item in results:
        bucket = by_mode[item.fault_mode]
        bucket["runs"] += 1
        if item.passed:
            bucket["passed"] += 1
            if item.prevented:
                false_positives.append(item.to_dict())
            continue
        bucket["failed"] += 1
        if item.prevented_pre:
            bucket["prevented_pre"] += 1
            for rule in (item.first_block or {}).get("blocked_by", ()):
                blocked_by[rule] += 1
        if item.prevented_outbound:
            bucket["prevented_outbound"] += 1
        if item.prevented:
            bucket["prevented"] += 1
        else:
            missed.append(item.to_dict())
            if item.failure_class:
                prevented_preventable[item.failure_class] += 1

    total_failed = sum(b["failed"] for b in by_mode.values())
    total_prevented = sum(b["prevented"] for b in by_mode.values())
    total_prevented_pre = sum(b["prevented_pre"] for b in by_mode.values())
    total_prevented_out = sum(b["prevented_outbound"] for b in by_mode.values())
    total_passed = sum(b["passed"] for b in by_mode.values())

    return {
        "run_dir": str(run).replace("\\", "/"),
        "suite": str(suite).replace("\\", "/"),
        "source": "counterfactual replay of stored tool calls; no model calls",
        "caveat": (
            "A block means the tool call never executed. The agent's behaviour after a "
            "denial is unknown, so this is an upper bound on prevention, not a success rate. "
            "Outbound hits are post-hoc: they only become preventive if replies are routed "
            "through send_reply, which the synthetic target does not always do."
        ),
        "totals": {
            "runs": len(results),
            "passed": total_passed,
            "failed": total_failed,
            "prevented": total_prevented,
            "prevented_pre": total_prevented_pre,
            "prevented_outbound": total_prevented_out,
            "not_prevented": total_failed - total_prevented,
            "prevention_rate": round(total_prevented / total_failed, 4) if total_failed else None,
            "false_positives": len(false_positives),
            "false_positive_rate": (
                round(len(false_positives) / total_passed, 4) if total_passed else None
            ),
        },
        "by_mode": {
            mode: {
                **{k: bucket[k] for k in ("runs", "passed", "failed", "prevented_pre",
                                          "prevented_outbound", "prevented")},
                "not_prevented": bucket["failed"] - bucket["prevented"],
            }
            for mode, bucket in sorted(by_mode.items())
        },
        "blocked_by_rule": dict(blocked_by.most_common()),
        "false_positives": false_positives,
        "not_prevented": missed,
    }


def render_replay_markdown(data: dict[str, Any]) -> str:
    totals = data["totals"]
    lines = [
        "# 在线拦截回放（counterfactual）",
        "",
        f"数据：{data['run_dir']}，共 {totals['runs']} 条 trace。"
        f"失败 {totals['failed']} 条，可拦 {totals['prevented']} 条"
        f"（执行前 {totals['prevented_pre']} + 出口脱敏 {totals['prevented_outbound']}），"
        f"误伤 {totals['false_positives']} 条。",
        "",
        "| 故障模式 | 运行 | 失败 | 执行前拦下 | 出口脱敏 | 仍漏 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, row in data["by_mode"].items():
        lines.append(
            f"| `{mode}` | {row['runs']} | {row['failed']} | {row['prevented_pre']} "
            f"| {row['prevented_outbound']} | {row['not_prevented']} |"
        )
    lines += ["", f"命中规则：{json.dumps(data['blocked_by_rule'], ensure_ascii=False)}", ""]
    lines.append(f"> {data['caveat']}")
    lines.append("")
    return "\n".join(lines)


def write_replay(run_dir: str | Path, suite: str | Path) -> Path:
    data = replay_run(run_dir, suite)
    out = Path(run_dir) / "prevention.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(run_dir) / "prevention.md").write_text(
        render_replay_markdown(data), encoding="utf-8"
    )
    return out