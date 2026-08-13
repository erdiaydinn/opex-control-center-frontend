from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_human_promotion_review import (
    HUMAN_PROMOTION_RELEASE_BLOCKER,
    OrdersV2HumanPromotionReviewArtifact,
    build_orders_v2_human_promotion_review,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import (
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
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


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


def live_evidence(
    attestation: OrdersV2SchemaAttestationArtifact,
) -> OrdersV2LiveCrossTenantEvidence:
    return build_orders_v2_live_cross_tenant_evidence_candidate(
        schema_attestation=attestation,
        executed_at=datetime(2026, 8, 13, 7, 0, tzinfo=UTC),
        query_job_id="job-example-123",
        authorized_scope_descriptor="entity=TENANT_A;store=Fulya",
        foreign_sentinel_scope_descriptor="entity=TENANT_B;store=Fulya",
        canonical_returned_rowset='[{"date":"2026-08-13","orders":2}]',
        foreign_sentinel_match_count=0,
    )


def human_review() -> OrdersV2HumanPromotionReviewArtifact:
    attestation = schema_attestation()
    return build_orders_v2_human_promotion_review(
        schema_attestation=attestation,
        live_evidence=live_evidence(attestation),
        reviewer_identity="reviewer@example.invalid",
        review_context="ticket=EAY-ORDERS-V2-REVIEW-001",
        reviewed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
    )


def test_human_review_is_release_gate_candidate_but_never_promotes() -> None:
    artifact = human_review()

    assert artifact.review_decision == "APPROVE_FOR_RELEASE_GATE"
    assert artifact.human_review_completed is True
    assert artifact.release_gate_candidate is True
    assert artifact.release_gate_required is True
    assert artifact.policy_mutation_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == HUMAN_PROMOTION_RELEASE_BLOCKER
    assert len(artifact.reviewer_identity_sha256) == 64
    assert len(artifact.review_context_sha256) == 64
    assert len(artifact.review_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


def test_human_review_rejects_evidence_from_different_attestation() -> None:
    attestation = schema_attestation()
    other_attestation = schema_attestation()
    other_payload = other_attestation.model_dump(mode="python")
    other_payload["collector_observation_fingerprint"] = "f" * 64

    with pytest.raises(ValidationError):
        OrdersV2SchemaAttestationArtifact.model_validate(other_payload)

    evidence = live_evidence(attestation)
    evidence_payload = evidence.model_dump(mode="python")
    evidence_payload["schema_attestation_fingerprint"] = "f" * 64
    foreign_evidence = OrdersV2LiveCrossTenantEvidence.model_construct(
        **evidence_payload
    )

    with pytest.raises(ValueError, match="not bound"):
        build_orders_v2_human_promotion_review(
            schema_attestation=attestation,
            live_evidence=foreign_evidence,
            reviewer_identity="reviewer@example.invalid",
            review_context="ticket=EAY-ORDERS-V2-REVIEW-001",
            reviewed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        )


def test_human_review_rejects_naive_timestamp_and_empty_identity() -> None:
    attestation = schema_attestation()
    evidence = live_evidence(attestation)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_orders_v2_human_promotion_review(
            schema_attestation=attestation,
            live_evidence=evidence,
            reviewer_identity="reviewer@example.invalid",
            review_context="ticket=EAY-ORDERS-V2-REVIEW-001",
            reviewed_at=datetime(2026, 8, 13, 8, 0),
        )

    with pytest.raises(ValueError, match="non-empty"):
        build_orders_v2_human_promotion_review(
            schema_attestation=attestation,
            live_evidence=evidence,
            reviewer_identity="",
            review_context="ticket=EAY-ORDERS-V2-REVIEW-001",
            reviewed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        )


def test_human_review_rejects_release_and_policy_tamper() -> None:
    artifact = human_review()

    for field, value in (
        ("candidate_template_fingerprint", "f" * 64),
        ("parameter_contract_fingerprint", "f" * 64),
        ("sdk_adapter_fingerprint", "f" * 64),
        ("review_decision", "REJECT"),
        ("release_gate_candidate", False),
        ("release_gate_required", False),
        ("policy_mutation_permitted", True),
        ("promotion_eligible", True),
        ("production_ready", True),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2HumanPromotionReviewArtifact.model_validate(payload)


def test_human_review_does_not_store_raw_reviewer_or_review_context() -> None:
    artifact = human_review()
    rendered = artifact.model_dump_json()

    assert "reviewer@example.invalid" not in rendered
    assert "EAY-ORDERS-V2-REVIEW-001" not in rendered
