from __future__ import annotations

TOOL_ALLOWLIST: set[str] = {
    "search_knowledge",
    "get_course",
    "get_student_record",
    "get_chart_config",
    "list_tickets",
    "check_policy",
    "get_ticket",
    "create_ticket",
    "update_ticket",
    "refund_course",
    "send_reply",
}

STATE_CHANGING_TOOLS: set[str] = {"create_ticket", "update_ticket", "refund_course"}

# Tools whose call must stay inside the caller's allowed course set.
COURSE_SCOPED_TOOLS: set[str] = {
    "get_student_record",
    "get_chart_config",
    "list_tickets",
    "create_ticket",
    "refund_course",
}

REQUIRED_ARGS: dict[str, tuple[str, ...]] = {
    "search_knowledge": ("query",),
    "get_course": ("course_id",),
    "get_student_record": ("student_id", "course_id"),
    "get_chart_config": ("course_id",),
    "check_policy": ("topic",),
    "get_ticket": ("ticket_id",),
    "create_ticket": ("course_id", "issue_type", "detail"),
    "update_ticket": ("ticket_id", "status"),
    "refund_course": ("student_id", "course_id"),
    "send_reply": ("text",),
}

ARG_PATTERNS: dict[str, str] = {
    "course_id": r"^C\d{3}$",
    "student_id": r"^S\d{3}$",
    "ticket_id": r"^T-\d{4}$",
}

# Mirrors audit_agent.target.tools.ISSUE_TYPES; a test keeps them in sync.
ISSUE_TYPES: tuple[str, ...] = (
    "doc_field_mismatch",
    "missing_grade",
    "chart_mismatch",
    "env_dependency",
    "policy_exception",
    "duplicate_ticket",
    "data_quality",
    "other",
)

TICKET_STATUSES: tuple[str, ...] = ("open", "reopened", "closed")
REFUND_WINDOW_DAYS = 7