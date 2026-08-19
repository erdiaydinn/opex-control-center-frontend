"""Integrity-sealed runtime binding for per-company Jarvis context.

Jarvis Core may be shared across customers. Company Brain state may not be.
This module turns an already integrity-checked CompanyContextSnapshot into two
non-authoritative receipts:

- onboarding completeness: which canonical company planes are actually bound;
- runtime request binding: which exact company/profile snapshot a request used.

Neither receipt promotes Company World truth, grants tool/action authority, nor
allows missing company knowledge to fall back to another company.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .company_context_boundary import (
    CompanyContextPlane,
    CompanyContextSnapshot,
)

COMPANY_BRAIN_RUNTIME_CONTRACT = "eay-company-brain-runtime-v1"

CANONICAL_COMPANY_BRAIN_PLANES: tuple[CompanyContextPlane, ...] = (
    CompanyContextPlane.KNOWLEDGE,
    CompanyContextPlane.TRUTH_BINDING,
    CompanyContextPlane.POLICY,
    CompanyContextPlane.MEMORY,
    CompanyContextPlane.CAPABILITY,
    CompanyContextPlane.CALIBRATION,
    CompanyContextPlane.MODEL_PROFILE,
)

_SECRET_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature)"
)


class CompanyBrainOnboardingStage(str, Enum):
    IDENTIFIED = "identified"
    PARTIAL = "partial"
    CONTEXT_COMPLETE = "context_complete"


class CompanyRuntimeDisposition(str, Enum):
    PROCEED = "proceed"
    HOLD = "hold"


class CompanyBrainOnboardingSnapshot(BaseModel):
    contract: str = COMPANY_BRAIN_RUNTIME_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    company_identity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_context_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of: datetime
    required_planes: tuple[CompanyContextPlane, ...]
    available_planes: tuple[CompanyContextPlane, ...]
    missing_planes: tuple[CompanyContextPlane, ...]
    stage: CompanyBrainOnboardingStage
    semantic_context_complete: bool
    cross_company_fallback_allowed: bool = False
    firm_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def onboarding_is_integral_and_non_authoritative(self) -> "CompanyBrainOnboardingSnapshot":
        _aware(self.as_of, "company_brain_onboarding_as_of_requires_timezone")
        if len(self.required_planes) != len(set(self.required_planes)):
            raise ValueError("company_brain_onboarding_duplicate_required_plane")
        if len(self.available_planes) != len(set(self.available_planes)):
            raise ValueError("company_brain_onboarding_duplicate_available_plane")
        expected_missing = tuple(
            plane for plane in self.required_planes if plane not in self.available_planes
        )
        if self.missing_planes != expected_missing:
            raise ValueError("company_brain_onboarding_missing_plane_mismatch")
        expected_complete = not expected_missing
        if self.semantic_context_complete is not expected_complete:
            raise ValueError("company_brain_onboarding_completeness_mismatch")
        expected_stage = _stage(
            required_planes=self.required_planes,
            missing_planes=expected_missing,
        )
        if self.stage is not expected_stage:
            raise ValueError("company_brain_onboarding_stage_mismatch")
        if self.cross_company_fallback_allowed:
            raise ValueError("company_brain_onboarding_cross_company_fallback_forbidden")
        if self.firm_truth_authority_granted:
            raise ValueError("company_brain_onboarding_never_grants_firm_truth")
        if self.execution_authority_granted:
            raise ValueError("company_brain_onboarding_never_grants_execution_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_brain_onboarding_fingerprint_mismatch")
        return self


class CompanyRuntimeRequestBinding(BaseModel):
    contract: str = COMPANY_BRAIN_RUNTIME_CONTRACT
    request_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    company_identity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_context_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    onboarding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at: datetime
    required_planes: tuple[CompanyContextPlane, ...]
    resolved_binding_fingerprints: tuple[str, ...]
    disposition: CompanyRuntimeDisposition
    blockers: tuple[str, ...]
    cross_company_fallback_allowed: bool = False
    firm_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def request_binding_is_integral_and_non_authoritative(self) -> "CompanyRuntimeRequestBinding":
        _aware(self.requested_at, "company_runtime_request_requires_timezone")
        _safe_ref(self.request_id, "company_runtime_request_secret_material_forbidden")
        if len(self.required_planes) != len(set(self.required_planes)):
            raise ValueError("company_runtime_request_duplicate_required_plane")
        if len(self.resolved_binding_fingerprints) != len(
            set(self.resolved_binding_fingerprints)
        ):
            raise ValueError("company_runtime_request_duplicate_resolved_binding")
        if self.disposition is CompanyRuntimeDisposition.PROCEED and self.blockers:
            raise ValueError("company_runtime_proceed_cannot_have_blockers")
        if self.disposition is CompanyRuntimeDisposition.HOLD and not self.blockers:
            raise ValueError("company_runtime_hold_requires_blocker")
        if self.cross_company_fallback_allowed:
            raise ValueError("company_runtime_cross_company_fallback_forbidden")
        if self.firm_truth_authority_granted:
            raise ValueError("company_runtime_binding_never_grants_firm_truth")
        if self.execution_authority_granted:
            raise ValueError("company_runtime_binding_never_grants_execution_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_runtime_request_binding_fingerprint_mismatch")
        return self


def assess_company_brain_onboarding(
    *,
    snapshot: CompanyContextSnapshot,
    required_planes: tuple[CompanyContextPlane, ...] = CANONICAL_COMPANY_BRAIN_PLANES,
) -> CompanyBrainOnboardingSnapshot:
    context = CompanyContextSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _unique_planes(required_planes, "company_brain_onboarding_duplicate_required_plane")
    available = tuple(
        sorted(set(context.available_planes), key=lambda item: item.value)
    )
    missing = tuple(plane for plane in required_planes if plane not in available)
    draft = {
        "contract": COMPANY_BRAIN_RUNTIME_CONTRACT,
        "tenant_id": context.identity.tenant_id,
        "company_id": context.identity.company_id,
        "profile_revision": context.identity.profile_revision,
        "company_identity_fingerprint": context.identity.fingerprint,
        "company_context_snapshot_fingerprint": context.fingerprint,
        "as_of": _iso(context.as_of),
        "required_planes": [plane.value for plane in required_planes],
        "available_planes": [plane.value for plane in available],
        "missing_planes": [plane.value for plane in missing],
        "stage": _stage(
            required_planes=required_planes,
            missing_planes=missing,
        ).value,
        "semantic_context_complete": not missing,
        "cross_company_fallback_allowed": False,
        "firm_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyBrainOnboardingSnapshot.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def bind_company_runtime_request(
    *,
    snapshot: CompanyContextSnapshot,
    request_id: str,
    requested_at: datetime,
    required_planes: tuple[CompanyContextPlane, ...],
) -> CompanyRuntimeRequestBinding:
    context = CompanyContextSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _aware(requested_at, "company_runtime_request_requires_timezone")
    _safe_ref(request_id, "company_runtime_request_secret_material_forbidden")
    if requested_at < context.as_of:
        raise ValueError("company_runtime_request_predates_context_snapshot")
    onboarding = assess_company_brain_onboarding(
        snapshot=context,
        required_planes=required_planes,
    )
    missing = onboarding.missing_planes
    blockers = tuple(f"company_brain_plane_missing:{plane.value}" for plane in missing)
    required_set = set(required_planes)
    resolved = tuple(
        sorted(
            binding.fingerprint
            for binding in context.bindings
            if binding.plane in required_set
        )
    )
    disposition = (
        CompanyRuntimeDisposition.HOLD
        if blockers
        else CompanyRuntimeDisposition.PROCEED
    )
    draft = {
        "contract": COMPANY_BRAIN_RUNTIME_CONTRACT,
        "request_id": request_id,
        "tenant_id": context.identity.tenant_id,
        "company_id": context.identity.company_id,
        "profile_revision": context.identity.profile_revision,
        "company_identity_fingerprint": context.identity.fingerprint,
        "company_context_snapshot_fingerprint": context.fingerprint,
        "onboarding_fingerprint": onboarding.fingerprint,
        "requested_at": _iso(requested_at),
        "required_planes": [plane.value for plane in required_planes],
        "resolved_binding_fingerprints": list(resolved),
        "disposition": disposition.value,
        "blockers": list(blockers),
        "cross_company_fallback_allowed": False,
        "firm_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyRuntimeRequestBinding.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def validate_company_runtime_request_binding(
    *,
    binding: CompanyRuntimeRequestBinding,
    snapshot: CompanyContextSnapshot,
) -> CompanyRuntimeRequestBinding:
    runtime_binding = CompanyRuntimeRequestBinding.model_validate(
        binding.model_dump(mode="json")
    )
    context = CompanyContextSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if runtime_binding.tenant_id != context.identity.tenant_id:
        raise ValueError("company_runtime_cross_tenant_binding")
    if runtime_binding.company_id != context.identity.company_id:
        raise ValueError("company_runtime_cross_company_binding")
    if runtime_binding.profile_revision != context.identity.profile_revision:
        raise ValueError("company_runtime_profile_revision_mismatch")
    if runtime_binding.company_identity_fingerprint != context.identity.fingerprint:
        raise ValueError("company_runtime_identity_fingerprint_mismatch")
    if runtime_binding.company_context_snapshot_fingerprint != context.fingerprint:
        raise ValueError("company_runtime_snapshot_fingerprint_mismatch")
    rebuilt = assess_company_brain_onboarding(
        snapshot=context,
        required_planes=runtime_binding.required_planes,
    )
    if runtime_binding.onboarding_fingerprint != rebuilt.fingerprint:
        raise ValueError("company_runtime_onboarding_fingerprint_mismatch")
    expected_resolved = tuple(
        sorted(
            item.fingerprint
            for item in context.bindings
            if item.plane in set(runtime_binding.required_planes)
        )
    )
    if runtime_binding.resolved_binding_fingerprints != expected_resolved:
        raise ValueError("company_runtime_resolved_binding_mismatch")
    return runtime_binding


def _stage(
    *,
    required_planes: tuple[CompanyContextPlane, ...],
    missing_planes: tuple[CompanyContextPlane, ...],
) -> CompanyBrainOnboardingStage:
    if not missing_planes:
        return CompanyBrainOnboardingStage.CONTEXT_COMPLETE
    if required_planes and len(missing_planes) == len(required_planes):
        return CompanyBrainOnboardingStage.IDENTIFIED
    return CompanyBrainOnboardingStage.PARTIAL


def _unique_planes(planes: tuple[CompanyContextPlane, ...], error: str) -> None:
    if len(planes) != len(set(planes)):
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _SECRET_REF.search(value):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "company_brain_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
