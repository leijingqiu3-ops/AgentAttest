from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AttestContext:
    """What the checker is allowed to know at call time."""

    allowed_courses: tuple[str, ...] = ()
    role: str = "teacher"
    days_since_enrollment: int | None = None
    approval_token: str | None = None
    untrusted_input: str = ""

    @classmethod
    def from_case(cls, case: Any) -> "AttestContext":
        return cls(allowed_courses=tuple(case.allowed_courses), role=case.user_role)


@dataclass
class RuleHit:
    rule_id: str
    ok: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Decision:
    allow: bool
    rule_hits: list[RuleHit] = field(default_factory=list)
    injection_flags: list[str] = field(default_factory=list)

    @property
    def blocked_by(self) -> list[str]:
        return [hit.rule_id for hit in self.rule_hits if not hit.ok]

    @property
    def reasons(self) -> list[str]:
        return [hit.reason for hit in self.rule_hits if not hit.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "blocked_by": self.blocked_by,
            "reasons": self.reasons,
            "injection_flags": self.injection_flags,
            "rule_hits": [hit.to_dict() for hit in self.rule_hits],
        }