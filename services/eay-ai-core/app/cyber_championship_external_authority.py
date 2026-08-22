"""External authority admission for real EAY cyber championship runs.

This module verifies independent evaluator authority and vendor credential bindings
without storing sealed answers or raw credentials. It admits a real-run control
plane only when the sealed bank, sandbox, evaluator and all required vendor
authorizations are exact, current, read-only and mutually bound.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_championship_execution import (
    CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
    ChampionshipSandboxAuthorization,
    CompetitorKind,
    SealedTaskBankReceipt,
)
from app.cyber_championship_vendor_adapters import (
    CompetitorAdapterSpec,
    CompetitorRunnerAuthorization,
    RunnerAuthorityStatus,
    assess_runner_authority,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_REF_SCHEMES = ("vault://", "secret-manager://", "key-vault://")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key(?:[-_: ]|$)|password|passwd|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"session[_-]?(?:token|cookie)(?:[-_: ]|$)|signed[_-]?url|"
    r"x-goog-signature|x-amz-signature|private[_-]?key)"
)
_REQUIRED_VENDORS = frozenset(
    {
        CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI,
        CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI,
        CompetitorKind.MICROSOFT_SECURITY_COPILOT,
    }
)


class VendorPreflightStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class ExternalAdmissionStatus(str, Enum):
    EXTERNAL_AUTHORITY_REQUIRED = "external_authority_required"
    READY_FOR_REAL_RUNS = "ready_for_real_runs"


class TrustedEvaluatorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trusted_issuer_refs: tuple[str, ...] = Field(min_length=1)
    trusted_key_fingerprints: tuple[str, ...] = Field(min_length=1)
    forbidden_competitor_org_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def policy_is_safe(self) -> TrustedEvaluatorPolicy:
        _unique(self.trusted_issuer_refs, "evaluator_policy_issuer_refs_duplicate")
        _unique(
            self.trusted_key_fingerprints,
            "evaluator_policy_key_fingerprints_duplicate",
        )
        _unique(
            self.forbidden_competitor_org_refs,
            "evaluator_policy_competitor_org_refs_duplicate",
        )
        for value in (*self.trusted_issuer_refs, *self.forbidden_competitor_org_refs):
            _safe_ref(value, "evaluator_policy_ref_unsafe")
        for value in self.trusted_key_fingerprints:
            if not _SHA256.fullmatch(value):
                raise ValueError("evaluator_policy_key_fingerprint_invalid")
        return self


class ExternalEvaluatorAuthorityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    evaluator_org_ref: str = Field(min_length=1)
    evaluator_identity_ref: str = Field(min_length=1)
    trusted_issuer_ref: str = Field(min_length=1)
    evaluator_signing_key_id: str = Field(min_length=1)
    evaluator_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bank_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bank_independent_provider_ref: str = Field(min_length=1)
    bank_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_ground_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rotation_epoch: str = Field(min_length=1)
    sealed_storage_ref: str = Field(min_length=1)
    authority_evidence_ref: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    independent_of_all_competitors: bool
    raw_ground_truth_in_receipt: bool = False
    private_key_material_present: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def evaluator_authority_is_sealed(self) -> ExternalEvaluatorAuthorityReceipt:
        _aware(self.issued_at, "evaluator_authority_issued_at_requires_timezone")
        _aware(self.expires_at, "evaluator_authority_expires_at_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("evaluator_authority_expiry_invalid")
        if (
            not self.independent_of_all_competitors
            or self.raw_ground_truth_in_receipt
            or self.private_key_material_present
        ):
            raise ValueError("evaluator_authority_boundary_violated")
        for value in (
            self.evaluator_org_ref,
            self.evaluator_identity_ref,
            self.trusted_issuer_ref,
            self.evaluator_signing_key_id,
            self.bank_independent_provider_ref,
            self.rotation_epoch,
            self.sealed_storage_ref,
            self.authority_evidence_ref,
        ):
            _safe_ref(value, "evaluator_authority_ref_unsafe")
        _verify(self, "evaluator_authority_fingerprint_mismatch")
        return self


class ExternalEvaluatorVerificationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    bank_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_at: datetime
    issuer_trusted: bool
    signing_key_trusted: bool
    competitor_independence_verified: bool
    bank_binding_verified: bool
    ground_truth_disclosed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verification_is_integral(self) -> ExternalEvaluatorVerificationReceipt:
        _aware(self.verified_at, "evaluator_verification_time_requires_timezone")
        if (
            not self.issuer_trusted
            or not self.signing_key_trusted
            or not self.competitor_independence_verified
            or not self.bank_binding_verified
            or self.ground_truth_disclosed
        ):
            raise ValueError("evaluator_verification_not_admissible")
        _verify(self, "evaluator_verification_fingerprint_mismatch")
        return self


class VendorCredentialBindingReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    organization_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    resource_ref: str = Field(min_length=1)
    workload_identity_ref: str = Field(min_length=1)
    credential_ref: str = Field(min_length=1)
    authorization_evidence_ref: str = Field(min_length=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_operation_refs: tuple[str, ...] = Field(min_length=1)
    authorized_at: datetime
    expires_at: datetime
    competition_use_authorized: bool
    read_only_scope_verified: bool
    identity_verified: bool
    raw_secret_material_present: bool = False
    write_or_admin_scope_present: bool = False
    production_mutation_authority: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def vendor_binding_is_bounded(self) -> VendorCredentialBindingReceipt:
        _aware(self.authorized_at, "vendor_binding_time_requires_timezone")
        _aware(self.expires_at, "vendor_binding_expiry_requires_timezone")
        if self.expires_at <= self.authorized_at:
            raise ValueError("vendor_binding_expiry_invalid")
        if self.competitor is CompetitorKind.JARVIS:
            raise ValueError("vendor_binding_vendor_required")
        if self.competitor not in _REQUIRED_VENDORS:
            raise ValueError("vendor_binding_unknown_competitor")
        if (
            not self.competition_use_authorized
            or not self.read_only_scope_verified
            or not self.identity_verified
            or self.raw_secret_material_present
            or self.write_or_admin_scope_present
            or self.production_mutation_authority
        ):
            raise ValueError("vendor_binding_authority_boundary_violated")
        if not self.credential_ref.startswith(_SECRET_REF_SCHEMES):
            raise ValueError("vendor_binding_requires_secret_manager_reference")
        _unique(self.allowed_operation_refs, "vendor_binding_operation_refs_duplicate")
        for value in (
            self.organization_ref,
            self.tenant_ref,
            self.resource_ref,
            self.workload_identity_ref,
            self.credential_ref,
            self.authorization_evidence_ref,
            *self.allowed_operation_refs,
        ):
            _safe_ref(value, "vendor_binding_ref_unsafe")
        _verify(self, "vendor_binding_fingerprint_mismatch")
        return self


class VendorPreflightReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    authorization_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    sandbox_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    checked_at: datetime
    status: VendorPreflightStatus
    blockers: tuple[str, ...] = ()
    raw_credentials_observed: bool = False
    production_mutation_authority: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def preflight_is_consistent(self) -> VendorPreflightReceipt:
        _aware(self.checked_at, "vendor_preflight_time_requires_timezone")
        if self.raw_credentials_observed or self.production_mutation_authority:
            raise ValueError("vendor_preflight_forbidden_authority")
        if self.status is VendorPreflightStatus.READY and self.blockers:
            raise ValueError("vendor_preflight_ready_cannot_have_blockers")
        if self.status is VendorPreflightStatus.BLOCKED and not self.blockers:
            raise ValueError("vendor_preflight_blocked_requires_reason")
        _verify(self, "vendor_preflight_fingerprint_mismatch")
        return self


class ExternalChampionshipAdmissionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    status: ExternalAdmissionStatus
    bank_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    sandbox_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evaluator_verification_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    vendor_preflight_fingerprints: tuple[str, ...] = ()
    blockers: tuple[str, ...]
    real_race_executed: bool = False
    verified_leader_claim_allowed: bool = False
    production_security_superiority_claim_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def admission_is_truthful(self) -> ExternalChampionshipAdmissionReceipt:
        if (
            self.real_race_executed
            or self.verified_leader_claim_allowed
            or self.production_security_superiority_claim_allowed
        ):
            raise ValueError("external_admission_cannot_claim_race_outcome")
        if self.status is ExternalAdmissionStatus.READY_FOR_REAL_RUNS and self.blockers:
            raise ValueError("external_admission_ready_cannot_have_blockers")
        if (
            self.status is ExternalAdmissionStatus.EXTERNAL_AUTHORITY_REQUIRED
            and not self.blockers
        ):
            raise ValueError("external_admission_blocked_requires_reason")
        _unique(
            self.vendor_preflight_fingerprints,
            "external_admission_vendor_preflight_fingerprints_duplicate",
        )
        _verify(self, "external_admission_fingerprint_mismatch")
        return self


def verify_external_bank_authority(
    *,
    bank: SealedTaskBankReceipt,
    authority: ExternalEvaluatorAuthorityReceipt,
    policy: TrustedEvaluatorPolicy,
    now: datetime,
) -> ExternalEvaluatorVerificationReceipt:
    bank = SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
    authority = ExternalEvaluatorAuthorityReceipt.model_validate(
        authority.model_dump(mode="json")
    )
    policy = TrustedEvaluatorPolicy.model_validate(policy.model_dump(mode="json"))
    _aware(now, "evaluator_verification_time_requires_timezone")
    if now < authority.issued_at or now >= authority.expires_at:
        raise ValueError("evaluator_authority_not_current")
    if authority.trusted_issuer_ref not in policy.trusted_issuer_refs:
        raise ValueError("evaluator_authority_issuer_untrusted")
    if authority.evaluator_key_fingerprint not in policy.trusted_key_fingerprints:
        raise ValueError("evaluator_authority_signing_key_untrusted")
    if authority.evaluator_org_ref in policy.forbidden_competitor_org_refs:
        raise ValueError("evaluator_authority_competitor_independence_failed")
    bindings = (
        authority.bank_fingerprint == bank.fingerprint,
        authority.bank_independent_provider_ref == bank.independent_provider_ref,
        authority.bank_manifest_sha256 == bank.public_manifest_sha256,
        authority.task_set_fingerprint == bank.task_set_fingerprint,
        authority.sealed_ground_truth_sha256 == bank.sealed_ground_truth_sha256,
        authority.rotation_epoch == bank.rotation_epoch,
        authority.sealed_storage_ref == bank.sealed_storage_ref,
        authority.evaluator_signing_key_id == bank.evaluator_key_id,
    )
    if not all(bindings):
        raise ValueError("evaluator_authority_bank_binding_mismatch")
    return _seal_model(
        ExternalEvaluatorVerificationReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "bank_fingerprint": bank.fingerprint,
            "authority_fingerprint": authority.fingerprint,
            "verified_at": now,
            "issuer_trusted": True,
            "signing_key_trusted": True,
            "competitor_independence_verified": True,
            "bank_binding_verified": True,
            "ground_truth_disclosed": False,
        },
    )


def preflight_vendor_binding(
    *,
    adapter: CompetitorAdapterSpec,
    authorization: CompetitorRunnerAuthorization,
    binding: VendorCredentialBindingReceipt,
    sandbox: ChampionshipSandboxAuthorization,
    now: datetime,
) -> VendorPreflightReceipt:
    sandbox = ChampionshipSandboxAuthorization.model_validate(
        sandbox.model_dump(mode="json")
    )
    authorization = CompetitorRunnerAuthorization.model_validate(
        authorization.model_dump(mode="json")
    )
    binding = VendorCredentialBindingReceipt.model_validate(binding.model_dump(mode="json"))
    status, blockers = assess_runner_authority(
        adapter=adapter,
        authorization=authorization,
        now=now,
    )
    failures = list(blockers)
    if status is RunnerAuthorityStatus.READY:
        if binding.competitor is not adapter.competitor:
            failures.append("vendor_binding_adapter_mismatch")
        if binding.competitor is not authorization.competitor:
            failures.append("vendor_binding_authorization_mismatch")
        if binding.organization_ref != authorization.organization_ref:
            failures.append("vendor_binding_organization_mismatch")
        if binding.workload_identity_ref not in authorization.identity_binding_refs:
            failures.append("vendor_binding_identity_mismatch")
        if binding.resource_ref not in authorization.resource_binding_refs:
            failures.append("vendor_binding_resource_mismatch")
        if binding.environment_fingerprint != sandbox.environment_fingerprint:
            failures.append("vendor_binding_environment_mismatch")
        if now < binding.authorized_at or now >= binding.expires_at:
            failures.append("vendor_binding_not_current")
    else:
        failures.append(f"vendor_runner_authority_status:{status.value}")
    unique_failures = tuple(dict.fromkeys(failures))
    return _seal_model(
        VendorPreflightReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "competitor": adapter.competitor,
            "authorization_fingerprint": authorization.fingerprint,
            "credential_binding_fingerprint": binding.fingerprint,
            "sandbox_fingerprint": sandbox.fingerprint,
            "checked_at": now,
            "status": (
                VendorPreflightStatus.BLOCKED
                if unique_failures
                else VendorPreflightStatus.READY
            ),
            "blockers": unique_failures,
            "raw_credentials_observed": False,
            "production_mutation_authority": False,
        },
    )


def assess_external_championship_admission(
    *,
    bank: SealedTaskBankReceipt | None,
    sandbox: ChampionshipSandboxAuthorization | None,
    evaluator_verification: ExternalEvaluatorVerificationReceipt | None,
    vendor_preflights: tuple[VendorPreflightReceipt, ...] = (),
) -> ExternalChampionshipAdmissionReceipt:
    blockers: list[str] = []
    if bank is None:
        blockers.append("external_independent_sealed_bank_missing")
    else:
        bank = SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
    if sandbox is None:
        blockers.append("external_authorized_sandbox_missing")
    else:
        sandbox = ChampionshipSandboxAuthorization.model_validate(
            sandbox.model_dump(mode="json")
        )
    if evaluator_verification is None:
        blockers.append("external_evaluator_verification_missing")
    else:
        evaluator_verification = ExternalEvaluatorVerificationReceipt.model_validate(
            evaluator_verification.model_dump(mode="json")
        )
        if bank is not None and evaluator_verification.bank_fingerprint != bank.fingerprint:
            blockers.append("external_evaluator_bank_binding_mismatch")

    validated = tuple(
        VendorPreflightReceipt.model_validate(item.model_dump(mode="json"))
        for item in vendor_preflights
    )
    competitors = {
        item.competitor
        for item in validated
        if item.status is VendorPreflightStatus.READY
    }
    if competitors != _REQUIRED_VENDORS:
        blockers.append("external_all_vendor_preflights_not_ready")
    if any(item.status is VendorPreflightStatus.BLOCKED for item in validated):
        blockers.append("external_vendor_preflight_blocked")
    if len(validated) != len(_REQUIRED_VENDORS):
        blockers.append("external_vendor_preflight_count_incomplete")
    if len({item.competitor for item in validated}) != len(validated):
        blockers.append("external_vendor_preflight_duplicate_competitor")
    if sandbox is not None and any(
        item.sandbox_fingerprint != sandbox.fingerprint for item in validated
    ):
        blockers.append("external_vendor_preflight_sandbox_mismatch")

    unique_blockers = tuple(dict.fromkeys(blockers))
    status = (
        ExternalAdmissionStatus.EXTERNAL_AUTHORITY_REQUIRED
        if unique_blockers
        else ExternalAdmissionStatus.READY_FOR_REAL_RUNS
    )
    return _seal_model(
        ExternalChampionshipAdmissionReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "status": status,
            "bank_fingerprint": bank.fingerprint if bank is not None else None,
            "sandbox_fingerprint": sandbox.fingerprint if sandbox is not None else None,
            "evaluator_verification_fingerprint": (
                evaluator_verification.fingerprint
                if evaluator_verification is not None
                else None
            ),
            "vendor_preflight_fingerprints": tuple(
                sorted(item.fingerprint for item in validated)
            ),
            "blockers": unique_blockers,
            "real_race_executed": False,
            "verified_leader_claim_allowed": False,
            "production_security_superiority_claim_allowed": False,
        },
    )


def _unique(values: tuple[Any, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal_model(model_cls: type[BaseModel], values: dict[str, Any]):
    draft = model_cls.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
