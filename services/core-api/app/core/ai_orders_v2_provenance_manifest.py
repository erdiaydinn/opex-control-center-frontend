"""Fail-closed provenance manifest for the blocked orders-v2 promotion chain.

The manifest validates the complete evidence/approval/consumption fingerprint
chain without mutating the active query policy, canonical consumption ledger,
or runtime execution state. It is review evidence only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orders_v2_deployment_authorization import (
    OrdersV2DeploymentAuthorizationArtifact,
)
from app.core.ai_orders_v2_human_promotion_review import (
    OrdersV2HumanPromotionReviewArtifact,
    OrdersV2ReleaseGateArtifact,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import (
    OrdersV2LiveCrossTenantEvidence,
)
from app.core.ai_orders_v2_manual_policy_promotion import (
    OrdersV2ManualPolicyPromotionProposal,
)
from app.core.ai_orders_v2_policy_consumption_commit_attestation import (
    OrdersV2PolicyConsumptionCommitAttestation,
)
from app.core.ai_orders_v2_policy_consumption_patch import (
    OrdersV2PolicyConsumptionPatchArtifact,
)
from app.core.ai_orders_v2_policy_consumption_review import (
    OrdersV2PolicyConsumptionReviewProposal,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    OrdersV2PolicyTransitionGuardArtifact,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PROVENANCE_MANIFEST_VERSION = 1
PROVENANCE_MANIFEST_BLOCKER = "orders_v2_manual_production_activation_required"


class OrdersV2ProvenanceManifest(BaseModel):
    """Immutable digest of the exact reviewed orders-v2 approval chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_provenance_manifest"]
    schema_attestation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    live_cross_tenant_evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)
    human_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    release_gate_fingerprint: str = Field(pattern=SHA256_PATTERN)
    deployment_authorization_fingerprint: str = Field(pattern=SHA256_PATTERN)
    policy_proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    transition_guard_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumption_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumption_patch_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumption_commit_attestation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    resulting_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    chain_validated: Literal[True]
    manual_production_activation_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal[
        "orders_v2_manual_production_activation_required"
    ]

    @property
    def manifest_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_provenance_manifest(
    *,
    schema_attestation: OrdersV2SchemaAttestationArtifact,
    live_evidence: OrdersV2LiveCrossTenantEvidence,
    human_review: OrdersV2HumanPromotionReviewArtifact,
    release_gate: OrdersV2ReleaseGateArtifact,
    deployment_authorization: OrdersV2DeploymentAuthorizationArtifact,
    policy_proposal: OrdersV2ManualPolicyPromotionProposal,
    transition_guard: OrdersV2PolicyTransitionGuardArtifact,
    consumption_review: OrdersV2PolicyConsumptionReviewProposal,
    consumption_patch: OrdersV2PolicyConsumptionPatchArtifact,
    commit_attestation: OrdersV2PolicyConsumptionCommitAttestation,
) -> OrdersV2ProvenanceManifest:
    """Validate every adjacent provenance edge and remain non-promoting."""

    schema_fp = schema_attestation.artifact_fingerprint
    live_fp = live_evidence.evidence_fingerprint
    human_fp = human_review.review_fingerprint
    release_fp = release_gate.release_gate_fingerprint
    deployment_fp = deployment_authorization.deployment_authorization_fingerprint
    proposal_fp = policy_proposal.proposal_fingerprint
    guard_fp = transition_guard.guard_fingerprint
    review_fp = consumption_review.review_fingerprint
    patch_fp = consumption_patch.patch_fingerprint
    commit_fp = commit_attestation.attestation_fingerprint

    if live_evidence.schema_attestation_fingerprint != schema_fp:
        raise ValueError("live evidence is not bound to schema attestation")
    if human_review.schema_attestation_fingerprint != schema_fp:
        raise ValueError("human review schema attestation fingerprint mismatch")
    if human_review.live_cross_tenant_evidence_fingerprint != live_fp:
        raise ValueError("human review live evidence fingerprint mismatch")
    if release_gate.human_review_fingerprint != human_fp:
        raise ValueError("release gate human review fingerprint mismatch")
    if deployment_authorization.human_review_fingerprint != human_fp:
        raise ValueError("deployment human review fingerprint mismatch")
    if deployment_authorization.release_gate_fingerprint != release_fp:
        raise ValueError("deployment release gate fingerprint mismatch")
    if policy_proposal.human_review_fingerprint != human_fp:
        raise ValueError("policy proposal human review fingerprint mismatch")
    if policy_proposal.release_gate_fingerprint != release_fp:
        raise ValueError("policy proposal release gate fingerprint mismatch")
    if policy_proposal.deployment_authorization_fingerprint != deployment_fp:
        raise ValueError("policy proposal deployment fingerprint mismatch")
    if transition_guard.proposal_fingerprint != proposal_fp:
        raise ValueError("transition guard proposal fingerprint mismatch")
    if consumption_review.proposal_fingerprint != proposal_fp:
        raise ValueError("consumption review proposal fingerprint mismatch")
    if consumption_review.guard_fingerprint != guard_fp:
        raise ValueError("consumption review guard fingerprint mismatch")
    if consumption_patch.review_fingerprint != review_fp:
        raise ValueError("consumption patch review fingerprint mismatch")
    if commit_attestation.patch_fingerprint != patch_fp:
        raise ValueError("commit attestation patch fingerprint mismatch")
    if (
        commit_attestation.previous_ledger_fingerprint
        != consumption_patch.current_ledger_fingerprint
    ):
        raise ValueError("commit attestation previous ledger mismatch")
    if (
        commit_attestation.appended_entry_fingerprint
        != consumption_patch.proposed_entry_fingerprint
    ):
        raise ValueError("commit attestation appended entry mismatch")
    if (
        commit_attestation.resulting_ledger_fingerprint
        != consumption_patch.resulting_ledger_fingerprint
    ):
        raise ValueError("commit attestation resulting ledger mismatch")

    expected_template = ORDERS_V2_CANDIDATE.template_fingerprint
    template_bindings = (
        schema_attestation.candidate_template_fingerprint,
        live_evidence.candidate_template_fingerprint,
        human_review.candidate_template_fingerprint,
        release_gate.candidate_template_fingerprint,
        deployment_authorization.candidate_template_fingerprint,
        policy_proposal.target_query_template_sha256,
    )
    if any(value != expected_template for value in template_bindings):
        raise ValueError("orders-v2 query template provenance drift detected")

    non_promoting = (
        schema_attestation.promotion_eligible is False,
        live_evidence.promotion_eligible is False,
        human_review.promotion_eligible is False,
        release_gate.promotion_eligible is False,
        deployment_authorization.promotion_eligible is False,
        policy_proposal.promotion_eligible is False,
        transition_guard.promotion_eligible is False,
        consumption_review.promotion_eligible is False,
        consumption_patch.promotion_eligible is False,
        commit_attestation.promotion_eligible is False,
        human_review.production_ready is False,
        release_gate.production_ready is False,
        deployment_authorization.production_ready is False,
        policy_proposal.production_ready is False,
        transition_guard.production_ready is False,
        consumption_review.production_ready is False,
        consumption_patch.production_ready is False,
        commit_attestation.production_ready is False,
    )
    if not all(non_promoting):
        raise ValueError("orders-v2 provenance chain contains promoting state")

    return OrdersV2ProvenanceManifest(
        version=PROVENANCE_MANIFEST_VERSION,
        kind="orders_v2_provenance_manifest",
        schema_attestation_fingerprint=schema_fp,
        live_cross_tenant_evidence_fingerprint=live_fp,
        human_review_fingerprint=human_fp,
        release_gate_fingerprint=release_fp,
        deployment_authorization_fingerprint=deployment_fp,
        policy_proposal_fingerprint=proposal_fp,
        transition_guard_fingerprint=guard_fp,
        consumption_review_fingerprint=review_fp,
        consumption_patch_fingerprint=patch_fp,
        consumption_commit_attestation_fingerprint=commit_fp,
        candidate_template_fingerprint=expected_template,
        resulting_ledger_fingerprint=commit_attestation.resulting_ledger_fingerprint,
        chain_validated=True,
        manual_production_activation_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=PROVENANCE_MANIFEST_BLOCKER,
    )
