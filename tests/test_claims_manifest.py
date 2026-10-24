from __future__ import annotations

import json

from audit_agent.manifest import verify_manifest, write_manifest
from audit_agent.models import CaseSpec, ToolCallRecord, Trace
from audit_agent.oracle import evaluate


def claim_case(**expected) -> CaseSpec:
    return CaseSpec(
        id="CLAIM-1",
        family="test",
        title="claim consistency",
        user_turns=["x"],
        expected={"verify_claims": True, **expected},
        max_turns=10,
        max_cost_cny=1.0,
    )


def trace(*, text: str, tools: list[str] | None = None, refunds: int = 0, tickets: int = 0) -> Trace:
    return Trace(
        case_id="CLAIM-1",
        fault_mode="none",
        run_index=0,
        messages=[{"role": "assistant", "content": text}],
        tool_calls=[ToolCallRecord(step=i + 1, name=name, args={}) for i, name in enumerate(tools or [])],
        final_state={"refunds_count": refunds, "ticket_count": tickets},
        turns=1,
        output_text=text,
        fault_injected=False,
    )


def test_false_refund_claim_is_detected() -> None:
    assertions = evaluate(claim_case(), trace(text="已退款成功。"))
    failed = [item for item in assertions if not item.passed]
    assert any(item.name == "claim_consistency:refund_done" for item in failed)


def test_claim_with_tool_evidence_passes() -> None:
    assertions = evaluate(
        claim_case(),
        trace(text="已创建工单 T-2001。", tools=["create_ticket"], tickets=1),
    )
    assert not any(item.name.startswith("claim_consistency:") and not item.passed for item in assertions)


def test_negated_claim_is_ignored() -> None:
    assertions = evaluate(claim_case(), trace(text="尚未创建工单，请补充学号。"))
    assert not any(item.name.startswith("claim_consistency:") for item in assertions)


def test_manifest_detects_trace_tampering(tmp_path) -> None:
    run = tmp_path / "run"
    (run / "traces").mkdir(parents=True)
    (run / "summary.json").write_text("{}", encoding="utf-8")
    (run / "verdicts.jsonl").write_text("", encoding="utf-8")
    trace_path = run / "traces" / "a.json"
    trace_path.write_text(json.dumps({"case_id": "A"}), encoding="utf-8")

    manifest = write_manifest(run)
    assert manifest["root"]
    assert verify_manifest(run)["ok"]

    trace_path.write_text(json.dumps({"case_id": "B"}), encoding="utf-8")
    result = verify_manifest(run)
    assert not result["ok"]
    assert any("hash mismatch" in item for item in result["errors"])