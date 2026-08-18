from __future__ import annotations

from app.insight.governed_metrics import GovernedMetric, can_activate_family
from app.insight.product_experience import MetricProvenance, build_insight_card
from app.insight.proactive import (
    action_requires_approval,
    auto_action_permitted,
    create_signal,
)
from app.jarvis.orders_v2_production_truth import (
    REQUIRED_EVIDENCE_KEYS,
    ProductionEvidence,
    orders_v2_production_receipt,
)

TENANT = "tenant-a"


def evidence(
    *,
    evidence_class: str,
    tenant_id: str = TENANT,
) -> tuple[ProductionEvidence, ...]:
    return tuple(
        ProductionEvidence(
            key=key,
            tenant_id=tenant_id,
            evidence_class=evidence_class,
            passed=True,
            provenance=f"evidence:{key}",
            approver="release-reviewer",
        )
        for key in REQUIRED_EVIDENCE_KEYS
    )


def test_synthetic_orders_v2_proof_never_activates_production() -> None:
    receipt = orders_v2_production_receipt(
        evidence(evidence_class="SYNTHETIC")
    )
    assert not receipt.ready
    assert receipt.production_activation_permitted is False
    assert all("not_live_production_evidence" in blocker for blocker in receipt.blockers)


def test_live_orders_receipt_is_tenant_and_provenance_bound() -> None:
    receipt = orders_v2_production_receipt(
        evidence(evidence_class="REAL_PRODUCTION_READONLY")
    )
    assert receipt.ready
    assert receipt.tenant_id == TENANT
    assert len(receipt.evidence_fingerprint) == 64

    mixed = list(evidence(evidence_class="REAL_PRODUCTION_READONLY"))
    mixed[-1] = ProductionEvidence(
        key=mixed[-1].key,
        tenant_id="tenant-b",
        evidence_class="REAL_PRODUCTION_READONLY",
        passed=True,
        provenance="foreign",
        approver="reviewer",
    )
    assert not orders_v2_production_receipt(tuple(mixed)).ready


def test_kpi_family_expansion_requires_orders_receipt_and_metric_governance() -> None:
    metric = GovernedMetric(
        tenant_id=TENANT,
        key="ops.kpi.nsfr.v1",
        family="nsfr_pfr_refund",
        formula_version="v1",
        glossary_concept_id="NSFR",
        source_contract="bq:orders-v2",
        production_ready=True,
    )
    synthetic = orders_v2_production_receipt(
        evidence(evidence_class="SYNTHETIC")
    )
    assert not can_activate_family(
        tenant_id=TENANT,
        family="nsfr_pfr_refund",
        orders_v2_receipt=synthetic,
        metrics=(metric,),
    )

    live = orders_v2_production_receipt(
        evidence(evidence_class="REAL_PRODUCTION_READONLY")
    )
    assert can_activate_family(
        tenant_id=TENANT,
        family="nsfr_pfr_refund",
        orders_v2_receipt=live,
        metrics=(metric,),
    )
    assert not can_activate_family(
        tenant_id="tenant-b",
        family="nsfr_pfr_refund",
        orders_v2_receipt=live,
        metrics=(metric,),
    )


def test_insight_card_and_proactive_action_are_tenant_provenance_bound() -> None:
    provenance = MetricProvenance(
        tenant_id=TENANT,
        metric_key="otp",
        formula_version="v3",
        source_contract="bq:otp",
        glossary_concept_id="OTP",
        evidence_fingerprint="a" * 64,
        observed_at="2026-08-18T00:00:00Z",
    )
    card = build_insight_card(
        tenant_id=TENANT,
        metric_key="otp",
        value=94.0,
        trend=(95.0, 94.0),
        explanation="Late prep increased",
        provenance=provenance,
        root_causes=("prep",),
        anomaly=True,
    )
    assert card.anomaly

    signal = create_signal(
        tenant_id=TENANT,
        key="warehouse_pressure",
        module="workforce",
        reason="effective capacity below governed demand",
        evidence_refs=("demand:1", "capacity:1"),
        risk="HIGH",
        policy_version="workforce-pressure-v1",
        proposed_action="open_shift",
    )
    assert action_requires_approval(signal)
    assert not auto_action_permitted(signal)

    low_risk = create_signal(
        tenant_id=TENANT,
        key="academy_gap",
        module="academy",
        reason="training completion below threshold",
        evidence_refs=("academy:completion:1",),
        risk="LOW",
        policy_version="academy-gap-v1",
        proposed_action="assign_training",
    )
    assert action_requires_approval(low_risk)
    assert not auto_action_permitted(low_risk)
