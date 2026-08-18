from datetime import datetime, timedelta, timezone

import pytest

from app.live_company_reality import (
    LiveBindingStatus,
    LiveEvidenceClass,
    LiveFactObservation,
    LiveRealityStatus,
    LiveSourceBindingPolicy,
    LiveSourceKind,
    bind_live_observation,
    build_live_company_reality_snapshot,
)
from app.world_model import EntityKind, TruthClass, WorldEntity

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
TENANT = "warehouse:fulya"


def _entity(entity_id="warehouse:fulya", kind=EntityKind.WAREHOUSE):
    return WorldEntity(
        entity_id=entity_id,
        tenant_id=TENANT,
        kind=kind,
        display_name=entity_id,
    )


def _policy(**overrides):
    payload = dict(
        binding_id="inventory-live-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="inventory://authoritative/postgres",
        schema_contract="inventory-stock-v1",
        schema_version="1.0.0",
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        max_observation_age_seconds=300,
        allowed_fields=("stock_on_hand",),
    )
    payload.update(overrides)
    return LiveSourceBindingPolicy(**payload)


def _observation(**overrides):
    payload = dict(
        binding_id="inventory-live-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="inventory://authoritative/postgres",
        schema_contract="inventory-stock-v1",
        schema_version="1.0.0",
        entity_id="warehouse:fulya",
        field_name="stock_on_hand",
        value=27,
        valid_from=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(seconds=30),
        evidence_ref="evidence://inventory/readback/27",
        source_receipt_ref="receipt://inventory/query/abc",
        evidence_class=LiveEvidenceClass.AUTHORITATIVE_LIVE,
        live_source_verified=True,
        confidence=1.0,
    )
    payload.update(overrides)
    return LiveFactObservation(**payload)


def test_authoritative_current_observation_enters_existing_world_model():
    result = build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[_entity()],
        policies=[_policy()],
        observations=[_observation()],
    )

    assert result.status is LiveRealityStatus.READY
    assert result.binding_receipts[0].status is LiveBindingStatus.ACCEPTED
    field = next(field for field in result.world.fields if field.field_name == "stock_on_hand")
    assert field.value == 27
    assert field.truth_class is TruthClass.GOVERNED_OPERATIONAL


def test_wrong_tenant_is_rejected_before_world_truth():
    outcome = bind_live_observation(
        policy=_policy(),
        observation=_observation(tenant_id="warehouse:besiktas"),
        as_of=NOW,
    )

    assert outcome.assertion is None
    assert outcome.receipt.status is LiveBindingStatus.REJECTED
    assert "tenant_mismatch" in outcome.receipt.reasons


def test_stale_live_observation_never_enters_world_truth():
    result = build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[_entity()],
        policies=[_policy(max_observation_age_seconds=60)],
        observations=[_observation(observed_at=NOW - timedelta(minutes=10))],
    )

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert result.world.fields == ()
    assert result.binding_receipts[0].status is LiveBindingStatus.STALE


@pytest.mark.parametrize(
    "evidence_class",
    [
        LiveEvidenceClass.CONTROLLED_LIVE,
        LiveEvidenceClass.SYNTHETIC,
        LiveEvidenceClass.REPOSITORY,
        LiveEvidenceClass.MODEL_DERIVED,
    ],
)
def test_non_authoritative_evidence_cannot_be_promoted_to_live_truth(evidence_class):
    outcome = bind_live_observation(
        policy=_policy(),
        observation=_observation(evidence_class=evidence_class),
        as_of=NOW,
    )

    assert outcome.assertion is None
    assert outcome.receipt.status is LiveBindingStatus.REJECTED
    assert "evidence_not_authoritative_live" in outcome.receipt.reasons


def test_repository_green_without_live_source_verification_is_not_live_truth():
    outcome = bind_live_observation(
        policy=_policy(),
        observation=_observation(live_source_verified=False),
        as_of=NOW,
    )

    assert outcome.assertion is None
    assert "live_source_not_verified" in outcome.receipt.reasons


def test_schema_and_field_namespace_drift_fail_closed():
    outcome = bind_live_observation(
        policy=_policy(),
        observation=_observation(schema_version="2.0.0", field_name="budget_available"),
        as_of=NOW,
    )

    assert outcome.assertion is None
    assert set(outcome.receipt.reasons) >= {"schema_version_mismatch", "field_namespace_not_allowed"}


def test_missing_required_source_reports_source_unavailable_not_fake_zero():
    result = build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[_entity()],
        policies=[_policy()],
        observations=[],
    )

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert result.unavailable_binding_ids == ("inventory-live-v1",)
    assert result.world.fields == ()
    assert result.binding_receipts[0].status is LiveBindingStatus.SOURCE_UNAVAILABLE


def test_equal_authority_live_conflict_remains_blocked_by_world_model():
    result = build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[_entity()],
        policies=[_policy()],
        observations=[
            _observation(value=27, evidence_ref="evidence://inventory/a"),
            _observation(value=24, evidence_ref="evidence://inventory/b"),
        ],
    )

    assert result.status is LiveRealityStatus.CONFLICT
    assert "warehouse:fulya:stock_on_hand" in result.world.blocked_field_keys
    assert not any(field.field_name == "stock_on_hand" for field in result.world.fields)


def test_lower_authority_external_context_cannot_override_operational_truth():
    external_policy = LiveSourceBindingPolicy(
        binding_id="external-stock-signal-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        source_ref="external://verified/signal",
        schema_contract="external-stock-signal-v1",
        schema_version="1.0.0",
        truth_class=TruthClass.VERIFIED_EXTERNAL,
        max_observation_age_seconds=300,
        allowed_fields=("stock_on_hand",),
        required=False,
    )
    external_observation = LiveFactObservation(
        binding_id="external-stock-signal-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        source_ref="external://verified/signal",
        schema_contract="external-stock-signal-v1",
        schema_version="1.0.0",
        entity_id="warehouse:fulya",
        field_name="stock_on_hand",
        value=999,
        valid_from=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(seconds=20),
        evidence_ref="evidence://external/signal",
        source_receipt_ref="receipt://external/query/xyz",
        evidence_class=LiveEvidenceClass.AUTHORITATIVE_LIVE,
        live_source_verified=True,
        confidence=1.0,
    )

    result = build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=[_entity()],
        policies=[_policy(), external_policy],
        observations=[_observation(value=27), external_observation],
    )

    field = next(field for field in result.world.fields if field.field_name == "stock_on_hand")
    assert field.value == 27
    assert field.truth_class is TruthClass.GOVERNED_OPERATIONAL


def test_receipt_does_not_retain_raw_fact_value_or_payload():
    marker = "SUPER-SECRET-RAW-PAYLOAD-9917"
    outcome = bind_live_observation(
        policy=_policy(),
        observation=_observation(value={"count": 27, "raw": marker}),
        as_of=NOW,
    )

    serialized_receipt = outcome.receipt.model_dump_json()
    assert marker not in serialized_receipt
    assert '"value"' not in serialized_receipt


def test_policy_cannot_turn_model_inference_into_live_authority():
    with pytest.raises(ValueError, match="live_binding_cannot_promote_analytic_inference"):
        _policy(truth_class=TruthClass.ANALYTIC_INFERENCE)
