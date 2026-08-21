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
    build_orders_v2_deployment_authorization,
)
from app.core.ai_orders_v2_human_promotion_review import (
    HUMAN_PROMOTION_RELEASE_BLOCKER,
    ORDERS_V2_DEPLOYMENT_BLOCKER,
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE


def _human_review(identity: str) -> OrdersV2HumanPromotionReviewArtifact:
    return OrdersV2HumanPromotionReviewArtifact(
        version=1,
        kind="orders_v2_human_promotion_review",
        reviewed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        reviewer_identity_sha256=sha256_text(identity),
        review_context_sha256=sha256_text("ticket=approval-separation"),
        schema_attestation_fingerprint="a" * 64,
        live_cross_tenant_evidence_fingerprint="b" * 64,
        candidate_template_fingerprint=ORDERS_V2_CANDIDATE.template_fingerprint,
        parameter_contract_fingerprint=(
            orders_v2_bigquery_parameter_contract_fingerprint()
        ),
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


def _release_gate(
    review: OrdersV2HumanPromotionReviewArtifact,
    identity: str,
) -> OrdersV2ReleaseGateArtifact:
    return OrdersV2ReleaseGateArtifact(
        version=1,
        kind="orders_v2_release_gate_artifact",
        released_at=datetime(2026, 8, 13, 9, 0, tzinfo=UTC),
        release_manifest_sha256=sha256_text("release-manifest"),
        release_approver_identity_sha256=sha256_text(identity),
        human_review_fingerprint=review.review_fingerprint,
        candidate_template_fingerprint=ORDERS_V2_CANDIDATE.template_fingerprint,
        parameter_contract_fingerprint=(
            orders_v2_bigquery_parameter_contract_fingerprint()
        ),
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


def test_deployment_rejects_same_human_and_release_approver() -> None:
    shared_identity = "shared-reviewer@example.invalid"
    review = _human_review(shared_identity)
    gate = _release_gate(review, shared_identity)

    with pytest.raises(ValueError, match="release approver must differ"):
        build_orders_v2_deployment_authorization(
            human_review=review,
            release_gate=gate,
            environment="production",
            deployment_manifest="deployment-manifest",
            deployment_approver_identity="deploy@example.invalid",
            authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
        )


def test_deployment_accepts_three_distinct_approval_identities() -> None:
    review = _human_review("human@example.invalid")
    gate = _release_gate(review, "release@example.invalid")

    artifact = build_orders_v2_deployment_authorization(
        human_review=review,
        release_gate=gate,
        environment="production",
        deployment_manifest="deployment-manifest",
        deployment_approver_identity="deploy@example.invalid",
        authorized_at=datetime(2026, 8, 13, 10, 0, tzinfo=UTC),
    )

    identities = {
        review.reviewer_identity_sha256,
        gate.release_approver_identity_sha256,
        artifact.deployment_approver_identity_sha256,
    }
    assert len(identities) == 3
    assert artifact.policy_mutation_permitted is False
    assert artifact.execution_enable_permitted is False
