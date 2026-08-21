from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_live_cross_tenant_evidence import (
    LIVE_CROSS_TENANT_REVIEW_BLOCKER,
    OrdersV2LiveCrossTenantEvidence,
    build_orders_v2_live_cross_tenant_evidence_candidate,
)
from app.core.ai_orders_v2_live_schema_collector import (
    UNATTESTED_COLLECTOR_BLOCKER,
    OrdersV2CollectedSchemaObservation,
)
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
    build_orders_v2_schema_attestation_candidate,
)
from app.core.ai_orders_v2_schema_evidence import (
    build_orders_v2_information_schema_evidence,
)


def schema_attestation() -> OrdersV2SchemaAttestationArtifact:
    evidence = build_orders_v2_information_schema_evidence(
        row={
            "table_catalog": "example-project",
            "table_schema": "curated_data_shared_coredata_business",
            "table_name": "orders",
            "column_name": "entity",
            "field_path": "entity.id",
            "data_type": "STRING",
        },
        observed_at=datetime(2026, 8, 13, 6, 0, tzinfo=UTC),
    )
    observation = OrdersV2CollectedSchemaObservation(
        provenance_kind="collector_observation_unattested",
        evidence=evidence,
        client_project="example-project",
        client_location="EU",
        metadata_row_count=1,
        attested_live_run=False,
        production_blocker=UNATTESTED_COLLECTOR_BLOCKER,
    )
    return build_orders_v2_schema_attestation_candidate(observation)


def live_candidate() -> OrdersV2LiveCrossTenantEvidence:
    return build_orders_v2_live_cross_tenant_evidence_candidate(
        schema_attestation=schema_attestation(),
        executed_at=datetime(2026, 8, 13, 7, 0, tzinfo=UTC),
        query_job_id="job-example-123",
        authorized_scope_descriptor="entity=TENANT_A;store=Fulya",
        foreign_sentinel_scope_descriptor="entity=TENANT_B;store=Fulya",
        canonical_returned_rowset='[{"date":"2026-08-13","orders":2}]',
        foreign_sentinel_match_count=0,
    )


def test_live_evidence_is_bound_but_non_promoting() -> None:
    artifact = live_candidate()

    assert artifact.project == "example-project"
    assert artifact.location == "EU"
    assert artifact.live_bigquery_run_claimed is True
    assert artifact.cryptographically_attested is False
    assert artifact.promotion_eligible is False
    assert artifact.human_review_required is True
    assert artifact.foreign_sentinel_match_count == 0
    assert artifact.production_blocker == LIVE_CROSS_TENANT_REVIEW_BLOCKER
    assert len(artifact.schema_attestation_fingerprint) == 64
    assert len(artifact.evidence_fingerprint) == 64


def test_live_evidence_rejects_foreign_sentinel_leakage() -> None:
    with pytest.raises(ValueError, match="leakage"):
        build_orders_v2_live_cross_tenant_evidence_candidate(
            schema_attestation=schema_attestation(),
            executed_at=datetime(2026, 8, 13, 7, 0, tzinfo=UTC),
            query_job_id="job-example-123",
            authorized_scope_descriptor="entity=TENANT_A;store=Fulya",
            foreign_sentinel_scope_descriptor="entity=TENANT_B;store=Fulya",
            canonical_returned_rowset="[]",
            foreign_sentinel_match_count=1,
        )


def test_live_evidence_rejects_same_authorized_and_foreign_scope() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        build_orders_v2_live_cross_tenant_evidence_candidate(
            schema_attestation=schema_attestation(),
            executed_at=datetime(2026, 8, 13, 7, 0, tzinfo=UTC),
            query_job_id="job-example-123",
            authorized_scope_descriptor="entity=TENANT_A;store=Fulya",
            foreign_sentinel_scope_descriptor="entity=TENANT_A;store=Fulya",
            canonical_returned_rowset="[]",
            foreign_sentinel_match_count=0,
        )


def test_live_evidence_rejects_contract_and_promotion_tamper() -> None:
    artifact = live_candidate()

    for field, value in (
        ("candidate_template_fingerprint", "f" * 64),
        ("parameter_contract_fingerprint", "f" * 64),
        ("sdk_adapter_fingerprint", "f" * 64),
        ("promotion_eligible", True),
        ("cryptographically_attested", True),
        ("human_review_required", False),
        ("foreign_sentinel_match_count", 1),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2LiveCrossTenantEvidence.model_validate(payload)


def test_live_evidence_does_not_store_raw_scope_or_job_id() -> None:
    artifact = live_candidate()
    rendered = artifact.model_dump_json()

    assert "TENANT_A" not in rendered
    assert "TENANT_B" not in rendered
    assert "Fulya" not in rendered
    assert "job-example-123" not in rendered
