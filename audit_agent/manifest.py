from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_manifest(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {"manifest.json", "report.md", "report.html"}:
            continue
        files[relative] = sha256_file(path)
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "files": files,
        "root": hashlib.sha256(_canonical(files).encode("utf-8")).hexdigest(),
    }


def write_manifest(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    manifest = build_manifest(root)
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def verify_manifest(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    path = root / "manifest.json"
    if not path.exists():
        return {"ok": False, "errors": ["manifest.json missing"], "checked": 0}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked = 0
    for relative, expected in manifest.get("files", {}).items():
        target = root / relative
        if not target.exists():
            errors.append(f"{relative}: missing")
            continue
        checked += 1
        actual = sha256_file(target)
        if actual != expected:
            errors.append(f"{relative}: hash mismatch")
    current = build_manifest(root)
    if current["root"] != manifest.get("root"):
        errors.append("manifest root mismatch (files changed or added)")
    return {
        "ok": not errors,
        "errors": errors,
        "checked": checked,
        "root": manifest.get("root"),
    }