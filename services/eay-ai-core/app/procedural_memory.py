"""Verified procedural memory for repeatable Jarvis work.

A successful one-off agent trajectory is not automatically trusted forever.
Procedures are compiled only from evidence-bound demonstrations whose final
effect was independently verified. Mutating procedures stay candidate-only
until replay/equivalence evidence exists, and detected drift suspends reuse.

Generic procedures may remain tenant-scoped. Company-private procedures must
use the exact Company Brain identity/profile and cannot be compiled through the
generic path or from demonstrations belonging to another company.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import AliasChoices, BaseModel, Field, model_validator

from .company_context_boundary import (
    CompanyContextPlane,
    CompanyContextSnapshot,
    require_company_plane,
)

PROCEDURAL_MEMORY_CONTRACT = "eay-procedural-memory-v1"


class ProcedureStepKind(str, Enum):
    API = "api"
    DOM = "dom"
    ACCESSIBILITY = "accessibility"
    DESKTOP_UI = "desktop_ui"
    VISION = "vision"
    READBACK = "readback"


class ProcedureStatus(str, Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ProcedureStep(BaseModel):
    step_id: str = Field(min_length=1)
    kind: ProcedureStepKind
    operation_ref: str = Field(min_length=1)
    input_schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_effect_ref: str | None = None
    # Keep verifier_ref as the stable internal/serialized field so existing
    # procedure fingerprints and callers do not drift. Newer execution layers
    # use the more explicit effect_verifier_ref spelling; accept both inputs.
    verifier_ref: str | None = Field(
        default=None,
        validation_alias=AliasChoices("verifier_ref", "effect_verifier_ref"),
    )
    side_effect: bool = False

    @property
    def effect_verifier_ref(self) -> str | None:
        """Compatibility read alias for newer write-execution components."""
        return self.verifier_ref

    @model_validator(mode="after")
    def writes_require_effect_contract(self) -> "ProcedureStep":
        if self.side_effect and (not self.expected_effect_ref or not self.verifier_ref):
            raise ValueError("procedure_side_effect_requires_effect_verifier")
        return self


class ProcedureDemonstration(BaseModel):
    demonstration_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str | None = None
    company_profile_revision: str | None = None
    company_identity_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    capability_name: str = Field(min_length=1)
    observed_at: datetime
    step_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    successful: bool
    effect_verified: bool
    ambiguous_outcome: bool = False
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_refs: tuple[str, ...]

    @model_validator(mode="after")
    def demonstration_is_evidence_bound(self) -> "ProcedureDemonstration":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("procedure_demonstration_requires_timezone")
        if not self.evidence_refs:
            raise ValueError("procedure_demonstration_requires_evidence")
        if self.ambiguous_outcome and self.effect_verified:
            raise ValueError("ambiguous_procedure_outcome_cannot_be_verified")
        company_scope = (
            self.company_id,
            self.company_profile_revision,
            self.company_identity_fingerprint,
        )
        if any(value is not None for value in company_scope) and not all(
            value is not None for value in company_scope
        ):
            raise ValueError("procedure_demonstration_company_scope_must_be_complete")
        return self


class ProceduralCapability(BaseModel):
    contract: str = PROCEDURAL_MEMORY_CONTRACT
    capability_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_name: str
    tenant_id: str
    company_id: str | None = None
    company_profile_revision: str | None = None
    company_identity_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    version: int = Field(ge=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    steps: tuple[ProcedureStep, ...]
    demonstrations: tuple[str, ...]
    status: ProcedureStatus
    direct_execution_allowed: bool
    requires_revalidation: bool
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def direct_execution_cannot_ignore_blockers(self) -> "ProceduralCapability":
        if self.direct_execution_allowed and self.blockers:
            raise ValueError("procedure_execution_cannot_ignore_blockers")
        if self.direct_execution_allowed and self.status is not ProcedureStatus.VALIDATED:
            raise ValueError("procedure_direct_execution_requires_validated_status")
        company_scope = (
            self.company_id,
            self.company_profile_revision,
            self.company_identity_fingerprint,
        )
        if any(value is not None for value in company_scope) and not all(
            value is not None for value in company_scope
        ):
            raise ValueError("procedural_capability_company_scope_must_be_complete")
        return self


def procedure_step_fingerprint(steps: tuple[ProcedureStep, ...]) -> str:
    canonical = json.dumps(
        [step.model_dump(mode="json") for step in steps],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _capability_id(
    *,
    tenant_id: str,
    capability_name: str,
    step_fingerprint: str,
    company_identity_fingerprint: str | None = None,
) -> str:
    payload: dict[str, str] = {
        "tenant_id": tenant_id,
        "capability_name": capability_name,
        "steps": step_fingerprint,
    }
    if company_identity_fingerprint is not None:
        payload["company_identity_fingerprint"] = company_identity_fingerprint
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compile_procedure(
    *,
    tenant_id: str,
    capability_name: str,
    steps: tuple[ProcedureStep, ...],
    demonstrations: list[ProcedureDemonstration],
    version: int = 1,
    minimum_verified_demonstrations: int = 2,
) -> ProceduralCapability:
    """Compile a generic tenant-scoped procedure.

    Company-bound demonstrations are rejected here. They must go through
    compile_company_procedure with an exact CompanyContextSnapshot so a caller
    cannot accidentally erase company scope by using the legacy compiler.
    """

    fingerprint = _validate_compile_input(
        steps=steps,
        minimum_verified_demonstrations=minimum_verified_demonstrations,
    )
    relevant = _relevant_demonstrations(
        demonstrations=demonstrations,
        tenant_id=tenant_id,
        capability_name=capability_name,
        step_fingerprint=fingerprint,
    )
    if any(demo.company_identity_fingerprint is not None for demo in relevant):
        raise ValueError("procedure_company_bound_demonstration_requires_company_compile")
    return _compile_relevant(
        tenant_id=tenant_id,
        company_id=None,
        company_profile_revision=None,
        company_identity_fingerprint=None,
        capability_name=capability_name,
        steps=steps,
        step_fingerprint=fingerprint,
        relevant=relevant,
        version=version,
        minimum_verified_demonstrations=minimum_verified_demonstrations,
    )


def compile_company_procedure(
    *,
    company_context: CompanyContextSnapshot,
    capability_name: str,
    steps: tuple[ProcedureStep, ...],
    demonstrations: list[ProcedureDemonstration],
    version: int = 1,
    minimum_verified_demonstrations: int = 2,
) -> ProceduralCapability:
    """Compile a procedure that belongs to one exact company/profile revision."""

    context = CompanyContextSnapshot.model_validate(
        company_context.model_dump(mode="json")
    )
    # A learned company procedure consumes company memory and becomes a company
    # capability. Presence of these planes is context completeness only; neither
    # plane grants execution authority.
    require_company_plane(snapshot=context, plane=CompanyContextPlane.MEMORY)
    require_company_plane(snapshot=context, plane=CompanyContextPlane.CAPABILITY)

    fingerprint = _validate_compile_input(
        steps=steps,
        minimum_verified_demonstrations=minimum_verified_demonstrations,
    )
    relevant = _relevant_demonstrations(
        demonstrations=demonstrations,
        tenant_id=context.identity.tenant_id,
        capability_name=capability_name,
        step_fingerprint=fingerprint,
    )
    for demo in relevant:
        if (
            demo.company_id != context.identity.company_id
            or demo.company_profile_revision != context.identity.profile_revision
            or demo.company_identity_fingerprint != context.identity.fingerprint
        ):
            raise ValueError("procedure_company_demonstration_scope_mismatch")

    return _compile_relevant(
        tenant_id=context.identity.tenant_id,
        company_id=context.identity.company_id,
        company_profile_revision=context.identity.profile_revision,
        company_identity_fingerprint=context.identity.fingerprint,
        capability_name=capability_name,
        steps=steps,
        step_fingerprint=fingerprint,
        relevant=relevant,
        version=version,
        minimum_verified_demonstrations=minimum_verified_demonstrations,
    )


def _validate_compile_input(
    *,
    steps: tuple[ProcedureStep, ...],
    minimum_verified_demonstrations: int,
) -> str:
    if not steps:
        raise ValueError("procedure_requires_steps")
    if minimum_verified_demonstrations < 1:
        raise ValueError("procedure_minimum_demonstrations_invalid")
    return procedure_step_fingerprint(steps)


def _relevant_demonstrations(
    *,
    demonstrations: list[ProcedureDemonstration],
    tenant_id: str,
    capability_name: str,
    step_fingerprint: str,
) -> list[ProcedureDemonstration]:
    return [
        demo
        for demo in demonstrations
        if demo.tenant_id == tenant_id
        and demo.capability_name == capability_name
        and demo.step_fingerprint == step_fingerprint
    ]


def _compile_relevant(
    *,
    tenant_id: str,
    company_id: str | None,
    company_profile_revision: str | None,
    company_identity_fingerprint: str | None,
    capability_name: str,
    steps: tuple[ProcedureStep, ...],
    step_fingerprint: str,
    relevant: list[ProcedureDemonstration],
    version: int,
    minimum_verified_demonstrations: int,
) -> ProceduralCapability:
    blockers: list[str] = []
    verified = [
        demo
        for demo in relevant
        if demo.successful and demo.effect_verified and not demo.ambiguous_outcome
    ]

    if len(verified) < minimum_verified_demonstrations:
        blockers.append("procedure_verified_demonstrations_insufficient")
    environments = {demo.environment_fingerprint for demo in verified}
    if len(environments) > 1:
        blockers.append("procedure_demonstration_environment_drift")
    if any(demo.ambiguous_outcome for demo in relevant):
        blockers.append("procedure_contains_ambiguous_demonstration")

    has_write = any(step.side_effect for step in steps)
    if has_write and len(verified) < max(2, minimum_verified_demonstrations):
        blockers.append("procedure_write_requires_repeated_effect_verification")

    environment = next(iter(environments), "0" * 64)
    status = ProcedureStatus.VALIDATED if not blockers else ProcedureStatus.CANDIDATE
    return ProceduralCapability(
        capability_id=_capability_id(
            tenant_id=tenant_id,
            company_identity_fingerprint=company_identity_fingerprint,
            capability_name=capability_name,
            step_fingerprint=step_fingerprint,
        ),
        capability_name=capability_name,
        tenant_id=tenant_id,
        company_id=company_id,
        company_profile_revision=company_profile_revision,
        company_identity_fingerprint=company_identity_fingerprint,
        version=version,
        environment_fingerprint=environment,
        steps=steps,
        demonstrations=tuple(sorted(demo.demonstration_id for demo in verified)),
        status=status,
        direct_execution_allowed=not blockers,
        requires_revalidation=bool(blockers),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def revalidate_environment(
    capability: ProceduralCapability,
    *,
    observed_environment_fingerprint: str,
) -> ProceduralCapability:
    if observed_environment_fingerprint == capability.environment_fingerprint:
        return capability
    blockers = tuple(dict.fromkeys((*capability.blockers, "procedure_runtime_environment_drift")))
    return capability.model_copy(
        update={
            "status": ProcedureStatus.SUSPENDED,
            "direct_execution_allowed": False,
            "requires_revalidation": True,
            "blockers": blockers,
        }
    )
