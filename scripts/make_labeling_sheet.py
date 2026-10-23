from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audit_agent.runner import load_cases  # noqa: E402
CLASSES = ["parameter", "tool", "context", "planning", "permission", "data"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default=str(ROOT / "reports" / "full_matrix"))
    parser.add_argument("--suite", default=str(ROOT / "cases" / "seed_cases.jsonl"))
    parser.add_argument("--out", default=str(ROOT / "reports" / "labeling_sheet.csv"))
    parser.add_argument("--per-class", type=int, default=5)
    args = parser.parse_args()

    run_dir = Path(args.run)
    cases = {case.id: case for case in load_cases(args.suite)}
    verdicts = [
        json.loads(line)
        for line in (run_dir / "verdicts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = [item for item in verdicts if not item["passed"] and item.get("failure_class")]
    by_class: dict[str, list[dict]] = defaultdict(list)
    for item in failures:
        by_class[item["failure_class"]].append(item)

    picked: list[dict] = []
    for name in CLASSES:
        picked.extend(by_class.get(name, [])[: args.per_class])
    if len(picked) < 30:
        chosen = {(item["case_id"], item["fault_mode"], item["run_index"]) for item in picked}
        for item in failures:
            key = (item["case_id"], item["fault_mode"], item["run_index"])
            if key not in chosen:
                picked.append(item)
                chosen.add(key)
            if len(picked) >= 30:
                break
    picked = picked[:30]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    key_path = out.with_name(out.stem + "_key.csv")
    with out.open("w", encoding="utf-8-sig", newline="") as handle, key_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as key_handle:
        writer = csv.writer(handle)
        key_writer = csv.writer(key_handle)
        writer.writerow(
            [
                "item_id",
                "case_id",
                "family",
                "fault_mode",
                "user_request",
                "failed_assertions",
                "trace_excerpt",
                "human_a",
                "human_b",
            ]
        )
        key_writer.writerow(["item_id", "case_id", "fault_mode", "run_index", "rule_label"])
        for index, item in enumerate(picked, 1):
            item_id = f"L{index:03d}"
            case = cases[item["case_id"]]
            failed = [
                f"{assertion['name']}: {assertion.get('detail', '')}"
                for assertion in item["assertions"]
                if not assertion["passed"]
            ]
            trace_path = Path(item["trace_path"])
            trace_excerpt = ""
            if trace_path.exists():
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
                calls = trace.get("tool_calls", [])[-3:]
                trace_excerpt = " ; ".join(
                    f"{call['name']}({json.dumps(call.get('args', {}), ensure_ascii=False)})"
                    for call in calls
                )
            writer.writerow(
                [
                    item_id,
                    item["case_id"],
                    case.family,
                    item["fault_mode"],
                    " | ".join(case.user_turns),
                    " || ".join(failed)[:1200],
                    trace_excerpt[:1200],
                    "",
                    "",
                ]
            )
            key_writer.writerow(
                [item_id, item["case_id"], item["fault_mode"], item["run_index"], item["failure_class"]]
            )

    counts = Counter(item["failure_class"] for item in picked)
    print(f"wrote {len(picked)} items -> {out}")
    print(f"key -> {key_path}")
    print("class distribution:", dict(counts))


if __name__ == "__main__":
    main()
