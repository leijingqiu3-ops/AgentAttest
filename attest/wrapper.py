from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from .dlp import redact_pii, screen_outbound
from .engine import AttestEngine
from .ledger import HashChainLedger
from .models import AttestContext

__all__ = ["guarded_call", "redact_pii"]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def guarded_call(
    engine: AttestEngine,
    ledger: HashChainLedger,
    tool: str,
    args: dict[str, Any],
    ctx: AttestContext,
    execute: Callable[[], str],
    resource_course: str | None = None,
) -> str:
    """Check, execute (or block), redact, and append an evidence entry.

    Outbound replies are screened before they leave: a masked copy is what gets
    sent and what gets hashed, so the ledger never stores the raw identifier.
    """
    dlp: list[str] = []
    if tool == "send_reply" and isinstance(args.get("text"), str):
        screen = screen_outbound(args["text"])
        if screen.leaked:
            args = {**args, "text": screen.text}
            dlp = list(screen.findings)

    decision = engine.check(tool, args, ctx, resource_course=resource_course)
    canonical = json.dumps(args, ensure_ascii=False, sort_keys=True)
    entry: dict[str, Any] = {
        "tool": tool,
        "args_preview": redact_pii(canonical)[:500],
        "args_hash": _hash(canonical),
        "decision": "allow" if decision.allow else "deny",
        "blocked_by": decision.blocked_by,
        "injection_flags": decision.injection_flags,
    }
    if dlp:
        entry["dlp"] = dlp
    if not decision.allow:
        result = json.dumps(
            {
                "ok": False,
                "blocked": True,
                "blocked_by": decision.blocked_by,
                "reasons": decision.reasons,
            },
            ensure_ascii=False,
        )
        entry.update({"result_hash": _hash(result), "result_preview": result[:300]})
        ledger.append(entry)
        return result

    try:
        raw = execute()
    except Exception as exc:  # keep the ledger; surface the failure to the planner
        raw = json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    safe = redact_pii(raw)
    entry.update({"result_hash": _hash(raw), "result_preview": safe[:300]})
    ledger.append(entry)
    return safe