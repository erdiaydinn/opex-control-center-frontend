from __future__ import annotations

import pytest

from app.company_reasoning_runtime import (
    COMPANY_REASONING_RUNTIME_CONTRACT,
    CompanyReasoningExecution,
    _fingerprint as company_reasoning_fingerprint,
)
from app.decision_intelligence import (
    DecisionPacketInput,
    DecisionReadiness,
)
from app.intelligence_supremacy import ReasoningMode
from app.live_company_readiness import (
    DecisionTruthStatus,
    _sealed_decision_truth_receipt,
)
from app.proactive_intelligence import (
    ExecutiveSignal,
    GovernedActionProposal,
    build_risk_radar,
)
from app.situation_company_reasoning import (
    SITUATION_COMPANY_REASONING_CONTRACT,
    SituationCompanyReasoningExecution,
    _fingerprint as situation_reasoning_fingerprint,
)
from app.situation_reasoned_decision import (
    build_situation_reasoned_decision,
    situation_decision_id,
    situation_reasoning_evidence_ref,
)
from app.strong_reasoning_runtime import (
    StrongReasoningExecution,
    StrongReasoningStatus,
)


TENANT = "YS_TR"
COMPANY = "company://yemeksepeti"
SITUATION_FP = "b" * 64
BINDING_FP = "c" * 64
TASK_ID = f"situation-reasoning://{TENANT}/fixture"
SIGNAL_ID = "signal://fulya/ops-risk"


def _reasoning() -> SituationCompanyReasoningExecution:
    strong = StrongReasoningExecution(
        task_id=TASK_ID,
        status=StrongReasoningStatus.LOCAL_RESULT,
        plan_mode=ReasoningMode.LOCAL_SINGLE,
        engine_evidence=(),
    )
    company_draft = {
        "contract": COMPANY_REASONING_RUNTIME_CONTRACT,
        "task_id": TASK_ID,
        "tenant_id": TENANT,
        "company_id": COMPANY,
        "profile_revision": "v1",
        "company_identity_fingerprint": "d" * 64,
        "company_context_snapshot_fingerprint": "e" * 64,
        "company_runtime_binding_fingerprint": BINDING_FP,
        "reasoning_execution": strong.model_dump(mode="json"),
        "cross_company_fallback_allowed": False,
        "firm_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    company = CompanyReasoningExecution.model_validate(
        {
            **company_draft,
            "fingerprint": company_reasoning_fingerprint(company_draft),
        }
    )
    situation_draft = {
        "contract": SITUATION_COMPANY_REASONING_CONTRACT,
        "tenant_id": TENANT,
        "company_id": COMPANY,
        "situation_fingerprint": SITUATION_FP,
        "situation_id": "situation://fixture/fulya",
        "objective_ref": "objective://situation/fulya",
        "rule_ref": "situation-rule://orders-weather-otp/v1",
        "task_id": TASK_ID,
        "company_runtime_binding_fingerprint": BINDING_FP,
        "reasoning": company.model_dump(mode="json"),
        "causal_claim_proven": False,
        "firm_truth_authority_granted": False,
        "replanning_authority_granted": False,
        "execution_authority_granted": False,
    }
    return SituationCompanyReasoningExecution.model_validate(
        {
            **situation_draft,
            "fingerprint": situation_reasoning_fingerprint(situation_draft),
        }
    )


def _truth(*, tenant: str = TENANT):
    return _sealed_decision_truth_receipt(
        requirement_id="fulya-situation-live-truth",
        tenant_id=tenant,
        status=DecisionTruthStatus.PROCEED,
        source_readiness=(),
        firm_claim_authorized=True,
        world_snapshot_fingerprint="f" * 64,
        requirement_fingerprint="1" * 64,
    )


def _radar(
    reasoning: SituationCompanyReasoningExecution,
    *,
    include_reasoning_provenance: bool = True,
    add_second_attention_signal: bool = False,
):
    reasoning_ref = situation_reasoning_evidence_ref(reasoning)
    refs = (
        (reasoning_ref, "live://company/fulya/orders")
        if include_reasoning_provenance
        else ("live://company/fulya/orders",)
    )
    signals = [
        ExecutiveSignal(
            signal_id=SIGNAL_ID,
            domain="operations",
            metric_name="situation_risk",
            location="Fulya",
            deviation_pct=-50.0,
            evidence_confidence=1.0,
            freshness_confidence=1.0,
            financial_materiality=1.0,
            time_to_impact_hours=0.0,
            provenance_refs=refs,
        )
    ]
    if add_second_attention_signal:
        signals.append(
            ExecutiveSignal(
                signal_id="signal://fulya/inventory-risk",
                domain="inventory",
                metric_name="stock_gap",
                location="Fulya",
                deviation_pct=-50.0,
                evidence_confidence=1.0,
                freshness_confidence=1.0,
                financial_materiality=1.0,
                time_to_impact_hours=0.0,
                provenance_refs=(reasoning_ref,),
            )
        )
    return build_risk_radar(signals)


def _payload(
    reasoning: SituationCompanyReasoningExecution,
    *,
    truth=True,
    include_reasoning_provenance: bool = True,
    add_second_attention_signal: bool = False,
    decision_id: str | None = None,
):
    bound = (SIGNAL_ID,)
    return DecisionPacketInput(
        decision_id=(
            decision_id
            or situation_decision_id(
                reasoning=reasoning,
                bound_signal_ids=bound,
            )
        ),
        risk_radar=_radar(
            reasoning,
            include_reasoning_provenance=include_reasoning_provenance,
            add_second_attention_signal=add_second_attention_signal,
        ),
        actions=(
            GovernedActionProposal(
                action_id="prepare-capacity-option",
                description="Prepare a reversible capacity option for review.",
            ),
        ),
        decision_truth=_truth() if truth else None,
        requires_live_company_truth=True,
        requires_firm_company_claim=True,
    )


def test_exact_situation_reasoning_and_live_truth_are_bound_into_decision_without_execution():
    reasoning = _reasoning()
    result = build_situation_reasoned_decision(
        reasoning=reasoning,
        payload=_payload(reasoning),
        bound_signal_ids=(SIGNAL_ID,),
    )

    assert result.reasoning_fingerprint == reasoning.fingerprint
    assert result.reasoning_evidence_ref == situation_reasoning_evidence_ref(reasoning)
    assert result.truth_receipt_fingerprint == _truth().receipt_fingerprint
    assert result.decision_packet.readiness in {
        DecisionReadiness.PREPARE,
        DecisionReadiness.ESCALATE,
    }
    assert result.decision_packet.firm_company_claim_authorized is True
    assert result.decision_packet.automatic_external_execution_allowed is False
    assert result.execution_authority_granted is False


def test_bound_attention_signal_without_exact_reasoning_provenance_fails_closed():
    reasoning = _reasoning()

    with pytest.raises(
        ValueError,
        match="situation_reasoned_decision_signal_reasoning_provenance_missing",
    ):
        build_situation_reasoned_decision(
            reasoning=reasoning,
            payload=_payload(reasoning, include_reasoning_provenance=False),
            bound_signal_ids=(SIGNAL_ID,),
        )


def test_unbound_attention_signal_cannot_influence_reasoned_decision():
    reasoning = _reasoning()

    with pytest.raises(
        ValueError,
        match="situation_reasoned_decision_attention_signal_coverage_mismatch",
    ):
        build_situation_reasoned_decision(
            reasoning=reasoning,
            payload=_payload(reasoning, add_second_attention_signal=True),
            bound_signal_ids=(SIGNAL_ID,),
        )


def test_generic_decision_id_cannot_reuse_situation_reasoning():
    reasoning = _reasoning()

    with pytest.raises(
        ValueError,
        match="situation_reasoned_decision_id_binding_mismatch",
    ):
        build_situation_reasoned_decision(
            reasoning=reasoning,
            payload=_payload(
                reasoning,
                decision_id="decision://generic/company",
            ),
            bound_signal_ids=(SIGNAL_ID,),
        )


def test_cross_tenant_live_truth_is_rejected_before_decision_synthesis():
    reasoning = _reasoning()
    payload = _payload(reasoning).model_copy(
        update={"decision_truth": _truth(tenant="tenant://other")}
    )

    with pytest.raises(
        ValueError,
        match="situation_reasoned_decision_truth_tenant_mismatch",
    ):
        build_situation_reasoned_decision(
            reasoning=reasoning,
            payload=payload,
            bound_signal_ids=(SIGNAL_ID,),
        )


def test_missing_live_truth_keeps_reasoned_decision_on_hold_and_suppresses_prepare_actions():
    reasoning = _reasoning()
    result = build_situation_reasoned_decision(
        reasoning=reasoning,
        payload=_payload(reasoning, truth=False),
        bound_signal_ids=(SIGNAL_ID,),
    )

    assert result.decision_packet.readiness is DecisionReadiness.HOLD
    assert "live_company_truth_receipt_missing" in result.decision_packet.blockers
    assert result.decision_packet.safe_prepare_action_ids == ()
    assert result.decision_packet.firm_company_claim_authorized is False
    assert result.decision_packet.automatic_external_execution_allowed is False
    assert result.execution_authority_granted is False
