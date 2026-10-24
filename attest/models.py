from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass, field
from typing import Any


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass(frozen=True)
class AttestContext:
    """What the checker is allowed to know at call time.

    ``task_arg_constraints`` maps ``"tool.arg"`` to the values allowed for this
    *task* (not just this role). Role scope says "you may touch C001-C005";
    the task contract says "this request is about C001". Only the latter can
    catch a plausible-but-wrong argument. The two are separate facts: a task
    contract must not silently shrink the caller's read scope.
    """

    allowed_courses: tuple[str, ...] = ()
    role: str = "teacher"
    days_since_enrollment: int | None = None
    approval_token: str | None = None
    untrusted_input: str = ""
    task_arg_constraints: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_case(cls, case: Any) -> "AttestContext":
        expected = _get(case, "expected", {}) or {}
        specs = _get(case, "tool_arg_constraints", None)
        if specs is None and isinstance(expected, dict):
            specs = expected.get("tool_arg_constraints", ())
        allowed = {str(item) for item in (_get(case, "allowed_courses", ()) or ())}
        constraints: dict[str, tuple[str, ...]] = {}
        for spec in specs or ():
            values = tuple(str(v) for v in (spec.get("allowed") or ()))
            tool, arg = spec.get("tool"), spec.get("arg")
            if not tool or not arg or not values:
                continue
            constraints[f"{tool}.{arg}"] = values
        return cls(
            allowed_courses=tuple(sorted(allowed)),
            role=str(_get(case, "user_role", "teacher")),
            task_arg_constraints=constraints,
        )

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


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