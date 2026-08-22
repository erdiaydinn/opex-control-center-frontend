from datetime import datetime, timedelta, timezone

import pytest

from app.executive_world_state import (
    ExecutiveFieldRequirement,
    FieldFreshnessObservation,
    WorldChangeKind,
    WorldRequirementStatus,
    assess_executive_world_readiness,
    build_decision_subgraph,
    diff_world_snapshots,
)
from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    WorldRelation,
    build_world_snapshot,
)

T0 = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
TENANT = "tenant://ys-tr"


def _entity(entity_id, kind):
    return WorldEntity(
        entity_id=entity_id,
        tenant_id=TENANT,
        kind=kind,
        display_name=entity_id,
    )


def _relation(relation_id, source, target):
    return WorldRelation(
        relation_id=relation_id,
        tenant_id=TENANT,
        source_entity_id=source,
        relation_type="decision_context",
        target_entity_id=target,
        valid_from=T0,
        evidence_ref=f"evidence://{relation_id}",
    )


def _assertion(assertion_id, entity_id, field_name, value, observed_at=T0, source="source://live"):
    return WorldAssertion(
        assertion_id=assertion_id,
        tenant_id=TENANT,
        entity_id=entity_id,
        field_name=field_name,
        value=value,
        truth_class=TruthClass.VERIFIED_COMPANY,
        valid_from=observed_at,
        observed_at=observed_at,
        source_ref=source,
        evidence_ref=f"evidence://{assertion_id}",
        confidence=0.95,
    )


def _snapshot(as_of=T0, assertions=(), relations=()):
    entities = (
        _entity("warehouse://fulya", EntityKind.WAREHOUSE),
        _entity("kpi://orders", EntityKind.KPI),
        _entity("product://sku-a", EntityKind.PRODUCT),
        _entity("warehouse://other", EntityKind.WAREHOUSE),
    )
    return build_world_snapshot(
        tenant_id=TENANT,
        as_of=as_of,
        entities=list(entities),
        assertions=list(assertions),
        relations=list(relations),
    )


def test_decision_subgraph_follows_only_canonical_relations_and_field_allowlist():
    snapshot = _snapshot(
        assertions=(
            _assertion("a1", "warehouse://fulya", "orders", 100),
            _assertion("a2", "warehouse://fulya", "nsfr", 0.012),
            _assertion("a3", "kpi://orders", "value", 100),
            _assertion("a4", "product://sku-a", "availability", 0.9),
            _assertion("a5", "warehouse://other", "orders", 200),
        ),
        relations=(
            _relation("rel-orders", "warehouse://fulya", "kpi://orders"),
            _relation("rel-product", "warehouse://fulya", "product://sku-a"),
        ),
    )
    subgraph = build_decision_subgraph(
        snapshot=snapshot,
        seed_entity_ids=("warehouse://fulya",),
        relationship_hops=1,
        field_allowlist=("orders", "value", "availability"),
    )

    assert {item.entity_id for item in subgraph.entities} == {
        "warehouse://fulya",
        "kpi://orders",
        "product://sku-a",
    }
    assert {(item.entity_id, item.field_name) for item in subgraph.fields} == {
        ("warehouse://fulya", "orders"),
        ("kpi://orders", "value"),
        ("product://sku-a", "availability"),
    }
    assert {item.relation_id for item in subgraph.relations} == {"rel-orders", "rel-product"}
    assert all(item.entity_id != "warehouse://other" for item in subgraph.entities)
    assert subgraph.persistent_memory_authority is False
    assert subgraph.truth_authority_granted is False


def test_world_readiness_exposes_ready_stale_missing_and_blocked_fields():
    as_of = T0 + timedelta(hours=2)
    snapshot = _snapshot(
        as_of=as_of,
        assertions=(
            _assertion("orders-old", "warehouse://fulya", "orders", 100, observed_at=T0),
            _assertion("nsfr-a", "warehouse://fulya", "nsfr", 0.010, observed_at=as_of),
            _assertion(
                "nsfr-b",
                "warehouse://fulya",
                "nsfr",
                0.020,
                observed_at=as_of,
                source="source://independent-equal-authority",
            ),
            _assertion("availability", "product://sku-a", "availability", 0.9, observed_at=as_of),
        ),
    )
    readiness = assess_executive_world_readiness(
        snapshot=snapshot,
        requirements=(
            ExecutiveFieldRequirement(
                entity_id="warehouse://fulya",
                field_name="orders",
                maximum_observation_age_seconds=1800,
            ),
            ExecutiveFieldRequirement(entity_id="warehouse://fulya", field_name="nsfr"),
            ExecutiveFieldRequirement(entity_id="warehouse://fulya", field_name="picking"),
            ExecutiveFieldRequirement(
                entity_id="product://sku-a",
                field_name="availability",
                maximum_observation_age_seconds=1800,
            ),
        ),
        freshness_observations=(
            FieldFreshnessObservation(
                entity_id="warehouse://fulya",
                field_name="orders",
                observed_at=T0,
                evidence_ref="evidence://orders-freshness",
            ),
            FieldFreshnessObservation(
                entity_id="product://sku-a",
                field_name="availability",
                observed_at=as_of,
                evidence_ref="evidence://availability-freshness",
            ),
        ),
    )

    status = {(item.entity_id, item.field_name): item.status for item in readiness.fields}
    assert status[("warehouse://fulya", "orders")] is WorldRequirementStatus.STALE
    assert status[("warehouse://fulya", "nsfr")] is WorldRequirementStatus.BLOCKED
    assert status[("warehouse://fulya", "picking")] is WorldRequirementStatus.MISSING
    assert status[("product://sku-a", "availability")] is WorldRequirementStatus.READY
    assert readiness.ready is False
    assert readiness.truth_authority_granted is False
    assert readiness.execution_authority_granted is False


def test_required_freshness_without_observation_fails_closed_as_unknown():
    snapshot = _snapshot(assertions=(_assertion("a1", "warehouse://fulya", "orders", 100),))
    readiness = assess_executive_world_readiness(
        snapshot=snapshot,
        requirements=(
            ExecutiveFieldRequirement(
                entity_id="warehouse://fulya",
                field_name="orders",
                maximum_observation_age_seconds=60,
            ),
        ),
    )
    assert readiness.ready is False
    assert readiness.fields[0].status is WorldRequirementStatus.FRESHNESS_UNKNOWN
    assert readiness.fields[0].blocker == "world_field_freshness_unknown:warehouse://fulya:orders"


def test_snapshot_delta_reports_value_change_without_copying_raw_business_values():
    before = _snapshot(
        as_of=T0,
        assertions=(_assertion("orders-before", "warehouse://fulya", "orders", 100),),
    )
    after_time = T0 + timedelta(hours=1)
    after = _snapshot(
        as_of=after_time,
        assertions=(
            _assertion("orders-after", "warehouse://fulya", "orders", 135, observed_at=after_time),
        ),
    )

    delta = diff_world_snapshots(before=before, after=after)

    assert len(delta.changes) == 1
    assert delta.changes[0].kind is WorldChangeKind.CHANGED
    assert delta.changes[0].field_key == "warehouse://fulya:orders"
    assert delta.changes[0].before_value_fingerprint != delta.changes[0].after_value_fingerprint
    assert delta.raw_values_retained is False
    serialized = delta.model_dump_json()
    assert '"value":100' not in serialized
    assert '"value":135' not in serialized
    assert delta.truth_authority_granted is False


def test_snapshot_delta_distinguishes_evidence_refresh_from_value_change():
    before = _snapshot(
        assertions=(_assertion("orders-v1", "warehouse://fulya", "orders", 100),)
    )
    after_time = T0 + timedelta(minutes=5)
    after = _snapshot(
        as_of=after_time,
        assertions=(
            _assertion("orders-v2", "warehouse://fulya", "orders", 100, observed_at=after_time),
        ),
    )

    delta = diff_world_snapshots(before=before, after=after)
    assert delta.changes[0].kind is WorldChangeKind.EVIDENCE_REFRESHED


def test_snapshot_delta_rejects_cross_tenant_comparison():
    before = _snapshot(assertions=(_assertion("a1", "warehouse://fulya", "orders", 100),))
    other_entity = WorldEntity(
        entity_id="warehouse://fulya",
        tenant_id="tenant://other",
        kind=EntityKind.WAREHOUSE,
        display_name="Fulya",
    )
    after = build_world_snapshot(
        tenant_id="tenant://other",
        as_of=T0,
        entities=[other_entity],
        assertions=[],
    )
    with pytest.raises(ValueError, match="world_delta_cross_tenant_forbidden"):
        diff_world_snapshots(before=before, after=after)
