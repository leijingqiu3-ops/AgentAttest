from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def cohen_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float]:
    valid = [(a, b) for a, b in pairs if a and b]
    if not valid:
        return 0.0, 0.0
    n = len(valid)
    observed = sum(1 for a, b in valid if a == b) / n
    labels = sorted({a for a, _ in valid} | {b for _, b in valid})
    expected = sum(
        (sum(1 for a, _ in valid if a == label) / n) * (sum(1 for _, b in valid if b == label) / n)
        for label in labels
    )
    kappa = 0.0 if expected == 1 else (observed - expected) / (1 - expected)
    return round(observed, 3), round(kappa, 3)


def confusion(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = {}
    for a, b in pairs:
        if not a or not b:
            continue
        table.setdefault(a, Counter())[b] += 1
    return {row: dict(cols) for row, cols in table.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    default_sheet = Path("reports/labeling_sheet_labeled.csv")
    if not default_sheet.exists():
        downloads = Path.home() / "Downloads" / "labeling_sheet_labeled.csv"
        if downloads.exists():
            default_sheet = downloads
    parser.add_argument("--sheet", default=str(default_sheet))
    parser.add_argument("--key", default="reports/labeling_sheet_key.csv")
    args = parser.parse_args()

    with Path(args.sheet).open(encoding="utf-8-sig", newline="") as handle:
        sheet = list(csv.DictReader(handle))
    with Path(args.key).open(encoding="utf-8-sig", newline="") as handle:
        key = {row["item_id"]: row["rule_label"] for row in csv.DictReader(handle)}

    rule = [key[row["item_id"]] for row in sheet]
    human_a = [row.get("human_a", "").strip() for row in sheet]
    human_b = [row.get("human_b", "").strip() for row in sheet]

    for name, pairs in {
        "rule vs human_a": list(zip(rule, human_a)),
        "rule vs human_b": list(zip(rule, human_b)),
        "human_a vs human_b": list(zip(human_a, human_b)),
    }.items():
        if not any(a and b for a, b in pairs):
            print(f"{name}: no paired labels")
            continue
        observed, kappa = cohen_kappa(pairs)
        print(f"{name}: n={sum(1 for a, b in pairs if a and b)} agreement={observed:.3f} kappa={kappa:.3f}")
        print("  confusion:", confusion(pairs))

    labeled = sum(1 for a in human_a if a)
    print(f"human_a coverage: {labeled}/{len(sheet)}")


if __name__ == "__main__":
    main()
