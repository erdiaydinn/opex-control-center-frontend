import asyncio
from types import SimpleNamespace

import pytest

from app.decision_intelligence import (
    DecisionPacketInput,
    DecisionReadiness,
    build_decision_packet,
)
from app.intelligence_router import (
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.live_company_readiness import (
    DecisionTruthReceipt,
    DecisionTruthStatus,
    _sealed_decision_truth_receipt,
)
from app.mission_execution import (
    MissionExecutionKind,
    MissionExecutionSpec,
    execute_mission_until_blocked,
)
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint
from app.proactive_intelligence import ExecutiveSignal, GovernedActionProposal, build_risk_radar


def _truth(status: DecisionTruthStatus, *, firm: bool) -> DecisionTruthReceipt:
    return _sealed_decision_truth_receipt(
        requirement_id="inventory-live",
        tenant_id="YS_TR",
        status=status,
        source_readiness=(),
        firm_claim_authorized=firm,
        world_snapshot_fingerprint="a" * 64,
        requirement_fingerprint="b" * 64,
    )


def _radar():
    return build_risk_radar(
        [
            ExecutiveSignal(
                signal_id="inventory-risk",
                domain="inventory",
                metric_name="stock_gap",
                location="Fulya",
                deviation_pct=-25.0,
                evidence_confidence=0.92,
                freshness_confidence=0.95,
                financial_materiality=0.80,
                time_to_impact_hours=1.0,
                provenance_refs=("live://inventory",),
            )
        ]
    )


def _task():
    return IntelligenceTask(
        task_id="inventory-live-decision",
        complexity=TaskComplexity.STANDARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
    )


def _reasoning_mission():
    return MissionDefinition(
        mission_id="live-inventory-reasoning",
        objective="Reason only from admitted live inventory truth",
        tenant_id="YS_TR",
        steps=(
            MissionStep(
                step_id="reason",
                description="Assess the live inventory condition",
            ),
        ),
    )


def _truth_bound_spec(*, firm: bool = True):
    return (
        MissionExecutionSpec(
            step_id="reason",
            kind=MissionExecutionKind.REASONING,
            intelligence_task=_task(),
            prompt="Assess the authoritative live inventory state.",
            decision_truth_requirement_id="inventory-live",
            requires_firm_company_truth=firm,
        ),
    )


def test_firm_company_decision_without_live_truth_receipt_is_held_and_actions_are_suppressed():
    packet = build_decision_packet(
        DecisionPacketInput(
            decision_id="inventory-executive-claim",
            risk_radar=_radar(),
            actions=(
                GovernedActionProposal(
                    action_id="prepare-replenishment",
                    description="Prepare a replenishment alternative",
                ),
            ),
            requires_live_company_truth=True,
            requires_firm_company_claim=True,
        )
    )

    assert packet.readiness is DecisionReadiness.HOLD
    assert packet.confidence_cap <= 0.25
    assert packet.safe_prepare_action_ids == ()
    assert packet.firm_company_claim_authorized is False
    assert "live_company_truth_receipt_missing" in packet.blockers
    assert "decision_actions_suppressed_by_live_truth_gate" in packet.warnings


def test_qualified_live_truth_cannot_be_upgraded_into_a_firm_company_claim():
    packet = build_decision_packet(
        DecisionPacketInput(
            decision_id="inventory-qualified",
            risk_radar=_radar(),
            decision_truth=_truth(DecisionTruthStatus.QUALIFIED, firm=False),
            requires_live_company_truth=True,
            requires_firm_company_claim=True,
        )
    )

    assert packet.readiness is DecisionReadiness.HOLD
    assert packet.decision_truth_status is DecisionTruthStatus.QUALIFIED
    assert packet.firm_company_claim_authorized is False
    assert "live_company_truth_qualified" in packet.warnings
    assert "live_company_firm_claim_not_authorized" in packet.blockers


def test_mutated_truth_receipt_is_rejected_by_decision_boundary():
    valid = _truth(DecisionTruthStatus.PROCEED, firm=True)
    tampered = valid.model_copy(
        update={
            "status": DecisionTruthStatus.QUALIFIED,
            "firm_claim_authorized": False,
        }
    )

    # DecisionPacketInput is itself a trusted boundary. Pydantic revalidates the
    # nested receipt and rejects fingerprint tampering before packet synthesis.
    with pytest.raises(ValueError, match="decision_truth_receipt_fingerprint_mismatch"):
        DecisionPacketInput(
            decision_id="inventory-tampered-receipt",
            risk_radar=_radar(),
            decision_truth=tampered,
            requires_live_company_truth=True,
            requires_firm_company_claim=True,
        )


def test_mission_waits_for_required_live_truth_without_consuming_retry_budget():
    definition = _reasoning_mission()

    class NeverCalledGateway:
        async def invoke_primary(self, **kwargs):  # pragma: no cover - safety assertion
            raise AssertionError("gateway_must_not_run_without_live_truth")

    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=definition,
            checkpoint=new_checkpoint(definition),
            specs=_truth_bound_spec(),
            gateway=NeverCalledGateway(),
            reasoning_evidence_writer=lambda receipt: "engine-output://unexpected",
            capability_handlers={},
            decision_truth_receipts={},
        )
    )

    assert summary.transitions_executed == 0
    assert summary.checkpoint.status is MissionStatus.READY
    state = summary.checkpoint.steps[0]
    assert state.attempts == 0
    assert state.evidence_refs == ()
    assert "live_company_truth_receipt_missing:reason" in summary.blockers


def test_mutated_truth_receipt_is_rejected_before_model_or_capability_execution():
    definition = _reasoning_mission()
    valid = _truth(DecisionTruthStatus.PROCEED, firm=True)
    tampered = valid.model_copy(update={"world_snapshot_fingerprint": "c" * 64})

    class NeverCalledGateway:
        async def invoke_primary(self, **kwargs):  # pragma: no cover - safety assertion
            raise AssertionError("gateway_must_not_run_with_invalid_live_truth")

    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=definition,
            checkpoint=new_checkpoint(definition),
            specs=_truth_bound_spec(),
            gateway=NeverCalledGateway(),
            reasoning_evidence_writer=lambda receipt: "engine-output://unexpected",
            capability_handlers={},
            decision_truth_receipts={"inventory-live": tampered},
        )
    )

    assert summary.transitions_executed == 0
    assert summary.checkpoint.steps[0].attempts == 0
    assert "live_company_truth_receipt_invalid:reason" in summary.blockers


def test_proceed_truth_receipt_is_bound_into_reasoning_evidence():
    definition = _reasoning_mission()
    truth = _truth(DecisionTruthStatus.PROCEED, firm=True)

    class LocalGateway:
        async def invoke_primary(self, *, task, prompt):
            assert task.task_id == "inventory-live-decision"
            assert prompt
            return SimpleNamespace(engine_id="local-eay", task_id=task.task_id)

    summary = asyncio.run(
        execute_mission_until_blocked(
            definition=definition,
            checkpoint=new_checkpoint(definition),
            specs=_truth_bound_spec(),
            gateway=LocalGateway(),
            reasoning_evidence_writer=lambda receipt: f"engine-output://{receipt.engine_id}/{receipt.task_id}",
            capability_handlers={},
            decision_truth_receipts={"inventory-live": truth},
        )
    )

    assert summary.checkpoint.status is MissionStatus.COMPLETED
    assert summary.transitions_executed == 1
    evidence_refs = summary.checkpoint.steps[0].evidence_refs
    assert any(
        ref.startswith("live-truth-readiness://YS_TR/inventory-live/proceed/")
        and ref.endswith(truth.receipt_fingerprint)
        for ref in evidence_refs
    )
    assert "engine-output://local-eay/inventory-live-decision" in evidence_refs
