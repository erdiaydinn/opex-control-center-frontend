"""Human review and release-gate artifacts for the blocked orders-v2 chain.

Human review can only nominate an exact evidence set for a later release gate.
The release gate can only nominate that reviewed set for an explicit deployment
gate. Neither artifact can mutate the active query policy, enable execution, or
mark orders-v2 production ready.
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
from app.core.ai_orders_v2_live_cross_tenant_evidence import (
    OrdersV2LiveCrossTenantEvidence,
    sha256_text,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
)

HUMAN_PROMOTION_REVIEW_VERSION = 1
HUMAN_PROMOTION_RELEASE_BLOCKER = "orders_v2_release_gate_required"
ORDERS_V2_RELEASE_GATE_VERSION = 1
ORDERS_V2_DEPLOYMENT_BLOCKER = "orders_v2_explicit_deployment_gate_required"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2HumanPromotionReviewArtifact(BaseModel):
    """Immutable proof that exact evidence was human-reviewed, not promoted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_human_promotion_review"]
    reviewed_at: datetime
    reviewer_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    review_context_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_attestation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    live_cross_tenant_evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    review_decision: Literal["APPROVE_FOR_RELEASE_GATE"]
    human_review_completed: Literal[True]
    release_gate_candidate: Literal[True]
    release_gate_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_release_gate_required"]

    @model_validator(mode="after")
    def validate_review_bindings(self) -> OrdersV2HumanPromotionReviewArtifact:
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("review timestamp must be timezone-aware")
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
    def review_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class OrdersV2ReleaseGateArtifact(BaseModel):
    """Immutable release decision that still cannot deploy or mutate policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_release_gate_artifact"]
    released_at: datetime
    release_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    release_approver_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    human_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    release_decision: Literal["APPROVE_FOR_DEPLOYMENT_GATE"]
    release_gate_completed: Literal[True]
    deployment_gate_candidate: Literal[True]
    deployment_gate_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_explicit_deployment_gate_required"]

    @model_validator(mode="after")
    def validate_release_bindings(self) -> OrdersV2ReleaseGateArtifact:
        if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
            raise ValueError("release timestamp must be timezone-aware")
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
    def release_gate_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_human_promotion_review(
    *,
    schema_attestation: OrdersV2SchemaAttestationArtifact,
    live_evidence: OrdersV2LiveCrossTenantEvidence,
    reviewer_identity: str,
    review_context: str,
    reviewed_at: datetime,
) -> OrdersV2HumanPromotionReviewArtifact:
    """Bind one explicit human approval to exact immutable evidence artifacts."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("review timestamp must be timezone-aware")
    if schema_attestation.promotion_eligible is not False:
        raise ValueError("schema attestation promotion state is invalid")
    if schema_attestation.human_review_required is not True:
        raise ValueError("schema attestation review state is invalid")
    if live_evidence.promotion_eligible is not False:
        raise ValueError("live evidence promotion state is invalid")
    if live_evidence.human_review_required is not True:
        raise ValueError("live evidence review state is invalid")
    if live_evidence.foreign_sentinel_match_count != 0:
        raise ValueError("live evidence contains foreign sentinel leakage")
    if (
        live_evidence.schema_attestation_fingerprint
        != schema_attestation.artifact_fingerprint
    ):
        raise ValueError("live evidence is not bound to schema attestation")
    if live_evidence.project != schema_attestation.project:
        raise ValueError("project binding mismatch")
    if live_evidence.location != schema_attestation.location:
        raise ValueError("location binding mismatch")

    expected_template = ORDERS_V2_CANDIDATE.template_fingerprint
    expected_parameters = orders_v2_bigquery_parameter_contract_fingerprint()
    expected_sdk = orders_v2_bigquery_sdk_adapter_fingerprint()
    if schema_attestation.candidate_template_fingerprint != expected_template:
        raise ValueError("schema attestation template fingerprint mismatch")
    if live_evidence.candidate_template_fingerprint != expected_template:
        raise ValueError("live evidence template fingerprint mismatch")
    if schema_attestation.parameter_contract_fingerprint != expected_parameters:
        raise ValueError("schema attestation parameter fingerprint mismatch")
    if live_evidence.parameter_contract_fingerprint != expected_parameters:
        raise ValueError("live evidence parameter fingerprint mismatch")
    if schema_attestation.sdk_adapter_fingerprint != expected_sdk:
        raise ValueError("schema attestation SDK fingerprint mismatch")
    if live_evidence.sdk_adapter_fingerprint != expected_sdk:
        raise ValueError("live evidence SDK fingerprint mismatch")

    return OrdersV2HumanPromotionReviewArtifact(
        version=HUMAN_PROMOTION_REVIEW_VERSION,
        kind="orders_v2_human_promotion_review",
        reviewed_at=reviewed_at,
        reviewer_identity_sha256=sha256_text(reviewer_identity),
        review_context_sha256=sha256_text(review_context),
        schema_attestation_fingerprint=schema_attestation.artifact_fingerprint,
        live_cross_tenant_evidence_fingerprint=live_evidence.evidence_fingerprint,
        candidate_template_fingerprint=expected_template,
        parameter_contract_fingerprint=expected_parameters,
        sdk_adapter_fingerprint=expected_sdk,
        review_decision="APPROVE_FOR_RELEASE_GATE",
        human_review_completed=True,
        release_gate_candidate=True,
        release_gate_required=True,
        policy_mutation_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=HUMAN_PROMOTION_RELEASE_BLOCKER,
    )


def build_orders_v2_release_gate_artifact(
    *,
    human_review: OrdersV2HumanPromotionReviewArtifact,
    release_manifest: str,
    release_approver_identity: str,
    released_at: datetime,
) -> OrdersV2ReleaseGateArtifact:
    """Bind one release approval to an exact human review without deploying."""

    if released_at.tzinfo is None or released_at.utcoffset() is None:
        raise ValueError("release timestamp must be timezone-aware")
    if human_review.human_review_completed is not True:
        raise ValueError("human review is incomplete")
    if human_review.release_gate_candidate is not True:
        raise ValueError("human review is not a release-gate candidate")
    if human_review.release_gate_required is not True:
        raise ValueError("human review release-gate state is invalid")
    if human_review.policy_mutation_permitted is not False:
        raise ValueError("human review policy mutation state is invalid")
    if human_review.promotion_eligible is not False:
        raise ValueError("human review promotion state is invalid")
    if human_review.production_ready is not False:
        raise ValueError("human review production state is invalid")

    expected_template = ORDERS_V2_CANDIDATE.template_fingerprint
    expected_parameters = orders_v2_bigquery_parameter_contract_fingerprint()
    expected_sdk = orders_v2_bigquery_sdk_adapter_fingerprint()
    if human_review.candidate_template_fingerprint != expected_template:
        raise ValueError("human review template fingerprint mismatch")
    if human_review.parameter_contract_fingerprint != expected_parameters:
        raise ValueError("human review parameter fingerprint mismatch")
    if human_review.sdk_adapter_fingerprint != expected_sdk:
        raise ValueError("human review SDK fingerprint mismatch")

    return OrdersV2ReleaseGateArtifact(
        version=ORDERS_V2_RELEASE_GATE_VERSION,
        kind="orders_v2_release_gate_artifact",
        released_at=released_at,
        release_manifest_sha256=sha256_text(release_manifest),
        release_approver_identity_sha256=sha256_text(release_approver_identity),
        human_review_fingerprint=human_review.review_fingerprint,
        candidate_template_fingerprint=expected_template,
        parameter_contract_fingerprint=expected_parameters,
        sdk_adapter_fingerprint=expected_sdk,
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
