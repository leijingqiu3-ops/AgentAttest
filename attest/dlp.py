from __future__ import annotations

import re
from dataclasses import dataclass

# Chinese mainland mobile numbers and 18-digit ID cards. Deliberately narrow:
# a wide net would mangle course codes and ticket numbers.
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


@dataclass(frozen=True)
class OutboundScreen:
    text: str
    findings: tuple[str, ...]

    @property
    def leaked(self) -> bool:
        return bool(self.findings)


def redact_pii(text: str) -> str:
    text = PHONE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text)
    return ID_CARD_RE.sub(lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:], text)


def screen_outbound(text: str) -> OutboundScreen:
    """Mask direct identifiers in text that leaves the agent boundary."""
    if not text:
        return OutboundScreen(text=text, findings=())
    findings: list[str] = []
    if PHONE_RE.search(text):
        findings.append("phone")
    if ID_CARD_RE.search(text):
        findings.append("id_card")
    return OutboundScreen(text=redact_pii(text), findings=tuple(findings))