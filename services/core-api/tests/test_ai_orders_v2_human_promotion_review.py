from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_deployment_authorization import (
    ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER,
    OrdersV2DeploymentAuthorizationArtifact,
    build_orders_v2_deployment_authorization,
)
from app.core.ai_orders_v2_human_promotion_review import (
    HUMAN_PROMOTION_RELEASE_BLOCKER,
    ORDERS_V2_DEPLOYMENT_BLOCKER,
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
    build_orders_v2_human_promotion_review,
    build_orders_v2_release_gate_artifact,
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


def release_gate(
    review: OrdersV2HumanPromotionReviewArtifact | None = None,
) -> OrdersV2ReleaseGateArtifact:
    resolved_review = human_review() if review is None else review
    return build_orders_v2_release_gate_artifact(
        human_review=resolved_review,
        release_manifest="orders-v2 release manifest revision 1",
        release_approver_identity="release-approver@example.invalid",
        released_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
    )


def deployment_authorization(
    environment: str = "production",
) -> OrdersV2DeploymentAuthorizationArtifact:
    review = human_review()
    return build_orders_v2_deployment_authorization(
        human_review=review,
        release_gate=release_gate(review),
        environment=environment,
        deployment_manifest="orders-v2 deployment manifest revision 1",
        deployment_approver_identity="deployment-approver@example.invalid",
        authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
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


def test_release_gate_is_deployment_candidate_but_never_deploys() -> None:
    artifact = release_gate()

    assert artifact.release_decision == "APPROVE_FOR_DEPLOYMENT_GATE"
    assert artifact.release_gate_completed is True
    assert artifact.deployment_gate_candidate is True
    assert artifact.deployment_gate_required is True
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == ORDERS_V2_DEPLOYMENT_BLOCKER
    assert len(artifact.release_manifest_sha256) == 64
    assert len(artifact.release_approver_identity_sha256) == 64
    assert len(artifact.human_review_fingerprint) == 64
    assert len(artifact.release_gate_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


def test_release_gate_rejects_naive_timestamp_and_empty_review_inputs() -> None:
    review = human_review()

    with pytest.raises(ValueError, match="timezone-aware"):
        build_orders_v2_release_gate_artifact(
            human_review=review,
            release_manifest="orders-v2 release manifest revision 1",
            release_approver_identity="release-approver@example.invalid",
            released_at=datetime(2026, 8, 13, 9, 0),
        )

    for manifest, approver in (
        ("", "release-approver@example.invalid"),
        ("orders-v2 release manifest revision 1", ""),
    ):
        with pytest.raises(ValueError, match="non-empty"):
            build_orders_v2_release_gate_artifact(
                human_review=review,
                release_manifest=manifest,
                release_approver_identity=approver,
                released_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
            )


def test_release_gate_rejects_contract_and_deployment_tamper() -> None:
    artifact = release_gate()

    for field, value in (
        ("candidate_template_fingerprint", "f" * 64),
        ("parameter_contract_fingerprint", "f" * 64),
        ("sdk_adapter_fingerprint", "f" * 64),
        ("release_decision", "REJECT"),
        ("release_gate_completed", False),
        ("deployment_gate_candidate", False),
        ("deployment_gate_required", False),
        ("policy_mutation_permitted", True),
        ("execution_enable_permitted", True),
        ("promotion_eligible", True),
        ("production_ready", True),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2ReleaseGateArtifact.model_validate(payload)


def test_release_gate_does_not_store_raw_manifest_or_approver() -> None:
    artifact = release_gate()
    rendered = artifact.model_dump_json()

    assert "orders-v2 release manifest revision 1" not in rendered
    assert "release-approver@example.invalid" not in rendered


def test_deployment_authorization_is_environment_bound_and_non_executing() -> None:
    artifact = deployment_authorization()

    assert artifact.environment == "production"
    assert artifact.authorization_decision == "APPROVE_FOR_MANUAL_POLICY_PROMOTION"
    assert artifact.deployment_authorization_completed is True
    assert artifact.manual_policy_promotion_required is True
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER
    assert len(artifact.release_gate_fingerprint) == 64
    assert len(artifact.human_review_fingerprint) == 64
    assert len(artifact.deployment_authorization_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


def test_deployment_authorization_rejects_non_release_environments() -> None:
    for environment in ("development", "test", "prod", ""):
        review = human_review()
        with pytest.raises(ValueError, match="environment"):
            build_orders_v2_deployment_authorization(
                human_review=review,
                release_gate=release_gate(review),
                environment=environment,
                deployment_manifest="orders-v2 deployment manifest revision 1",
                deployment_approver_identity="deployment-approver@example.invalid",
                authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
            )

    assert deployment_authorization("staging").environment == "staging"


def test_deployment_authorization_requires_separation_of_duties() -> None:
    review = human_review()
    gate = release_gate(review)

    for approver, expected in (
        ("reviewer@example.invalid", "human reviewer"),
        ("release-approver@example.invalid", "release approver"),
    ):
        with pytest.raises(ValueError, match=expected):
            build_orders_v2_deployment_authorization(
                human_review=review,
                release_gate=gate,
                environment="production",
                deployment_manifest="orders-v2 deployment manifest revision 1",
                deployment_approver_identity=approver,
                authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
            )


def test_deployment_authorization_rejects_release_review_substitution() -> None:
    review = human_review()
    gate = release_gate(review)
    payload = gate.model_dump(mode="python")
    payload["human_review_fingerprint"] = "f" * 64
    foreign_gate = OrdersV2ReleaseGateArtifact.model_construct(**payload)

    with pytest.raises(ValueError, match="not bound"):
        build_orders_v2_deployment_authorization(
            human_review=review,
            release_gate=foreign_gate,
            environment="production",
            deployment_manifest="orders-v2 deployment manifest revision 1",
            deployment_approver_identity="deployment-approver@example.invalid",
            authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        )


def test_deployment_authorization_rejects_timestamp_and_empty_inputs() -> None:
    review = human_review()
    gate = release_gate(review)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_orders_v2_deployment_authorization(
            human_review=review,
            release_gate=gate,
            environment="production",
            deployment_manifest="orders-v2 deployment manifest revision 1",
            deployment_approver_identity="deployment-approver@example.invalid",
            authorized_at=datetime(2026, 8, 13, 10, 0),
        )

    for manifest, approver in (
        ("", "deployment-approver@example.invalid"),
        ("orders-v2 deployment manifest revision 1", ""),
    ):
        with pytest.raises(ValueError, match="non-empty"):
            build_orders_v2_deployment_authorization(
                human_review=review,
                release_gate=gate,
                environment="production",
                deployment_manifest=manifest,
                deployment_approver_identity=approver,
                authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
            )


def test_deployment_authorization_rejects_policy_and_execution_tamper() -> None:
    artifact = deployment_authorization()

    for field, value in (
        ("candidate_template_fingerprint", "f" * 64),
        ("parameter_contract_fingerprint", "f" * 64),
        ("sdk_adapter_fingerprint", "f" * 64),
        ("environment", "development"),
        ("authorization_decision", "DEPLOY_NOW"),
        ("deployment_authorization_completed", False),
        ("manual_policy_promotion_required", False),
        ("policy_mutation_permitted", True),
        ("execution_enable_permitted", True),
        ("promotion_eligible", True),
        ("production_ready", True),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2DeploymentAuthorizationArtifact.model_validate(payload)


def test_deployment_authorization_hides_raw_manifest_and_approver() -> None:
    artifact = deployment_authorization()
    rendered = artifact.model_dump_json()

    assert "orders-v2 deployment manifest revision 1" not in rendered
    assert "deployment-approver@example.invalid" not in rendered
    assert "reviewer@example.invalid" not in rendered
    assert "release-approver@example.invalid" not in rendered
