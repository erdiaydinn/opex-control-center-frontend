from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_parameter_contract_fingerprint,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    orders_v2_bigquery_sdk_adapter_fingerprint,
)
from app.core.ai_orders_v2_deployment_authorization import (
    ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER,
    OrdersV2DeploymentAuthorizationArtifact,
)
from app.core.ai_orders_v2_human_promotion_review import (
    HUMAN_PROMOTION_RELEASE_BLOCKER,
    ORDERS_V2_DEPLOYMENT_BLOCKER,
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_manual_policy_promotion import (
    ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    build_orders_v2_manual_policy_promotion_proposal,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


def _review(identity: str = "human@example.invalid") -> OrdersV2HumanPromotionReviewArtifact:
    return OrdersV2HumanPromotionReviewArtifact(
        version=1,
        kind="orders_v2_human_promotion_review",
        reviewed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        reviewer_identity_sha256=sha256_text(identity),
        review_context_sha256=sha256_text("review-context"),
        schema_attestation_fingerprint="a" * 64,
        live_cross_tenant_evidence_fingerprint="b" * 64,
        candidate_template_fingerprint=ORDERS_V2_CANDIDATE.template_fingerprint,
        parameter_contract_fingerprint=orders_v2_bigquery_parameter_contract_fingerprint(),
        sdk_adapter_fingerprint=orders_v2_bigquery_sdk_adapter_fingerprint(),
        review_decision="APPROVE_FOR_RELEASE_GATE",
        human_review_completed=True,
        release_gate_candidate=True,
        release_gate_required=True,
        policy_mutation_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=HUMAN_PROMOTION_RELEASE_BLOCKER,
    )


def _release(
    review: OrdersV2HumanPromotionReviewArtifact,
    identity: str = "release@example.invalid",
) -> OrdersV2ReleaseGateArtifact:
    return OrdersV2ReleaseGateArtifact(
        version=1,
        kind="orders_v2_release_gate_artifact",
        released_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        release_manifest_sha256=sha256_text("release-manifest"),
        release_approver_identity_sha256=sha256_text(identity),
        human_review_fingerprint=review.review_fingerprint,
        candidate_template_fingerprint=ORDERS_V2_CANDIDATE.template_fingerprint,
        parameter_contract_fingerprint=orders_v2_bigquery_parameter_contract_fingerprint(),
        sdk_adapter_fingerprint=orders_v2_bigquery_sdk_adapter_fingerprint(),
        release_decision="APPROVE_FOR_DEPLOYMENT_GATE",
        release_gate_completed=True,
        deployment_gate_candidate=True,
        deployment_gate_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_DEPLOYMENT_BLOCKER,
    )


def _deployment(
    review: OrdersV2HumanPromotionReviewArtifact,
    release: OrdersV2ReleaseGateArtifact,
    *,
    environment: str = "production",
    identity: str = "deploy@example.invalid",
) -> OrdersV2DeploymentAuthorizationArtifact:
    return OrdersV2DeploymentAuthorizationArtifact(
        version=1,
        kind="orders_v2_deployment_authorization",
        environment=environment,
        authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        deployment_manifest_sha256=sha256_text("deployment-manifest"),
        deployment_approver_identity_sha256=sha256_text(identity),
        release_gate_fingerprint=release.release_gate_fingerprint,
        human_review_fingerprint=review.review_fingerprint,
        candidate_template_fingerprint=ORDERS_V2_CANDIDATE.template_fingerprint,
        parameter_contract_fingerprint=orders_v2_bigquery_parameter_contract_fingerprint(),
        sdk_adapter_fingerprint=orders_v2_bigquery_sdk_adapter_fingerprint(),
        authorization_decision="APPROVE_FOR_MANUAL_POLICY_PROMOTION",
        deployment_authorization_completed=True,
        manual_policy_promotion_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER,
    )


def test_policy_proposal_is_bound_and_cannot_mutate_active_policy() -> None:
    review = _review()
    release = _release(review)
    deployment = _deployment(review, release)

    artifact = build_orders_v2_manual_policy_promotion_proposal(
        human_review=review,
        release_gate=release,
        deployment_authorization=deployment,
        policy_promoter_identity="policy@example.invalid",
        proposal_manifest="manual policy proposal revision 1",
        proposed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    )

    assert artifact.target_contract_id == "ops.kpi.orders.v2"
    assert artifact.target_contract_revision == 2
    assert artifact.target_data_scope_argument == "stores"
    assert artifact.target_tenant_discriminator_parameter == "entity_ids"
    assert artifact.target_query_template_sha256 == ORDERS_V2_CANDIDATE.template_fingerprint
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert artifact.production_blocker == ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER
    assert len(artifact.proposal_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


def test_policy_proposal_requires_four_distinct_approvers() -> None:
    review = _review()
    release = _release(review)
    deployment = _deployment(review, release)

    for identity in (
        "human@example.invalid",
        "release@example.invalid",
        "deploy@example.invalid",
    ):
        with pytest.raises(ValueError, match="policy promoter must be independent"):
            build_orders_v2_manual_policy_promotion_proposal(
                human_review=review,
                release_gate=release,
                deployment_authorization=deployment,
                policy_promoter_identity=identity,
                proposal_manifest="manual policy proposal revision 1",
                proposed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
            )


def test_policy_proposal_rejects_prior_approval_role_collision() -> None:
    review = _review("shared@example.invalid")
    release = _release(review, "shared@example.invalid")
    deployment = _deployment(review, release)

    with pytest.raises(ValueError, match="must be distinct"):
        build_orders_v2_manual_policy_promotion_proposal(
            human_review=review,
            release_gate=release,
            deployment_authorization=deployment,
            policy_promoter_identity="policy@example.invalid",
            proposal_manifest="manual policy proposal revision 1",
            proposed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
        )


def test_policy_proposal_requires_production_deployment_authorization() -> None:
    review = _review()
    release = _release(review)
    deployment = _deployment(review, release, environment="staging")

    with pytest.raises(ValueError, match="production authorization"):
        build_orders_v2_manual_policy_promotion_proposal(
            human_review=review,
            release_gate=release,
            deployment_authorization=deployment,
            policy_promoter_identity="policy@example.invalid",
            proposal_manifest="manual policy proposal revision 1",
            proposed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
        )


def test_policy_proposal_does_not_store_raw_approver_or_manifest() -> None:
    review = _review()
    release = _release(review)
    deployment = _deployment(review, release)

    artifact = build_orders_v2_manual_policy_promotion_proposal(
        human_review=review,
        release_gate=release,
        deployment_authorization=deployment,
        policy_promoter_identity="policy@example.invalid",
        proposal_manifest="manual policy proposal revision 1",
        proposed_at=datetime(2026, 8, 13, 11, 0, tzinfo=UTC),
    )
    rendered = artifact.model_dump_json()

    assert "policy@example.invalid" not in rendered
    assert "manual policy proposal revision 1" not in rendered
