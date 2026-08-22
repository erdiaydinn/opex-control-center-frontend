"""Ask-once, vault-after credential acquisition for Jarvis enterprise sessions.

The user experience target is simple: Jarvis should use an existing managed
credential silently; if an enterprise application genuinely asks for a secret
that Jarvis does not have, it may ask the authenticated user once, enroll the
secret into an approved credential vault, and use only the resulting reference
on future runs.

This contract never persists or serializes the raw secret. A secret may exist
transiently in process memory only long enough to hand it to a trusted vault
adapter. Audit, memory, traces and model context receive references/receipts,
not the secret value.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

CREDENTIAL_ACQUISITION_CONTRACT = "eay-credential-acquisition-v1"


class CredentialKind(str, Enum):
    PASSWORD = "password"


class CredentialState(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    REJECTED = "rejected"
    REVOKED = "revoked"


class CredentialAcquisitionStatus(str, Enum):
    READY = "ready"
    NEEDS_USER_SECRET = "needs_user_secret"
    BLOCKED = "blocked"


class ManagedCredentialObservation(BaseModel):
    application_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    credential_kind: CredentialKind
    credential_scope_ref: str = Field(min_length=1)
    state: CredentialState
    vault_ref: str | None = None
    observed_at: datetime
    rejection_evidence_ref: str | None = None

    @model_validator(mode="after")
    def observation_is_consistent(self) -> "ManagedCredentialObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("credential_observation_requires_timezone")
        if self.state is CredentialState.AVAILABLE and not self.vault_ref:
            raise ValueError("available_credential_requires_vault_ref")
        if self.state is not CredentialState.AVAILABLE and self.vault_ref is not None:
            raise ValueError("unavailable_credential_cannot_claim_vault_ref")
        if self.state in {CredentialState.REJECTED, CredentialState.REVOKED} and not self.rejection_evidence_ref:
            raise ValueError("rejected_or_revoked_credential_requires_evidence")
        return self


class CredentialPersistencePolicy(BaseModel):
    policy_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    credential_scope_ref: str = Field(min_length=1)
    approved_vault_ref: str = Field(min_length=1)
    user_authorized_persistent_enrollment: bool = False
    allow_user_secret_prompt: bool = False
    retry_rejected_secret_without_user: bool = False

    @model_validator(mode="after")
    def policy_never_bruteforces_rejected_credentials(self) -> "CredentialPersistencePolicy":
        if self.retry_rejected_secret_without_user:
            raise ValueError("credential_policy_cannot_retry_rejected_secret_without_user")
        return self


class CredentialAcquisitionPlan(BaseModel):
    contract: str = CREDENTIAL_ACQUISITION_CONTRACT
    application_id: str
    principal_ref: str
    credential_kind: CredentialKind
    credential_scope_ref: str
    status: CredentialAcquisitionStatus
    vault_ref: str | None = None
    user_prompt: str | None = None
    remember_after_capture: bool = False
    blockers: tuple[str, ...] = ()
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def plan_is_secret_safe(self) -> "CredentialAcquisitionPlan":
        if self.secret_value_retained:
            raise ValueError("credential_acquisition_plan_cannot_retain_secret")
        if self.status is CredentialAcquisitionStatus.READY:
            if not self.vault_ref or self.user_prompt or self.blockers:
                raise ValueError("ready_credential_plan_requires_only_vault_ref")
        elif self.status is CredentialAcquisitionStatus.NEEDS_USER_SECRET:
            if not self.user_prompt or self.vault_ref or self.blockers:
                raise ValueError("credential_user_prompt_plan_inconsistent")
        elif not self.blockers:
            raise ValueError("blocked_credential_plan_requires_blocker")
        return self


def plan_credential_acquisition(
    *,
    observation: ManagedCredentialObservation,
    policy: CredentialPersistencePolicy,
    application_display_name: str,
) -> CredentialAcquisitionPlan:
    if observation.application_id != policy.application_id:
        raise ValueError("credential_application_policy_mismatch")
    if observation.principal_ref != policy.principal_ref:
        raise ValueError("credential_principal_policy_mismatch")
    if observation.credential_scope_ref != policy.credential_scope_ref:
        raise ValueError("credential_scope_policy_mismatch")

    if observation.state is CredentialState.AVAILABLE:
        return CredentialAcquisitionPlan(
            application_id=observation.application_id,
            principal_ref=observation.principal_ref,
            credential_kind=observation.credential_kind,
            credential_scope_ref=observation.credential_scope_ref,
            status=CredentialAcquisitionStatus.READY,
            vault_ref=observation.vault_ref,
        )

    if observation.state in {CredentialState.REJECTED, CredentialState.REVOKED}:
        if not policy.allow_user_secret_prompt:
            return CredentialAcquisitionPlan(
                application_id=observation.application_id,
                principal_ref=observation.principal_ref,
                credential_kind=observation.credential_kind,
                credential_scope_ref=observation.credential_scope_ref,
                status=CredentialAcquisitionStatus.BLOCKED,
                blockers=("credential_rejected_or_revoked_user_reentry_not_authorized",),
            )

    if not policy.allow_user_secret_prompt:
        return CredentialAcquisitionPlan(
            application_id=observation.application_id,
            principal_ref=observation.principal_ref,
            credential_kind=observation.credential_kind,
            credential_scope_ref=observation.credential_scope_ref,
            status=CredentialAcquisitionStatus.BLOCKED,
            blockers=("credential_user_secret_prompt_not_authorized",),
        )

    remember = policy.user_authorized_persistent_enrollment
    suffix = (
        " Güvenli kasaya kaydedip sonraki girişlerde tekrar sormayacağım; yalnız şifre değişir veya erişim iptal edilirse yeniden sorarım."
        if remember
        else " Bu oturum için kullanacağım ve kalıcı olarak saklamayacağım."
    )
    return CredentialAcquisitionPlan(
        application_id=observation.application_id,
        principal_ref=observation.principal_ref,
        credential_kind=observation.credential_kind,
        credential_scope_ref=observation.credential_scope_ref,
        status=CredentialAcquisitionStatus.NEEDS_USER_SECRET,
        user_prompt=f"{application_display_name} şifre istedi. Şifreni söyler misin?{suffix}",
        remember_after_capture=remember,
    )


class TransientUserSecret(BaseModel):
    application_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    credential_scope_ref: str = Field(min_length=1)
    credential_kind: CredentialKind
    secret_value: str = Field(min_length=1, exclude=True)
    captured_at: datetime
    must_not_be_persisted_outside_vault: bool = True

    @model_validator(mode="after")
    def transient_secret_is_time_bound_and_nonblank(self) -> "TransientUserSecret":
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("transient_user_secret_requires_timezone")
        if not self.secret_value.strip():
            raise ValueError("transient_user_secret_cannot_be_blank")
        if not self.must_not_be_persisted_outside_vault:
            raise ValueError("user_secret_must_not_be_persisted_outside_vault")
        return self


class VaultEnrollmentReceipt(BaseModel):
    contract: str = CREDENTIAL_ACQUISITION_CONTRACT
    application_id: str
    principal_ref: str
    credential_scope_ref: str
    credential_kind: CredentialKind
    vault_provider_ref: str = Field(min_length=1)
    vault_ref: str = Field(min_length=1)
    enrolled_at: datetime
    enrollment_evidence_ref: str = Field(min_length=1)
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def receipt_never_contains_secret(self) -> "VaultEnrollmentReceipt":
        if self.enrolled_at.tzinfo is None or self.enrolled_at.utcoffset() is None:
            raise ValueError("vault_enrollment_receipt_requires_timezone")
        if self.secret_value_retained:
            raise ValueError("vault_enrollment_receipt_cannot_retain_secret")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_vault_enrollment(
    *,
    transient_secret: TransientUserSecret,
    receipt: VaultEnrollmentReceipt,
    policy: CredentialPersistencePolicy,
) -> str:
    if not policy.user_authorized_persistent_enrollment:
        raise ValueError("persistent_credential_enrollment_not_authorized")
    expected = (
        transient_secret.application_id,
        transient_secret.principal_ref,
        transient_secret.credential_scope_ref,
        transient_secret.credential_kind,
    )
    actual = (
        receipt.application_id,
        receipt.principal_ref,
        receipt.credential_scope_ref,
        receipt.credential_kind,
    )
    if expected != actual:
        raise ValueError("vault_enrollment_identity_or_scope_mismatch")
    if policy.application_id != receipt.application_id or policy.principal_ref != receipt.principal_ref:
        raise ValueError("vault_enrollment_policy_identity_mismatch")
    if policy.credential_scope_ref != receipt.credential_scope_ref:
        raise ValueError("vault_enrollment_policy_scope_mismatch")
    if receipt.vault_provider_ref != policy.approved_vault_ref:
        raise ValueError("vault_enrollment_provider_not_approved")
    return receipt.vault_ref
