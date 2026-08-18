"""Provenance-bound teaching/distillation candidates for Jarvis local models.

The goal is to convert verified teaching material into reusable local capability
without turning chats, tenant data, secrets or unlicensed text into a shared
training corpus.  Shared-base training is limited to source-grounded,
license-cleared, non-private material.  Tenant knowledge stays in tenant-bound
memory unless an explicitly isolated adapter path is approved.

This module only produces training candidates.  It never starts fine-tuning,
changes production weights, promotes an adapter, or exports tenant material.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

TEACHING_DISTILLATION_CONTRACT = "eay-teaching-distillation-v1"


class KnowledgeSensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class TrainingScope(str, Enum):
    SHARED_BASE = "shared_base"
    TENANT_ISOLATED_ADAPTER = "tenant_isolated_adapter"
    MEMORY_ONLY = "memory_only"


class SourceTrainingPolicy(BaseModel):
    source_ref: str = Field(min_length=1)
    license_ref: str = Field(min_length=1)
    commercial_use_allowed: bool = False
    derivative_training_allowed: bool = False
    redistribution_allowed: bool = False
    verified_at: datetime
    policy_evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "SourceTrainingPolicy":
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise ValueError("teaching_distillation_policy_requires_timezone")
        return self


class TeachingMaterial(BaseModel):
    material_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    ideal_response: str = Field(min_length=1)
    sensitivity: KnowledgeSensitivity
    tenant_ref: str | None = None
    factual_evidence_refs: tuple[str, ...] = Field(min_length=1)
    contains_secret: bool = False
    contains_personal_data: bool = False
    contains_hidden_reasoning: bool = False
    source_grounded: bool = True

    @model_validator(mode="after")
    def material_has_safe_identity(self) -> "TeachingMaterial":
        if self.sensitivity in {KnowledgeSensitivity.CONFIDENTIAL, KnowledgeSensitivity.RESTRICTED} and not self.tenant_ref:
            raise ValueError("teaching_distillation_private_material_requires_tenant")
        if self.contains_secret:
            raise ValueError("teaching_distillation_secret_material_forbidden")
        if self.contains_hidden_reasoning:
            raise ValueError("teaching_distillation_hidden_reasoning_forbidden")
        if not self.source_grounded:
            raise ValueError("teaching_distillation_source_grounding_required")
        return self


class DistillationApproval(BaseModel):
    approval_ref: str = Field(min_length=1)
    approved_by_principal_ref: str = Field(min_length=1)
    approved_at: datetime
    scope: TrainingScope
    tenant_ref: str | None = None
    human_reviewed: bool = True

    @model_validator(mode="after")
    def approval_is_valid(self) -> "DistillationApproval":
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("teaching_distillation_approval_requires_timezone")
        if not self.human_reviewed:
            raise ValueError("teaching_distillation_requires_human_review")
        if self.scope is TrainingScope.TENANT_ISOLATED_ADAPTER and not self.tenant_ref:
            raise ValueError("teaching_distillation_tenant_adapter_requires_tenant")
        if self.scope is TrainingScope.SHARED_BASE and self.tenant_ref is not None:
            raise ValueError("teaching_distillation_shared_base_cannot_be_tenant_bound")
        return self


class TeachingTrainingCandidate(BaseModel):
    contract: str = TEACHING_DISTILLATION_CONTRACT
    candidate_ref: str
    material_id: str
    objective_id: str
    source_ref: str
    scope: TrainingScope
    tenant_ref: str | None = None
    instruction: str
    ideal_response: str
    evidence_refs: tuple[str, ...]
    license_ref: str
    approval_ref: str
    export_allowed: bool = False
    production_weight_update_allowed: bool = False
    automatic_training_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def candidate_never_self_trains(self) -> "TeachingTrainingCandidate":
        if self.production_weight_update_allowed or self.automatic_training_allowed:
            raise ValueError("teaching_distillation_candidate_cannot_self_train")
        if self.scope is TrainingScope.TENANT_ISOLATED_ADAPTER and self.export_allowed:
            raise ValueError("teaching_distillation_tenant_candidate_cannot_export")
        return self


def _candidate_ref(material: TeachingMaterial, scope: TrainingScope, approval_ref: str) -> str:
    payload = "|".join(
        [material.material_id, material.source_ref, material.objective_id, scope.value, approval_ref]
    ).encode("utf-8")
    return "teaching-candidate:" + hashlib.sha256(payload).hexdigest()


def build_training_candidate(
    *,
    material: TeachingMaterial,
    source_policy: SourceTrainingPolicy,
    approval: DistillationApproval,
) -> TeachingTrainingCandidate:
    if source_policy.source_ref != material.source_ref:
        raise ValueError("teaching_distillation_source_policy_mismatch")
    if approval.scope is TrainingScope.TENANT_ISOLATED_ADAPTER:
        if material.tenant_ref != approval.tenant_ref:
            raise ValueError("teaching_distillation_tenant_approval_mismatch")

    blockers: list[str] = []
    export_allowed = False

    if approval.scope is TrainingScope.MEMORY_ONLY:
        blockers.append("teaching_distillation_memory_only_not_trainable")
    elif approval.scope is TrainingScope.SHARED_BASE:
        if material.tenant_ref is not None or material.sensitivity is not KnowledgeSensitivity.PUBLIC:
            blockers.append("teaching_distillation_shared_base_requires_public_non_tenant_material")
        if material.contains_personal_data:
            blockers.append("teaching_distillation_shared_base_personal_data_forbidden")
        if not source_policy.commercial_use_allowed:
            blockers.append("teaching_distillation_commercial_use_not_cleared")
        if not source_policy.derivative_training_allowed:
            blockers.append("teaching_distillation_derivative_training_not_cleared")
        export_allowed = not blockers and source_policy.redistribution_allowed
    else:
        if material.tenant_ref is None:
            blockers.append("teaching_distillation_tenant_material_missing")
        if material.sensitivity is KnowledgeSensitivity.RESTRICTED:
            blockers.append("teaching_distillation_restricted_material_weight_training_forbidden")
        if material.contains_personal_data:
            blockers.append("teaching_distillation_personal_data_weight_training_forbidden")
        if not source_policy.derivative_training_allowed:
            blockers.append("teaching_distillation_derivative_training_not_cleared")
        export_allowed = False

    return TeachingTrainingCandidate(
        candidate_ref=_candidate_ref(material, approval.scope, approval.approval_ref),
        material_id=material.material_id,
        objective_id=material.objective_id,
        source_ref=material.source_ref,
        scope=approval.scope,
        tenant_ref=material.tenant_ref if approval.scope is TrainingScope.TENANT_ISOLATED_ADAPTER else None,
        instruction=material.instruction,
        ideal_response=material.ideal_response,
        evidence_refs=tuple(dict.fromkeys((*material.factual_evidence_refs, *source_policy.policy_evidence_refs))),
        license_ref=source_policy.license_ref,
        approval_ref=approval.approval_ref,
        export_allowed=export_allowed,
        blockers=tuple(dict.fromkeys(blockers)),
    )
