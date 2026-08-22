from datetime import datetime, timedelta, timezone

from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    WorldRelation,
    build_world_snapshot,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 1, 30, tzinfo=UTC)


def _entity(entity_id="sku:1", tenant="warehouse:fulya", kind=EntityKind.SKU):
    return WorldEntity(
        entity_id=entity_id,
        tenant_id=tenant,
        kind=kind,
        display_name=entity_id,
    )


def _assertion(**overrides):
    payload = dict(
        assertion_id="stock-live",
        tenant_id="warehouse:fulya",
        entity_id="sku:1",
        field_name="stock_on_hand",
        value=27,
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=NOW - timedelta(minutes=10),
        observed_at=NOW - timedelta(minutes=5),
        source_ref="wms://stock",
        evidence_ref="evidence://stock/27",
        confidence=1.0,
    )
    payload.update(overrides)
    return WorldAssertion(**payload)


def test_analytic_inference_cannot_override_governed_operational_truth():
    snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[_entity()],
        assertions=[
            _assertion(),
            _assertion(
                assertion_id="forecast-stock",
                value=31,
                truth_class=TruthClass.ANALYTIC_INFERENCE,
                source_ref="model://forecast",
                evidence_ref="evidence://forecast",
                confidence=0.99,
            ),
        ],
    )

    stock = next(field for field in snapshot.fields if field.field_name == "stock_on_hand")
    assert stock.value == 27
    assert stock.truth_class is TruthClass.GOVERNED_OPERATIONAL


def test_equal_authority_conflict_blocks_field_instead_of_guessing():
    snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[_entity()],
        assertions=[
            _assertion(assertion_id="stock-a", value=27, evidence_ref="evidence://a"),
            _assertion(assertion_id="stock-b", value=24, evidence_ref="evidence://b"),
        ],
    )

    assert "sku:1:stock_on_hand" in snapshot.blocked_field_keys
    assert not any(field.field_name == "stock_on_hand" for field in snapshot.fields)
    assert snapshot.contradictions[0].reason == "equal_authority_active_assertions_conflict"


def test_snapshot_is_strictly_tenant_isolated():
    snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[
            _entity(),
            _entity(entity_id="sku:2", tenant="warehouse:besiktas"),
        ],
        assertions=[
            _assertion(),
            _assertion(
                assertion_id="other-tenant",
                tenant_id="warehouse:besiktas",
                entity_id="sku:2",
                value=999,
            ),
        ],
    )

    assert {entity.entity_id for entity in snapshot.entities} == {"sku:1"}
    assert all(field.entity_id == "sku:1" for field in snapshot.fields)


def test_temporal_snapshot_resolves_state_at_requested_time():
    older = _assertion(
        assertion_id="old-stock",
        value=30,
        valid_from=NOW - timedelta(hours=2),
        valid_to=NOW - timedelta(hours=1),
        observed_at=NOW - timedelta(hours=2),
        evidence_ref="evidence://old",
    )
    current = _assertion(
        assertion_id="current-stock",
        value=27,
        valid_from=NOW - timedelta(hours=1),
        observed_at=NOW - timedelta(minutes=50),
        evidence_ref="evidence://current",
    )

    old_snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW - timedelta(hours=1, minutes=30),
        entities=[_entity()],
        assertions=[older, current],
    )
    current_snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[_entity()],
        assertions=[older, current],
    )

    assert old_snapshot.fields[0].value == 30
    assert current_snapshot.fields[0].value == 27
    assert old_snapshot.fingerprint != current_snapshot.fingerprint


def test_relations_are_temporal_and_tenant_bound():
    warehouse = _entity(entity_id="warehouse:fulya", kind=EntityKind.WAREHOUSE)
    sku = _entity()
    relation = WorldRelation(
        relation_id="rel:stocks",
        tenant_id="warehouse:fulya",
        source_entity_id="warehouse:fulya",
        relation_type="stocks",
        target_entity_id="sku:1",
        valid_from=NOW - timedelta(days=1),
        evidence_ref="catalog://fulya",
    )
    snapshot = build_world_snapshot(
        tenant_id="warehouse:fulya",
        as_of=NOW,
        entities=[warehouse, sku],
        assertions=[_assertion()],
        relations=[relation],
    )

    assert snapshot.relations == (relation,)
