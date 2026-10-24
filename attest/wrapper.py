from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from .engine import AttestEngine
from .ledger import HashChainLedger
from .models import AttestContext

PHONE_RE = re.compile(r"1[3-9]\d{9}")
ID_CARD_RE = re.compile(r"\d{17}[\dXx]")


def redact_pii(text: str) -> str:
    text = PHONE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text)
    return ID_CARD_RE.sub(lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:], text)


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
    """Check, execute (or block), redact, and append an evidence entry."""
    decision = engine.check(tool, args, ctx, resource_course=resource_course)
    entry: dict[str, Any] = {
        "tool": tool,
        "args_preview": redact_pii(json.dumps(args, ensure_ascii=False, sort_keys=True))[:500],
        "args_hash": _hash(json.dumps(args, ensure_ascii=False, sort_keys=True)),
        "decision": "allow" if decision.allow else "deny",
        "blocked_by": decision.blocked_by,
        "injection_flags": decision.injection_flags,
    }
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