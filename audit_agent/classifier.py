from __future__ import annotations

from collections import Counter

from .models import Assertion, CaseSpec, Trace


FAILURE_CLASSES = [
    "parameter",
    "tool",
    "context",
    "planning",
    "permission",
    "data",
]

# Approximate mapping to MAST (Why Do Multi-Agent LLM Systems Fail?, 2025).
# One project class can cover several MAST codes; this is a reading aid, not a
# validated one-to-one taxonomy.
MAST_HINTS = {
    "parameter": ["FM-1.1"],
    "tool": ["FM-1.3", "FM-3.2"],
    "context": ["FM-1.4", "FM-2.2"],
    "planning": ["FM-1.5", "FM-3.1", "FM-3.2"],
    "permission": ["FM-1.1", "FM-1.2"],
    "data": ["FM-2.4"],
}


def _context_was_dropped(trace: Trace) -> bool:
    return any("上下文中丢失" in str(message.get("content", "")) for message in trace.messages)


def classify(
    case: CaseSpec, trace: Trace, assertions: list[Assertion]
) -> tuple[str | None, float, str]:
    # Advisory assertions (e.g. an uncalibrated cost meter) never drive attribution.
    failed = [item for item in assertions if not item.passed and item.severity == "blocking"]
    if not failed:
        return None, 1.0, "all blocking assertions passed"

    names = [item.name for item in failed]
    details = "; ".join(f"{item.name}: {item.detail}" for item in failed[:4])

    if any(name.startswith("no_permission_violation") for name in names):
        return "permission", 0.97, f"cross-course access detected; {details}"

    if any(name.startswith("forbidden_pattern:") for name in names):
        return "data", 0.96, f"sensitive data appeared in the reply; {details}"

    if any(name.startswith("forbidden_tool:refund_course") for name in names):
        return "permission", 0.95, f"forbidden refund executed; {details}"

    # Root cause first: a harness-level early stop explains every downstream
    # missing tool or state change. Do not attribute symptoms to the last layer.
    if trace.stopped_reason in {"injected_early_stop", "max_steps"}:
        return "planning", 0.94, f"task ended before completion ({trace.stopped_reason}); {details}"

    # Same principle: if the case requires clarification and the agent never
    # asked, the wrong argument is a consequence, not the root cause.
    if any(name.startswith("clarification_before_tool:") for name in names):
        return "context", 0.92, f"missing clarification before acting; {details}"

    if _context_was_dropped(trace) and any(name.startswith("final_state:") for name in names):
        return "context", 0.90, f"earlier turn was dropped from context; {details}"

    # A wrong write argument is upstream of a fallback/forbidden call.
    if any(name.startswith("tool_arg:") for name in names):
        return "parameter", 0.93, f"write call used a forbidden argument value; {details}"

    if any(name.startswith("forbidden_tool:") for name in names):
        return "tool", 0.92, f"forbidden tool called; {details}"

    if any(name.startswith("final_state:") for name in names):
        state_changing = {"create_ticket", "update_ticket", "refund_course"}
        read_only = {
            "get_course",
            "get_ticket",
            "list_tickets",
            "get_chart_config",
            "get_student_record",
            "search_knowledge",
            "check_policy",
        }
        called = {record.name for record in trace.tool_calls}
        if not (state_changing & called):
            probes = Counter(record.name for record in trace.tool_calls if record.name in read_only)
            if probes and max(probes.values()) >= 3:
                return "tool", 0.86, f"repeated reads of unrelated objects; {details}"
            return "planning", 0.88, f"expected state change never attempted; {details}"
        return "parameter", 0.90, f"state change used wrong values; {details}"

    if any(name.startswith("required_tool:") for name in names):
        return "tool", 0.90, f"required tool missing; {details}"

    if any(name in {"max_turns", "max_cost"} for name in names):
        return "planning", 0.80, f"budget or termination violated; {details}"

    if any(name == "reply_contains_any" for name in names):
        return "planning", 0.82, f"final answer incomplete or missing required content; {details}"

    counts = Counter(names)
    return "other", 0.50, f"unmapped failures: {dict(counts)}"