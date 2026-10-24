from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class HashChainLedger:
    """Append-only JSONL ledger with a hash chain and optional HMAC.

    Honest scope: this is tamper-evident, not a public-key signature. Set
    ATTEST_SECRET to add HMAC-SHA256; without it, an attacker who can rewrite
    the whole file can also recompute the chain.
    """

    def __init__(self, path: str | Path, secret: str | None = None) -> None:
        self.path = Path(path)
        self.secret = secret if secret is not None else os.environ.get("ATTEST_SECRET")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash, self._seq = self._read_tail()

    def _read_tail(self) -> tuple[str, int]:
        if not self.path.exists():
            return "0" * 64, 0
        last = "0" * 64
        count = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                count += 1
                last = json.loads(line).get("hash", last)
        return last, count

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        seq = self._seq
        payload: dict[str, Any] = {
            "seq": seq,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "prev_hash": self._last_hash,
            **event,
        }
        digest = _sha256(self._last_hash + _canonical(payload))
        entry = {**payload, "hash": digest}
        if self.secret:
            entry["hmac"] = hmac.new(
                self.secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(entry) + "\n")
        self._last_hash = digest
        return entry

    def verify(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"ok": True, "entries": 0, "errors": [], "integrity": "empty"}
        errors: list[str] = []
        prev = "0" * 64
        entries = 0
        for line_no, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            entries += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: invalid json ({exc})")
                continue
            stored_hash = entry.pop("hash", None)
            stored_hmac = entry.pop("hmac", None)
            if entry.get("prev_hash") != prev:
                errors.append(f"line {line_no}: prev_hash mismatch")
            expected = _sha256(prev + _canonical(entry))
            if stored_hash != expected:
                errors.append(f"line {line_no}: hash mismatch")
            if self.secret and stored_hmac:
                expected_hmac = hmac.new(
                    self.secret.encode("utf-8"), expected.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(stored_hmac, expected_hmac):
                    errors.append(f"line {line_no}: hmac mismatch")
            prev = stored_hash or expected
        return {
            "ok": not errors,
            "entries": entries,
            "errors": errors,
            "integrity": "hmac_sha256" if self.secret else "hash_chain_only",
        }