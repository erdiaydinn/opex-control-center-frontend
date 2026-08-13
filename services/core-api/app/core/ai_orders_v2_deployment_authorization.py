"""Environment-bound deployment authorization for the blocked orders-v2 chain.

This artifact is the final evidence hand-off before a separate, explicit policy
promotion change. It binds an independent deployment approver to the exact human
review and release-gate fingerprints for one environment. It does not mutate the
active query policy, enable execution, or mark orders-v2 production ready.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_parameter_contract_fingerprint,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    orders_v2_bigquery_sdk_adapter_fingerprint,
)
from app.core.ai_orders_v2_human_promotion_review import (
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE

ORDERS_V2_DEPLOYMENT_AUTHORIZATION_VERSION = 1
ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER = (
    "orders_v2_manual_policy_promotion_required"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2DeploymentAuthorizationArtifact(BaseModel):
    """Immutable authorization to enter a manual policy-promotion review only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_deployment_authorization"]
    environment: Literal["staging", "production"]
    authorized_at: datetime
    deployment_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    deployment_approver_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    release_gate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    human_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    authorization_decision: Literal["APPROVE_FOR_MANUAL_POLICY_PROMOTION"]
    deployment_authorization_completed: Literal[True]
    manual_policy_promotion_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal[
        "orders_v2_manual_policy_promotion_required"
    ]

    @model_validator(mode="after")
    def validate_deployment_bindings(self) -> OrdersV2DeploymentAuthorizationArtifact:
        if self.authorized_at.tzinfo is None or self.authorized_at.utcoffset() is None:
            raise ValueError("deployment authorization timestamp must be timezone-aware")
        if (
            self.candidate_template_fingerprint
            != ORDERS_V2_CANDIDATE.template_fingerprint
        ):
            raise ValueError("candidate template fingerprint mismatch")
        if (
            self.parameter_contract_fingerprint
            != orders_v2_bigquery_parameter_contract_fingerprint()
        ):
            raise ValueError("parameter contract fingerprint mismatch")
        if (
            self.sdk_adapter_fingerprint
            != orders_v2_bigquery_sdk_adapter_fingerprint()
        ):
            raise ValueError("SDK adapter fingerprint mismatch")
        return self

    @property
    def deployment_authorization_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_deployment_authorization(
    *,
    human_review: OrdersV2HumanPromotionReviewArtifact,
    release_gate: OrdersV2ReleaseGateArtifact,
    environment: str,
    deployment_manifest: str,
    deployment_approver_identity: str,
    authorized_at: datetime,
) -> OrdersV2DeploymentAuthorizationArtifact:
    """Bind three independent approvals without changing runtime policy."""

    if environment not in {"staging", "production"}:
        raise ValueError("deployment environment is invalid")
    if authorized_at.tzinfo is None or authorized_at.utcoffset() is None:
        raise ValueError("deployment authorization timestamp must be timezone-aware")
    if human_review.human_review_completed is not True:
        raise ValueError("human review is incomplete")
    if human_review.release_gate_candidate is not True:
        raise ValueError("human review is not a release-gate candidate")
    if release_gate.release_gate_completed is not True:
        raise ValueError("release gate is incomplete")
    if release_gate.deployment_gate_candidate is not True:
        raise ValueError("release gate is not a deployment-gate candidate")
    if release_gate.deployment_gate_required is not True:
        raise ValueError("release gate deployment state is invalid")
    if release_gate.policy_mutation_permitted is not False:
        raise ValueError("release gate policy mutation state is invalid")
    if release_gate.execution_enable_permitted is not False:
        raise ValueError("release gate execution state is invalid")
    if release_gate.promotion_eligible is not False:
        raise ValueError("release gate promotion state is invalid")
    if release_gate.production_ready is not False:
        raise ValueError("release gate production state is invalid")
    if release_gate.human_review_fingerprint != human_review.review_fingerprint:
        raise ValueError("release gate is not bound to human review")
    if (
        release_gate.release_approver_identity_sha256
        == human_review.reviewer_identity_sha256
    ):
        raise ValueError("release approver must differ from human reviewer")

    expected_template = ORDERS_V2_CANDIDATE.template_fingerprint
    expected_parameters = orders_v2_bigquery_parameter_contract_fingerprint()
    expected_sdk = orders_v2_bigquery_sdk_adapter_fingerprint()
    for artifact_name, template, parameters, sdk in (
        (
            "human review",
            human_review.candidate_template_fingerprint,
            human_review.parameter_contract_fingerprint,
            human_review.sdk_adapter_fingerprint,
        ),
        (
            "release gate",
            release_gate.candidate_template_fingerprint,
            release_gate.parameter_contract_fingerprint,
            release_gate.sdk_adapter_fingerprint,
        ),
    ):
        if template != expected_template:
            raise ValueError(f"{artifact_name} template fingerprint mismatch")
        if parameters != expected_parameters:
            raise ValueError(f"{artifact_name} parameter fingerprint mismatch")
        if sdk != expected_sdk:
            raise ValueError(f"{artifact_name} SDK fingerprint mismatch")

    deployment_approver_sha256 = sha256_text(deployment_approver_identity)
    if deployment_approver_sha256 == human_review.reviewer_identity_sha256:
        raise ValueError("deployment approver must differ from human reviewer")
    if deployment_approver_sha256 == release_gate.release_approver_identity_sha256:
        raise ValueError("deployment approver must differ from release approver")

    return OrdersV2DeploymentAuthorizationArtifact(
        version=ORDERS_V2_DEPLOYMENT_AUTHORIZATION_VERSION,
        kind="orders_v2_deployment_authorization",
        environment=environment,
        authorized_at=authorized_at,
        deployment_manifest_sha256=sha256_text(deployment_manifest),
        deployment_approver_identity_sha256=deployment_approver_sha256,
        release_gate_fingerprint=release_gate.release_gate_fingerprint,
        human_review_fingerprint=human_review.review_fingerprint,
        candidate_template_fingerprint=expected_template,
        parameter_contract_fingerprint=expected_parameters,
        sdk_adapter_fingerprint=expected_sdk,
        authorization_decision="APPROVE_FOR_MANUAL_POLICY_PROMOTION",
        deployment_authorization_completed=True,
        manual_policy_promotion_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_MANUAL_POLICY_PROMOTION_BLOCKER,
    )
