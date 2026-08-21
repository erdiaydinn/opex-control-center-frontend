from __future__ import annotations

from app.insight.governed_metrics import GovernedMetric, can_activate_family
from app.insight.proactive import (
    action_requires_approval,
    auto_action_permitted,
    create_signal,
)
from app.insight.product_experience import MetricProvenance, build_insight_card
from app.jarvis.orders_v2_production_truth import (
    EXPECTED_EVIDENCE_CLASS,
    REQUIRED_EVIDENCE_KEYS,
    ProductionEvidence,
    orders_v2_production_receipt,
)

TENANT = "tenant-a"


def evidence(*, live: bool, tenant_id: str = TENANT) -> tuple[ProductionEvidence, ...]:
    records: list[ProductionEvidence] = []
    for key in REQUIRED_EVIDENCE_KEYS:
        records.append(
            ProductionEvidence(
                key=key,
                tenant_id=tenant_id,
                evidence_class=(
                    EXPECTED_EVIDENCE_CLASS[key] if live else "SYNTHETIC"
                ),
                passed=True,
                provenance=f"evidence:{key}",
                approver="release-reviewer",
            )
        )
    return tuple(records)


def test_synthetic_orders_v2_proof_never_activates_production() -> None:
    receipt = orders_v2_production_receipt(evidence(live=False))
    assert not receipt.ready
    assert receipt.production_activation_permitted is False
    assert all("wrong_evidence_class" in blocker for blocker in receipt.blockers)


def test_live_orders_receipt_is_tenant_and_provenance_bound_but_non_activating() -> None:
    receipt = orders_v2_production_receipt(evidence(live=True))
    assert receipt.ready
    assert receipt.tenant_id == TENANT
    assert len(receipt.evidence_fingerprint) == 64
    assert receipt.production_activation_permitted is False

    mixed = list(evidence(live=True))
    mixed[-1] = ProductionEvidence(
        key=mixed[-1].key,
        tenant_id="tenant-b",
        evidence_class="REAL_HUMAN_APPROVAL",
        passed=True,
        provenance="foreign",
        approver="reviewer",
    )
    assert not orders_v2_production_receipt(tuple(mixed)).ready


def test_human_promotion_evidence_is_not_misclassified_as_bigquery_observation() -> None:
    records = list(evidence(live=True))
    records[-1] = ProductionEvidence(
        key="human_release_deploy_promotion",
        tenant_id=TENANT,
        evidence_class="REAL_PRODUCTION_READONLY",
        passed=True,
        provenance="approval:1",
        approver="release-reviewer",
    )
    receipt = orders_v2_production_receipt(tuple(records))
    assert not receipt.ready
    assert "human_release_deploy_promotion:wrong_evidence_class" in receipt.blockers


def metric(*, family: str, tenant_id: str = TENANT) -> GovernedMetric:
    return GovernedMetric(
        tenant_id=tenant_id,
        key=f"ops.kpi.{family}.v1",
        family=family,
        formula_version="v1",
        glossary_concept_id=family.upper(),
        source_contract="bq:orders-v2",
        production_ready=True,
    )


def test_orders_and_later_kpi_families_require_live_same_tenant_receipt() -> None:
    synthetic = orders_v2_production_receipt(evidence(live=False))
    live = orders_v2_production_receipt(evidence(live=True))

    for family in ("orders", "nsfr_pfr_refund"):
        governed_metric = metric(family=family)
        assert not can_activate_family(
            tenant_id=TENANT,
            family=family,
            orders_v2_receipt=synthetic,
            metrics=(governed_metric,),
        )
        assert can_activate_family(
            tenant_id=TENANT,
            family=family,
            orders_v2_receipt=live,
            metrics=(governed_metric,),
        )
        assert not can_activate_family(
            tenant_id="tenant-b",
            family=family,
            orders_v2_receipt=live,
            metrics=(governed_metric,),
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
