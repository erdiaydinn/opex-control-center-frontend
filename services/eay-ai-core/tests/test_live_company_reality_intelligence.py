from datetime import datetime, timedelta, timezone

import pytest

from app.live_company_reality import (
    LiveBindingStatus,
    LiveEvidenceClass,
    LiveFactObservation,
    LiveRealityStatus,
    LiveSourceAttestation,
    LiveSourceBindingPolicy,
    LiveSourceKind,
    bind_live_observation,
    build_live_company_reality_snapshot,
    build_live_source_attestation,
)
from app.world_model import EntityKind, TruthClass, WorldEntity

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
TENANT = "warehouse:fulya"
KNOWN_ENTITY_IDS = {TENANT}


def _entity(entity_id=TENANT, tenant=TENANT, kind=EntityKind.WAREHOUSE):
    return WorldEntity(
        entity_id=entity_id,
        tenant_id=tenant,
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
        environment_ref="env://inventory/production",
        execution_identity_ref="identity://inventory/read-only-runtime",
        verifier_ref="verifier://inventory/readback-v1",
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        max_observation_age_seconds=300,
        max_attestation_age_seconds=300,
        allowed_fields=("stock_on_hand",),
    )
    payload.update(overrides)
    return LiveSourceBindingPolicy(**payload)


def _attestation(**overrides):
    payload = dict(
        binding_id="inventory-live-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="inventory://authoritative/postgres",
        schema_contract="inventory-stock-v1",
        schema_version="1.0.0",
        environment_ref="env://inventory/production",
        execution_identity_ref="identity://inventory/read-only-runtime",
        verifier_ref="verifier://inventory/readback-v1",
        verified_at=NOW - timedelta(seconds=20),
        evidence_ref="evidence://inventory/readback/27",
        source_receipt_ref="receipt://inventory/query/abc",
        evidence_class=LiveEvidenceClass.AUTHORITATIVE_LIVE,
        field_production_verified=True,
    )
    payload.update(overrides)
    return build_live_source_attestation(**payload)


def _observation(**overrides):
    payload = dict(
        binding_id="inventory-live-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.INVENTORY,
        source_ref="inventory://authoritative/postgres",
        schema_contract="inventory-stock-v1",
        schema_version="1.0.0",
        entity_id=TENANT,
        field_name="stock_on_hand",
        value=27,
        valid_from=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(seconds=30),
        confidence=1.0,
        attestation=_attestation(),
    )
    payload.update(overrides)
    return LiveFactObservation(**payload)


def _bind(observation=None, policy=None, trusted=None):
    item = observation or _observation()
    trusted_fingerprints = (
        {item.attestation.fingerprint}
        if trusted is None
        else trusted
    )
    return bind_live_observation(
        policy=policy or _policy(),
        observation=item,
        as_of=NOW,
        known_entity_ids=KNOWN_ENTITY_IDS,
        trusted_attestation_fingerprints=trusted_fingerprints,
    )


def _snapshot(*, policies=None, observations=None, entities=None, trusted=None):
    items = observations if observations is not None else [_observation()]
    trusted_fingerprints = (
        {item.attestation.fingerprint for item in items}
        if trusted is None
        else trusted
    )
    return build_live_company_reality_snapshot(
        tenant_id=TENANT,
        as_of=NOW,
        entities=entities or [_entity()],
        policies=policies or [_policy()],
        observations=items,
        trusted_attestation_fingerprints=trusted_fingerprints,
    )


def test_authoritative_current_observation_enters_existing_world_model():
    result = _snapshot()

    assert result.status is LiveRealityStatus.READY
    assert result.binding_receipts[0].status is LiveBindingStatus.ACCEPTED
    field = next(
        field for field in result.world.fields
        if field.field_name == "stock_on_hand"
    )
    assert field.value == 27
    assert field.truth_class is TruthClass.GOVERNED_OPERATIONAL


def test_wrong_tenant_is_rejected_before_world_truth():
    attestation = _attestation(tenant_id="warehouse:besiktas")
    observation = _observation(
        tenant_id="warehouse:besiktas",
        attestation=attestation,
    )
    outcome = _bind(observation)

    assert outcome.assertion is None
    assert outcome.receipt.status is LiveBindingStatus.REJECTED
    assert "tenant_mismatch" in outcome.receipt.reasons
    assert "attestation_tenant_mismatch" in outcome.receipt.reasons


def test_unknown_entity_is_rejected_instead_of_silently_dropped():
    result = _snapshot(observations=[_observation(entity_id="warehouse:ghost")])

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert result.world.fields == ()
    assert "entity_unknown_for_tenant" in result.binding_receipts[0].reasons


def test_cross_tenant_entity_does_not_count_as_known_entity():
    result = _snapshot(
        entities=[
            _entity(),
            _entity(
                entity_id="warehouse:besiktas",
                tenant="warehouse:besiktas",
            ),
        ],
        observations=[_observation(entity_id="warehouse:besiktas")],
    )

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert "entity_unknown_for_tenant" in result.binding_receipts[0].reasons


def test_untrusted_attestation_cannot_self_authorize_live_truth():
    outcome = _bind(_observation(), trusted=set())

    assert outcome.assertion is None
    assert outcome.receipt.status is LiveBindingStatus.REJECTED
    assert "attestation_not_in_trusted_registry" in outcome.receipt.reasons


def test_stale_live_observation_never_enters_world_truth():
    result = _snapshot(
        policies=[_policy(max_observation_age_seconds=60)],
        observations=[
            _observation(observed_at=NOW - timedelta(minutes=10))
        ],
    )

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert result.world.fields == ()
    assert result.binding_receipts[0].status is LiveBindingStatus.STALE
    assert "observation_stale" in result.binding_receipts[0].reasons


def test_stale_attestation_never_authorizes_fresh_observation():
    attestation = _attestation(verified_at=NOW - timedelta(hours=1))
    outcome = _bind(
        _observation(attestation=attestation),
        _policy(max_attestation_age_seconds=60),
    )

    assert outcome.assertion is None
    assert outcome.receipt.status is LiveBindingStatus.STALE
    assert "attestation_stale" in outcome.receipt.reasons


@pytest.mark.parametrize(
    "evidence_class",
    [
        LiveEvidenceClass.CONTROLLED_LIVE,
        LiveEvidenceClass.SYNTHETIC,
        LiveEvidenceClass.REPOSITORY,
        LiveEvidenceClass.MODEL_DERIVED,
    ],
)
def test_non_authoritative_evidence_cannot_be_promoted(evidence_class):
    attestation = _attestation(evidence_class=evidence_class)
    outcome = _bind(_observation(attestation=attestation))

    assert outcome.assertion is None
    assert "evidence_not_authoritative_live" in outcome.receipt.reasons


def test_repository_green_is_not_field_production_truth():
    attestation = _attestation(
        evidence_class=LiveEvidenceClass.REPOSITORY,
        field_production_verified=False,
    )
    outcome = _bind(_observation(attestation=attestation))

    assert outcome.assertion is None
    assert "evidence_not_authoritative_live" in outcome.receipt.reasons
    assert "field_production_not_verified" in outcome.receipt.reasons


def test_wrong_verifier_environment_or_identity_fails_closed():
    attestation = _attestation(
        verifier_ref="verifier://unknown",
        environment_ref="env://inventory/staging",
        execution_identity_ref="identity://wrong",
    )
    outcome = _bind(_observation(attestation=attestation))

    assert outcome.assertion is None
    assert set(outcome.receipt.reasons) >= {
        "attestation_verifier_mismatch",
        "attestation_environment_mismatch",
        "attestation_execution_identity_mismatch",
    }


def test_attestation_fingerprint_is_stable_and_tamper_evident():
    first = _attestation()
    second = _attestation()
    assert first.fingerprint == second.fingerprint

    payload = first.model_dump()
    payload["source_receipt_ref"] = "receipt://forged"
    with pytest.raises(
        ValueError,
        match="live_attestation_fingerprint_mismatch",
    ):
        LiveSourceAttestation(**payload)


def test_schema_and_field_namespace_drift_fail_closed():
    outcome = _bind(
        _observation(
            schema_version="2.0.0",
            field_name="budget_available",
        )
    )

    assert outcome.assertion is None
    assert set(outcome.receipt.reasons) >= {
        "schema_version_mismatch",
        "field_namespace_not_allowed",
    }


def test_missing_required_source_is_unavailable_not_fake_zero():
    result = _snapshot(observations=[])

    assert result.status is LiveRealityStatus.SOURCE_UNAVAILABLE
    assert result.unavailable_binding_ids == ("inventory-live-v1",)
    assert result.world.fields == ()
    assert result.binding_receipts[0].status is LiveBindingStatus.SOURCE_UNAVAILABLE


def test_equal_authority_live_conflict_remains_blocked():
    first = _observation(
        value=27,
        attestation=_attestation(evidence_ref="evidence://inventory/a"),
    )
    second = _observation(
        value=24,
        attestation=_attestation(evidence_ref="evidence://inventory/b"),
    )
    result = _snapshot(observations=[first, second])

    assert result.status is LiveRealityStatus.CONFLICT
    assert "warehouse:fulya:stock_on_hand" in result.world.blocked_field_keys
    assert not any(
        field.field_name == "stock_on_hand"
        for field in result.world.fields
    )


def test_lower_authority_external_context_cannot_override_operations():
    external_policy = LiveSourceBindingPolicy(
        binding_id="external-stock-signal-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        source_ref="external://verified/signal",
        schema_contract="external-stock-signal-v1",
        schema_version="1.0.0",
        environment_ref="env://external/production",
        execution_identity_ref="identity://external/reader",
        verifier_ref="verifier://external/source-v1",
        truth_class=TruthClass.VERIFIED_EXTERNAL,
        max_observation_age_seconds=300,
        max_attestation_age_seconds=300,
        allowed_fields=("stock_on_hand",),
        required=False,
    )
    external_attestation = build_live_source_attestation(
        binding_id="external-stock-signal-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        source_ref="external://verified/signal",
        schema_contract="external-stock-signal-v1",
        schema_version="1.0.0",
        environment_ref="env://external/production",
        execution_identity_ref="identity://external/reader",
        verifier_ref="verifier://external/source-v1",
        verified_at=NOW - timedelta(seconds=10),
        evidence_ref="evidence://external/signal",
        source_receipt_ref="receipt://external/query/xyz",
        evidence_class=LiveEvidenceClass.AUTHORITATIVE_LIVE,
        field_production_verified=True,
    )
    external_observation = LiveFactObservation(
        binding_id="external-stock-signal-v1",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.EXTERNAL_CONTEXT,
        source_ref="external://verified/signal",
        schema_contract="external-stock-signal-v1",
        schema_version="1.0.0",
        entity_id=TENANT,
        field_name="stock_on_hand",
        value=999,
        valid_from=NOW - timedelta(minutes=2),
        observed_at=NOW - timedelta(seconds=20),
        confidence=1.0,
        attestation=external_attestation,
    )
    operational = _observation(value=27)
    result = _snapshot(
        policies=[_policy(), external_policy],
        observations=[operational, external_observation],
    )

    field = next(
        field for field in result.world.fields
        if field.field_name == "stock_on_hand"
    )
    assert field.value == 27
    assert field.truth_class is TruthClass.GOVERNED_OPERATIONAL


def test_receipt_does_not_retain_raw_fact_value_or_payload():
    marker = "SUPER-SECRET-RAW-PAYLOAD-9917"
    outcome = _bind(
        _observation(value={"count": 27, "raw": marker})
    )

    serialized = outcome.receipt.model_dump_json()
    assert marker not in serialized
    assert '"value"' not in serialized


def test_policy_cannot_promote_model_inference_to_live_authority():
    with pytest.raises(
        ValueError,
        match="live_binding_cannot_promote_analytic_inference",
    ):
        _policy(truth_class=TruthClass.ANALYTIC_INFERENCE)
