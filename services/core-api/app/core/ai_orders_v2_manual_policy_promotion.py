"""Manual policy-promotion proposal for the blocked orders-v2 chain.

This module produces reviewable code-change evidence only. It binds the exact
human review, release gate, deployment authorization, current blocked policy and
intended orders-v2 target policy fields, while refusing to mutate the active
version-controlled registry or enable execution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_deployment_authorization import (
    OrdersV2DeploymentAuthorizationArtifact,
)
from app.core.ai_orders_v2_human_promotion_review import (
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    AiQueryContractPolicy,
    ai_query_contract_policy_fingerprint,
    expected_query_contract_review_fingerprint,
)

ORDERS_V2_POLICY_PROPOSAL_VERSION = 1
ORDERS_V2_TARGET_CONTRACT_REVISION = 2
ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER = "orders_v2_manual_code_change_required"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2ManualPolicyPromotionProposal(BaseModel):
    """Immutable proposal for a later human-reviewed version-controlled change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_manual_policy_promotion_proposal"]
    environment: Literal["production"]
    proposed_at: datetime
    proposal_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_promoter_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    human_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    release_gate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    deployment_authorization_fingerprint: str = Field(pattern=SHA256_PATTERN)
    current_policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    target_contract_id: Literal["ops.kpi.orders.v2"]
    target_contract_revision: Literal[2]
    target_data_scope_argument: Literal["stores"]
    target_tenant_discriminator_parameter: Literal["entity_ids"]
    target_query_template_sha256: str = Field(pattern=SHA256_PATTERN)
    target_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposal_decision: Literal["APPROVE_FOR_MANUAL_VERSION_CONTROL_CHANGE"]
    manual_version_control_change_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_manual_code_change_required"]

    @model_validator(mode="after")
    def validate_target_contract(self) -> OrdersV2ManualPolicyPromotionProposal:
        if self.proposed_at.tzinfo is None or self.proposed_at.utcoffset() is None:
            raise ValueError("policy proposal timestamp must be timezone-aware")
        if self.target_query_template_sha256 != ORDERS_V2_CANDIDATE.template_fingerprint:
            raise ValueError("target query template fingerprint mismatch")
        expected = _target_policy_review_fingerprint()
        if self.target_review_fingerprint != expected:
            raise ValueError("target review fingerprint mismatch")
        current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
        if self.current_policy_fingerprint != ai_query_contract_policy_fingerprint(current):
            raise ValueError("current policy fingerprint mismatch")
        return self

    @property
    def proposal_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _target_policy_review_fingerprint() -> str:
    candidate = AiQueryContractPolicy(
        tool="ops_kpi_query",
        contract_id=ORDERS_V2_CANDIDATE.query_id,
        contract_revision=ORDERS_V2_TARGET_CONTRACT_REVISION,
        data_scope_argument="stores",
        tenant_discriminator_parameter="entity_ids",
        query_template_sha256=ORDERS_V2_CANDIDATE.template_fingerprint,
        review_fingerprint=None,
        production_ready=False,
        blockers=("proposal_only",),
    )
    return expected_query_contract_review_fingerprint(candidate)


def build_orders_v2_manual_policy_promotion_proposal(
    *,
    human_review: OrdersV2HumanPromotionReviewArtifact,
    release_gate: OrdersV2ReleaseGateArtifact,
    deployment_authorization: OrdersV2DeploymentAuthorizationArtifact,
    policy_promoter_identity: str,
    proposal_manifest: str,
    proposed_at: datetime,
) -> OrdersV2ManualPolicyPromotionProposal:
    """Bind four-party approval evidence without changing the active policy."""

    if proposed_at.tzinfo is None or proposed_at.utcoffset() is None:
        raise ValueError("policy proposal timestamp must be timezone-aware")
    if deployment_authorization.environment != "production":
        raise ValueError("policy promotion proposal requires production authorization")
    if deployment_authorization.deployment_authorization_completed is not True:
        raise ValueError("deployment authorization is incomplete")
    if deployment_authorization.manual_policy_promotion_required is not True:
        raise ValueError("deployment authorization promotion state is invalid")
    if deployment_authorization.policy_mutation_permitted is not False:
        raise ValueError("deployment authorization policy mutation state is invalid")
    if deployment_authorization.execution_enable_permitted is not False:
        raise ValueError("deployment authorization execution state is invalid")
    if deployment_authorization.promotion_eligible is not False:
        raise ValueError("deployment authorization promotion eligibility is invalid")
    if deployment_authorization.production_ready is not False:
        raise ValueError("deployment authorization production state is invalid")
    if release_gate.human_review_fingerprint != human_review.review_fingerprint:
        raise ValueError("release gate is not bound to human review")
    if deployment_authorization.human_review_fingerprint != human_review.review_fingerprint:
        raise ValueError("deployment authorization is not bound to human review")
    if deployment_authorization.release_gate_fingerprint != release_gate.release_gate_fingerprint:
        raise ValueError("deployment authorization is not bound to release gate")

    identities = {
        human_review.reviewer_identity_sha256,
        release_gate.release_approver_identity_sha256,
        deployment_authorization.deployment_approver_identity_sha256,
    }
    if len(identities) != 3:
        raise ValueError("human, release, and deployment approvers must be distinct")

    promoter_sha256 = sha256_text(policy_promoter_identity)
    if promoter_sha256 in identities:
        raise ValueError("policy promoter must be independent of prior approvers")

    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    if current.contract_id != "ops.kpi.orders.v1" or current.production_ready is not False:
        raise ValueError("current ops KPI policy state is not the reviewed blocked baseline")

    return OrdersV2ManualPolicyPromotionProposal(
        version=ORDERS_V2_POLICY_PROPOSAL_VERSION,
        kind="orders_v2_manual_policy_promotion_proposal",
        environment="production",
        proposed_at=proposed_at,
        proposal_manifest_sha256=sha256_text(proposal_manifest),
        policy_promoter_identity_sha256=promoter_sha256,
        human_review_fingerprint=human_review.review_fingerprint,
        release_gate_fingerprint=release_gate.release_gate_fingerprint,
        deployment_authorization_fingerprint=(
            deployment_authorization.deployment_authorization_fingerprint
        ),
        current_policy_fingerprint=ai_query_contract_policy_fingerprint(current),
        target_contract_id=ORDERS_V2_CANDIDATE.query_id,
        target_contract_revision=ORDERS_V2_TARGET_CONTRACT_REVISION,
        target_data_scope_argument="stores",
        target_tenant_discriminator_parameter="entity_ids",
        target_query_template_sha256=ORDERS_V2_CANDIDATE.template_fingerprint,
        target_review_fingerprint=_target_policy_review_fingerprint(),
        proposal_decision="APPROVE_FOR_MANUAL_VERSION_CONTROL_CHANGE",
        manual_version_control_change_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_MANUAL_CODE_CHANGE_BLOCKER,
    )
