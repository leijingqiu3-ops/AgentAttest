from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    step: int
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    ok: bool = True
    latency_ms: int = 0


class Trace(BaseModel):
    case_id: str
    fault_mode: str
    run_index: int
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cny: float = 0.0
    latency_ms: int = 0
    stopped_reason: str = ""
    output_text: str = ""
    fault_injected: bool | None = None
    fault_notes: list[str] = Field(default_factory=list)


class Assertion(BaseModel):
    name: str
    passed: bool
    detail: str = ""
    evidence_step: int | None = None


class Verdict(BaseModel):
    case_id: str
    fault_mode: str
    run_index: int
    passed: bool
    assertions: list[Assertion] = Field(default_factory=list)
    failure_class: str | None = None
    confidence: float = 1.0
    rationale: str = ""
    trace_path: str = ""


class CaseSpec(BaseModel):
    id: str
    family: str
    title: str
    user_role: str = "teacher"
    allowed_courses: list[str] = Field(default_factory=list)
    user_turns: list[str] = Field(default_factory=list)
    expected: dict[str, Any] = Field(default_factory=dict)
    max_turns: int = 10
    max_cost_cny: float = 0.10
    tags: list[str] = Field(default_factory=list)
    source: str = "synthetic"
