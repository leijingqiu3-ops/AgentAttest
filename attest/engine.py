from __future__ import annotations

import re
from typing import Any

from .injection import scan_untrusted_input
from .models import AttestContext, Decision, RuleHit
from .policy import (
    ARG_PATTERNS,
    COURSE_SCOPED_TOOLS,
    ISSUE_TYPES,
    REFUND_WINDOW_DAYS,
    REQUIRED_ARGS,
    STATE_CHANGING_TOOLS,
    TICKET_STATUSES,
    TOOL_ALLOWLIST,
)


class AttestEngine:
    """Deterministic pre-flight checks. No model calls, no network."""

    def check(
        self,
        tool: str,
        args: dict[str, Any],
        ctx: AttestContext,
        resource_course: str | None = None,
    ) -> Decision:
        hits: list[RuleHit] = []
        flags = scan_untrusted_input(ctx.untrusted_input)

        def hit(rule_id: str, ok: bool, reason: str) -> None:
            hits.append(RuleHit(rule_id=rule_id, ok=ok, reason=reason))

        hit("tool_allowlist", tool in TOOL_ALLOWLIST, f"tool={tool!r} not in allowlist")
        if tool not in TOOL_ALLOWLIST:
            return Decision(allow=False, rule_hits=hits, injection_flags=flags)

        missing = [name for name in REQUIRED_ARGS.get(tool, ()) if not str(args.get(name, "")).strip()]
        hit("required_args", not missing, f"missing required args: {missing}")

        for name, pattern in ARG_PATTERNS.items():
            value = args.get(name)
            if value is None:
                continue
            hit(
                f"arg_format:{name}",
                bool(re.match(pattern, str(value))),
                f"{name}={value!r} does not match {pattern}",
            )

        if tool == "create_ticket":
            value = str(args.get("issue_type", ""))
            hit("issue_type_enum", value in ISSUE_TYPES, f"issue_type={value!r} not allowed")
        if tool == "update_ticket":
            value = str(args.get("status", ""))
            hit("status_enum", value in TICKET_STATUSES, f"status={value!r} not allowed")

        course_id = args.get("course_id") or resource_course
        if tool in COURSE_SCOPED_TOOLS and course_id and ctx.role != "admin":
            allowed = tuple(ctx.allowed_courses)
            hit(
                "course_scope",
                str(course_id) in allowed,
                f"course_id={course_id!r} outside allowed_courses={list(allowed)}",
            )

        if tool == "refund_course":
            days = ctx.days_since_enrollment
            within_window = days is not None and days <= REFUND_WINDOW_DAYS
            approved = bool(ctx.approval_token)
            if days is None:
                hit("refund_window", approved, "enrollment age unknown; human approval required")
            else:
                hit(
                    "refund_window",
                    within_window or approved,
                    f"days_since_enrollment={days} > {REFUND_WINDOW_DAYS}; human approval required",
                )

        if flags and tool in STATE_CHANGING_TOOLS and not ctx.approval_token:
            hit(
                "untrusted_instruction",
                False,
                f"state-changing call after untrusted instruction: {flags}",
            )

        return Decision(allow=all(item.ok for item in hits), rule_hits=hits, injection_flags=flags)