import pytest

from app.kpi_putaway_contracts import PutawayActivationBundle
from app.kpi_putaway_production_activation import seal_putaway_production_activation


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64
FP_E = "e" * 64


def activation(**overrides):
    payload = {
        "metric": "putaway",
        "semantic_fingerprint": FP_A,
        "schema_fingerprint": FP_B,
        "schema_evidence_fingerprint": FP_C,
        "sla_contract_fingerprint": FP_D,
        "quantity_contract_fingerprint": FP_E,
    }
    payload.update(overrides)
    return PutawayActivationBundle(**payload)


def source_mapping(**overrides):
    payload = {
        "verified": True,
        "metric": "putaway",
        "schema_evidence_fingerprint": FP_C,
        "mapping_fingerprint": "f" * 64,
        "role_to_column": {
            "date": "event_date",
            "city": "city_name",
            "inbound_kind": "inbound_type",
            "elapsed_minutes": "elapsed_min",
            "initial_qty": "qty_initial",
            "on_shelf_qty": "qty_shelf",
        },
        "role_types": {
            "date": "DATE",
            "city": "STRING",
            "inbound_kind": "STRING",
            "elapsed_minutes": "NUMERIC",
            "initial_qty": "INT64",
            "on_shelf_qty": "INT64",
        },
    }
    payload.update(overrides)
    return payload


def test_putaway_production_activation_seals_all_review_lineage_and_stays_non_executable():
    artifact = seal_putaway_production_activation(
        activation=activation(),
        source_mapping_verification=source_mapping(),
        approval_reference="PUTAWAY-REVIEW-2026-001",
        reviewer="ops-metric-owner",
    )
    assert artifact.approved_for_registry_review is True
    assert artifact.executable is False
    assert artifact.schema_evidence_fingerprint == FP_C
    assert artifact.sla_contract_fingerprint == FP_D
    assert artifact.quantity_contract_fingerprint == FP_E
    assert len(artifact.fingerprint) == 64


def test_putaway_production_activation_rejects_stale_source_mapping_schema():
    with pytest.raises(ValueError, match="putaway_production_activation_schema_evidence_mismatch"):
        seal_putaway_production_activation(
            activation=activation(),
            source_mapping_verification=source_mapping(schema_evidence_fingerprint="9" * 64),
            approval_reference="PUTAWAY-REVIEW-2026-001",
            reviewer="ops-metric-owner",
        )


def test_putaway_production_activation_requires_verified_source_mapping():
    with pytest.raises(ValueError, match="putaway_production_activation_source_mapping_required"):
        seal_putaway_production_activation(
            activation=activation(),
            source_mapping_verification=source_mapping(verified=False),
            approval_reference="PUTAWAY-REVIEW-2026-001",
            reviewer="ops-metric-owner",
        )


def test_putaway_production_activation_requires_complete_source_roles():
    mapping = source_mapping()
    roles = dict(mapping["role_to_column"])
    roles.pop("inbound_kind")
    with pytest.raises(ValueError, match="putaway_production_activation_source_roles_incomplete"):
        seal_putaway_production_activation(
            activation=activation(),
            source_mapping_verification=source_mapping(role_to_column=roles),
            approval_reference="PUTAWAY-REVIEW-2026-001",
            reviewer="ops-metric-owner",
        )


def test_putaway_production_activation_requires_explicit_human_approval_reference():
    with pytest.raises(ValueError, match="putaway_production_activation_approval_reference_required"):
        seal_putaway_production_activation(
            activation=activation(),
            source_mapping_verification=source_mapping(),
            approval_reference=" ",
            reviewer="ops-metric-owner",
        )
