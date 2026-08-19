"""Strict per-company context partitioning for EAY Jarvis.

Jarvis Core is shared. Company semantics, policies, memory, capabilities,
calibration and live-source bindings are not. This module binds every
company-scoped artifact to an exact tenant + company + profile revision and
provides time-cutoff-safe snapshots without creating a second truth or
execution authority system.

The boundary is deliberately non-authoritative:
- it never promotes Company World truth;
- it never grants business execution authority;
- it never allows cross-company fallback;
- it never permits company-private artifacts to enter shared model
  distillation through this contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

COMPANY_CONTEXT_BOUNDARY_CONTRACT = "eay-company-context-boundary-v1"

_SECRET_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature)"
)


class CompanyContextPlane(str, Enum):
    KNOWLEDGE = "knowledge"
    TRUTH_BINDING = "truth_binding"
    POLICY = "policy"
    MEMORY = "memory"
    CAPABILITY = "capability"
    CALIBRATION = "calibration"
    MODEL_PROFILE = "model_profile"


class CompanyIdentity(BaseModel):
    contract: str = COMPANY_CONTEXT_BOUNDARY_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    company_slug: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_is_integral(self) -> "CompanyIdentity":
        for value in (
            self.tenant_id,
            self.company_id,
            self.company_slug,
            self.profile_revision,
            self.environment,
        ):
            _safe_ref(value, "company_identity_secret_material_forbidden")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_identity_fingerprint_mismatch")
        return self


class CompanyContextBinding(BaseModel):
    contract: str = COMPANY_CONTEXT_BOUNDARY_CONTRACT
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    company_identity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_revision: str = Field(min_length=1)
    plane: CompanyContextPlane
    artifact_ref: str = Field(min_length=1)
    artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_from: datetime
    observed_at: datetime
    recorded_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    cross_company_reuse_allowed: bool = False
    shared_model_distillation_allowed: bool = False
    firm_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_integral_and_non_authoritative(self) -> "CompanyContextBinding":
        _aware(self.effective_from, "company_context_effective_from_requires_timezone")
        _aware(self.observed_at, "company_context_observed_at_requires_timezone")
        _aware(self.recorded_at, "company_context_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("company_context_recorded_at_predates_observation")
        if self.cross_company_reuse_allowed:
            raise ValueError("company_context_cross_company_reuse_forbidden")
        if self.shared_model_distillation_allowed:
            raise ValueError("company_context_shared_distillation_requires_separate_approval")
        if self.firm_truth_authority_granted:
            raise ValueError("company_context_never_grants_firm_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("company_context_never_grants_execution_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("company_context_evidence_refs_must_be_unique")
        for ref in (self.binding_id, self.artifact_ref, *self.evidence_refs):
            _safe_ref(ref, "company_context_secret_bearing_reference_forbidden")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_context_binding_fingerprint_mismatch")
        return self


class CompanyContextSnapshot(BaseModel):
    contract: str = COMPANY_CONTEXT_BOUNDARY_CONTRACT
    identity: CompanyIdentity
    as_of: datetime
    bindings: tuple[CompanyContextBinding, ...]
    available_planes: tuple[CompanyContextPlane, ...]
    missing_planes: tuple[CompanyContextPlane, ...]
    cross_company_fallback_allowed: bool = False
    firm_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def snapshot_is_exact_and_non_authoritative(self) -> "CompanyContextSnapshot":
        _aware(self.as_of, "company_context_snapshot_as_of_requires_timezone")
        identity = CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if identity.fingerprint != self.identity.fingerprint:
            raise ValueError("company_context_snapshot_identity_integrity_mismatch")
        for binding in self.bindings:
            _validate_exact_identity(binding=binding, identity=identity)
            if binding.effective_from > self.as_of:
                raise ValueError("company_context_snapshot_contains_future_effective_binding")
            if binding.observed_at > self.as_of or binding.recorded_at > self.as_of:
                raise ValueError("company_context_snapshot_contains_future_known_binding")
        if self.cross_company_fallback_allowed:
            raise ValueError("company_context_snapshot_cross_company_fallback_forbidden")
        if self.firm_truth_authority_granted:
            raise ValueError("company_context_snapshot_never_grants_firm_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("company_context_snapshot_never_grants_execution_authority")
        if len(self.available_planes) != len(set(self.available_planes)):
            raise ValueError("company_context_snapshot_duplicate_available_plane")
        if len(self.missing_planes) != len(set(self.missing_planes)):
            raise ValueError("company_context_snapshot_duplicate_missing_plane")
        if set(self.available_planes).intersection(self.missing_planes):
            raise ValueError("company_context_snapshot_plane_overlap")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_context_snapshot_fingerprint_mismatch")
        return self


def build_company_identity(
    *,
    tenant_id: str,
    company_id: str,
    company_slug: str,
    profile_revision: str,
    environment: str,
) -> CompanyIdentity:
    draft = {
        "contract": COMPANY_CONTEXT_BOUNDARY_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "company_slug": company_slug,
        "profile_revision": profile_revision,
        "environment": environment,
    }
    return CompanyIdentity.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_company_context_binding(
    *,
    identity: CompanyIdentity,
    binding_id: str,
    plane: CompanyContextPlane,
    artifact_ref: str,
    artifact_fingerprint: str,
    effective_from: datetime,
    observed_at: datetime,
    recorded_at: datetime,
    evidence_refs: tuple[str, ...],
) -> CompanyContextBinding:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": COMPANY_CONTEXT_BOUNDARY_CONTRACT,
        "binding_id": binding_id,
        "tenant_id": identity.tenant_id,
        "company_id": identity.company_id,
        "company_identity_fingerprint": identity.fingerprint,
        "profile_revision": identity.profile_revision,
        "plane": plane.value,
        "artifact_ref": artifact_ref,
        "artifact_fingerprint": artifact_fingerprint,
        "effective_from": _iso(effective_from),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "evidence_refs": list(evidence_refs),
        "cross_company_reuse_allowed": False,
        "shared_model_distillation_allowed": False,
        "firm_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyContextBinding.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_company_context_snapshot(
    *,
    identity: CompanyIdentity,
    bindings: tuple[CompanyContextBinding, ...],
    as_of: datetime,
    required_planes: tuple[CompanyContextPlane, ...] = (),
) -> CompanyContextSnapshot:
    _aware(as_of, "company_context_snapshot_as_of_requires_timezone")
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    if len(required_planes) != len(set(required_planes)):
        raise ValueError("company_context_required_planes_must_be_unique")

    eligible: list[CompanyContextBinding] = []
    seen_binding_ids: set[str] = set()
    for raw in bindings:
        binding = CompanyContextBinding.model_validate(raw.model_dump(mode="json"))
        _validate_exact_identity(binding=binding, identity=identity)
        if binding.binding_id in seen_binding_ids:
            raise ValueError("company_context_duplicate_binding_id")
        seen_binding_ids.add(binding.binding_id)
        if (
            binding.effective_from <= as_of
            and binding.observed_at <= as_of
            and binding.recorded_at <= as_of
        ):
            eligible.append(binding)

    available = tuple(
        sorted({item.plane for item in eligible}, key=lambda item: item.value)
    )
    missing = tuple(item for item in required_planes if item not in available)
    draft = {
        "contract": COMPANY_CONTEXT_BOUNDARY_CONTRACT,
        "identity": identity.model_dump(mode="json"),
        "as_of": _iso(as_of),
        "bindings": [item.model_dump(mode="json") for item in eligible],
        "available_planes": [item.value for item in available],
        "missing_planes": [item.value for item in missing],
        "cross_company_fallback_allowed": False,
        "firm_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyContextSnapshot.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def require_company_plane(
    *,
    snapshot: CompanyContextSnapshot,
    plane: CompanyContextPlane,
) -> tuple[CompanyContextBinding, ...]:
    snapshot = CompanyContextSnapshot.model_validate(snapshot.model_dump(mode="json"))
    matches = tuple(item for item in snapshot.bindings if item.plane is plane)
    if not matches:
        raise ValueError(f"company_context_plane_missing:{plane.value}")
    return matches


def has_company_artifact(
    *,
    snapshot: CompanyContextSnapshot,
    plane: CompanyContextPlane,
    artifact_ref: str,
) -> bool:
    snapshot = CompanyContextSnapshot.model_validate(snapshot.model_dump(mode="json"))
    _safe_ref(artifact_ref, "company_context_secret_bearing_reference_forbidden")
    return any(
        item.plane is plane and item.artifact_ref == artifact_ref
        for item in snapshot.bindings
    )


def _validate_exact_identity(
    *,
    binding: CompanyContextBinding,
    identity: CompanyIdentity,
) -> None:
    if binding.tenant_id != identity.tenant_id:
        raise ValueError("company_context_cross_tenant_binding")
    if binding.company_id != identity.company_id:
        raise ValueError("company_context_cross_company_binding")
    if binding.company_identity_fingerprint != identity.fingerprint:
        raise ValueError("company_context_identity_fingerprint_mismatch")
    if binding.profile_revision != identity.profile_revision:
        raise ValueError("company_context_profile_revision_mismatch")


def _safe_ref(value: str, error: str) -> None:
    if _SECRET_REF.search(value):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "company_context_datetime_requires_timezone")
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
