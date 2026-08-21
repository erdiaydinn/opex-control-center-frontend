from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_synthetic_proof import (
    SYNTHETIC_PROOF_BLOCKER,
    OrdersV2SyntheticProofArtifact,
    aggregate_orders_v2_synthetic_scope,
    evaluate_orders_v2_synthetic_scope,
    run_orders_v2_synthetic_cross_tenant_proof,
    synthetic_orders_v2_fixture,
)
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


def test_synthetic_matrix_proves_expected_scope_separation() -> None:
    artifact = run_orders_v2_synthetic_cross_tenant_proof()

    assert artifact.proof_kind == "synthetic_semantics_only"
    assert artifact.case_count == 5
    assert artifact.passed_case_ids == (
        "tenant_a_fulya",
        "tenant_b_fulya",
        "tenant_a_dicle",
        "explicit_multi_tenant_fulya",
        "date_exclusion",
    )
    assert artifact.live_bigquery_verified is False
    assert artifact.production_blocker == SYNTHETIC_PROOF_BLOCKER
    assert len(artifact.fixture_fingerprint) == 64
    assert len(artifact.proof_fingerprint) == 64
    assert artifact.candidate_template_fingerprint == (
        ORDERS_V2_CANDIDATE.template_fingerprint
    )


def test_synthetic_proof_cannot_be_relabelled_as_live_bigquery_evidence() -> None:
    artifact = run_orders_v2_synthetic_cross_tenant_proof()
    payload = artifact.model_dump(mode="python")
    payload["live_bigquery_verified"] = True

    with pytest.raises(ValidationError):
        OrdersV2SyntheticProofArtifact.model_validate(payload)

    payload = artifact.model_dump(mode="python")
    payload["production_blocker"] = ""
    with pytest.raises(ValidationError):
        OrdersV2SyntheticProofArtifact.model_validate(payload)

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False
    assert ORDERS_V2_CANDIDATE.cross_tenant_proof_fingerprint is None


def test_same_store_other_tenant_never_leaks() -> None:
    selected = evaluate_orders_v2_synthetic_scope(
        synthetic_orders_v2_fixture(),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 12),
        entity_ids=("TENANT_A",),
        stores=("Fulya",),
    )

    assert selected == ("A-F-1", "A-F-2")
    assert "B-F-1" not in selected
    assert "A-D-1" not in selected
    assert "A-F-OLD" not in selected
    assert "A-f-lower" not in selected


def test_scope_only_expands_when_entity_is_explicitly_authorized() -> None:
    rows = synthetic_orders_v2_fixture()

    tenant_a = evaluate_orders_v2_synthetic_scope(
        rows,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 12),
        entity_ids=("TENANT_A",),
        stores=("Fulya",),
    )
    explicit_a_b = evaluate_orders_v2_synthetic_scope(
        rows,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 12),
        entity_ids=("TENANT_A", "TENANT_B"),
        stores=("Fulya",),
    )

    assert tenant_a == ("A-F-1", "A-F-2")
    assert explicit_a_b == ("A-F-1", "A-F-2", "B-F-1")


def test_synthetic_aggregation_mirrors_distinct_order_semantics() -> None:
    aggregated = aggregate_orders_v2_synthetic_scope(
        synthetic_orders_v2_fixture(),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 12),
        entity_ids=("TENANT_A",),
        stores=("Fulya",),
    )

    assert aggregated == (
        (date(2026, 8, 10), "Fulya", 2),
    )


def test_runtime_scope_bypass_values_are_still_rejected() -> None:
    rows = synthetic_orders_v2_fixture()

    for entities, stores in (
        ((), ("Fulya",)),
        (("TENANT_A",), ()),
        (("*",), ("Fulya",)),
        (("TENANT_A",), ("*",)),
        (("TENANT_A", "tenant_a"), ("Fulya",)),
    ):
        with pytest.raises(ValueError):
            evaluate_orders_v2_synthetic_scope(
                rows,
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 12),
                entity_ids=entities,
                stores=stores,
            )
