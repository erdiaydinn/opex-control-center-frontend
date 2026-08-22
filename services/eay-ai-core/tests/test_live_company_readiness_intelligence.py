from datetime import datetime, timezone

import pytest

from app.live_company_readiness import (
    DecisionTruthRequirement,
    DecisionTruthStatus,
    SourceTruthReadiness,
    evaluate_decision_truth_readiness,
)
from app.live_company_reality import (
    LiveBindingReceipt,
    LiveBindingStatus,
    LiveCompanyRealitySnapshot,
    LiveRealityStatus,
    LiveSourceKind,
)
from app.world_model import (
    EntityKind,
    ResolvedField,
    TruthClass,
    WorldEntity,
    WorldSnapshot,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
TENANT = "warehouse:fulya"
FIELD_KEY = "warehouse:fulya:orders_7d"


def _receipt(
    *,
    binding_id="orders-live-v1",
    source_kind=LiveSourceKind.ORDERS,
    status=LiveBindingStatus.ACCEPTED,
    entity_id="warehouse:fulya",
    field_name="orders_7d",
    reasons=(),
    tenant_id=TENANT,
):
    return LiveBindingReceipt(
        binding_id=binding_id,
        tenant_id=tenant_id,
        source_kind=source_kind,
        source_ref=f"source://{source_kind.value}/authoritative",
        status=status,
        entity_id=entity_id,
        field_name=field_name,
        observed_at=NOW,
        evidence_ref="evidence://live/1",
        source_receipt_ref="receipt://live/1",
        attestation_fingerprint="a" * 64,
        assertion_id="live:assertion" if status is LiveBindingStatus.ACCEPTED else None,
        reasons=reasons,
    )


def _world(*, include_field=True, blocked=()):
    fields = ()
    if include_field:
        fields = (
            ResolvedField(
                entity_id="warehouse:fulya",
                field_name="orders_7d",
                value=1200,
                truth_class=TruthClass.GOVERNED_OPERATIONAL,
                confidence=1.0,
                assertion_ids=("live:assertion",),
                evidence_refs=("evidence://live/1",),
            ),
        )
    return WorldSnapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=(
            WorldEntity(
                entity_id="warehouse:fulya",
                tenant_id=TENANT,
                kind=EntityKind.WAREHOUSE,
                display_name="Fulya",
            ),
        ),
        fields=fields,
        relations=(),
        contradictions=(),
        blocked_field_keys=tuple(blocked),
        fingerprint="0" * 64,
    )


def _snapshot(*, receipts=None, world=None, status=LiveRealityStatus.READY):
    return LiveCompanyRealitySnapshot(
        tenant_id=TENANT,
        as_of=NOW,
        status=status,
        world=world or _world(),
        binding_receipts=tuple(receipts if receipts is not None else [_receipt()]),
        unavailable_binding_ids=(),
        degraded_binding_ids=(),
    )


def _requirement(**overrides):
    payload = dict(
        requirement_id="diagnose-fulya-v1",
        tenant_id=TENANT,
        required_binding_ids=("orders-live-v1",),
        required_field_keys=(FIELD_KEY,),
    )
    payload.update(overrides)
    return DecisionTruthRequirement(**payload)


def test_required_live_source_and_fact_authorize_firm_claim():
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.PROCEED
    assert result.firm_claim_authorized is True
    assert result.source_readiness[0].status is SourceTruthReadiness.READY


def test_missing_required_binding_blocks_decision():
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(receipts=[]),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.BLOCKED
    assert result.firm_claim_authorized is False
    assert result.missing_required_binding_ids == ("orders-live-v1",)
    assert "required_source_unavailable" in result.reasons


def test_stale_required_source_blocks_even_if_old_field_exists():
    stale = _receipt(
        status=LiveBindingStatus.STALE,
        reasons=("observation_stale",),
    )
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(receipts=[stale]),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.BLOCKED
    assert result.stale_required_binding_ids == ("orders-live-v1",)
    assert result.firm_claim_authorized is False


def test_required_equal_authority_conflict_blocks_firm_claim():
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(
            world=_world(include_field=False, blocked=(FIELD_KEY,)),
            status=LiveRealityStatus.CONFLICT,
        ),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.BLOCKED
    assert result.conflicted_required_binding_ids == ("orders-live-v1",)
    assert result.conflicted_required_field_keys == (FIELD_KEY,)
    assert result.source_readiness[0].status is SourceTruthReadiness.CONFLICT


def test_missing_required_fact_blocks_even_when_source_has_other_accepted_fact():
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(),
        requirement=_requirement(
            required_field_keys=("warehouse:fulya:cancel_rate",),
        ),
    )

    assert result.status is DecisionTruthStatus.BLOCKED
    assert result.missing_required_field_keys == ("warehouse:fulya:cancel_rate",)
    assert "required_fact_missing" in result.reasons


def test_partially_rejected_required_source_is_blocked_by_default():
    rejected = _receipt(
        status=LiveBindingStatus.REJECTED,
        reasons=("schema_version_mismatch",),
    )
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(receipts=[_receipt(), rejected]),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.BLOCKED
    assert result.degraded_required_binding_ids == ("orders-live-v1",)
    assert result.source_readiness[0].status is SourceTruthReadiness.DEGRADED


def test_explicitly_allowed_degraded_source_only_allows_qualified_claim():
    rejected = _receipt(
        status=LiveBindingStatus.REJECTED,
        reasons=("one_observation_rejected",),
    )
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(receipts=[_receipt(), rejected]),
        requirement=_requirement(allow_degraded_required_bindings=True),
    )

    assert result.status is DecisionTruthStatus.QUALIFIED
    assert result.firm_claim_authorized is False
    assert "required_source_degraded" in result.reasons


def test_optional_unavailable_source_downgrades_to_qualified_not_firm():
    optional = _receipt(
        binding_id="weather-live-v1",
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        status=LiveBindingStatus.SOURCE_UNAVAILABLE,
        entity_id=None,
        field_name=None,
        reasons=("optional_source_observation_missing",),
    )
    result = evaluate_decision_truth_readiness(
        snapshot=_snapshot(receipts=[_receipt(), optional]),
        requirement=_requirement(),
    )

    assert result.status is DecisionTruthStatus.QUALIFIED
    assert result.firm_claim_authorized is False


def test_snapshot_tenant_mismatch_fails_closed():
    with pytest.raises(ValueError, match="decision_truth_tenant_mismatch"):
        evaluate_decision_truth_readiness(
            snapshot=_snapshot(),
            requirement=_requirement(tenant_id="warehouse:besiktas"),
        )


def test_cross_tenant_receipt_fails_closed():
    with pytest.raises(
        ValueError,
        match="decision_truth_receipt_tenant_mismatch",
    ):
        evaluate_decision_truth_readiness(
            snapshot=_snapshot(
                receipts=[_receipt(tenant_id="warehouse:besiktas")],
            ),
            requirement=_requirement(),
        )


def test_requirement_cannot_be_empty_or_ambiguous():
    with pytest.raises(
        ValueError,
        match="decision_truth_requirement_must_name_truth",
    ):
        DecisionTruthRequirement(
            requirement_id="empty",
            tenant_id=TENANT,
        )
