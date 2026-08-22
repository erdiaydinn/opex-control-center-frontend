"""Runtime composition for ask-once enterprise authentication.

This is the user-facing behavior boundary: inspect the approved credential
vault, plan the live Okta challenge, ask the authenticated user only when a
required password is genuinely missing/rejected, enroll a supplied password
into the approved vault, then automatically re-plan without exposing the raw
secret to durable state.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .credential_acquisition import (
    CredentialKind,
    CredentialPersistencePolicy,
    TransientUserSecret,
    validate_vault_enrollment,
)
from .credential_vault_adapter import NativeCredentialVault
from .okta_auth_orchestration import OktaAuthenticationPolicy, OktaChallengeObservation
from .okta_credential_bootstrap import (
    OktaCredentialBootstrapPlan,
    OktaCredentialBootstrapStatus,
    plan_okta_with_credential_bootstrap,
)

ENTERPRISE_AUTH_RUNTIME_CONTRACT = "eay-enterprise-auth-runtime-v1"


class EnterpriseAuthRuntimeResult(BaseModel):
    contract: str = ENTERPRISE_AUTH_RUNTIME_CONTRACT
    application_id: str = Field(min_length=1)
    bootstrap: OktaCredentialBootstrapPlan
    user_prompt: str | None = None
    credential_enrollment_ref: str | None = None
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def runtime_result_is_secret_safe(self) -> "EnterpriseAuthRuntimeResult":
        if self.secret_value_retained:
            raise ValueError("enterprise_auth_runtime_cannot_retain_secret")
        if self.bootstrap.status is OktaCredentialBootstrapStatus.NEEDS_USER_SECRET:
            if not self.user_prompt:
                raise ValueError("enterprise_auth_runtime_user_prompt_required")
        elif self.user_prompt is not None:
            raise ValueError("enterprise_auth_runtime_prompt_only_when_secret_needed")
        return self


def resolve_enterprise_auth(
    *,
    challenge: OktaChallengeObservation,
    auth_policy: OktaAuthenticationPolicy,
    credential_policy: CredentialPersistencePolicy,
    vault: NativeCredentialVault,
    application_display_name: str,
    now: datetime,
) -> EnterpriseAuthRuntimeResult:
    observation = vault.observe(
        application_id=credential_policy.application_id,
        principal_ref=credential_policy.principal_ref,
        credential_scope_ref=credential_policy.credential_scope_ref,
        credential_kind=CredentialKind.PASSWORD,
        now=now,
    )
    bootstrap = plan_okta_with_credential_bootstrap(
        challenge=challenge,
        auth_policy=auth_policy,
        credential_observation=observation,
        credential_policy=credential_policy,
        application_display_name=application_display_name,
    )
    prompt = None
    if bootstrap.status is OktaCredentialBootstrapStatus.NEEDS_USER_SECRET:
        prompt = bootstrap.credential_plan.user_prompt if bootstrap.credential_plan else None
    return EnterpriseAuthRuntimeResult(
        application_id=challenge.application_id,
        bootstrap=bootstrap,
        user_prompt=prompt,
    )


def enroll_user_password_and_resume(
    *,
    raw_password: str,
    challenge: OktaChallengeObservation,
    auth_policy: OktaAuthenticationPolicy,
    credential_policy: CredentialPersistencePolicy,
    vault: NativeCredentialVault,
    application_display_name: str,
    now: datetime,
) -> EnterpriseAuthRuntimeResult:
    if not credential_policy.user_authorized_persistent_enrollment:
        raise ValueError("enterprise_auth_persistent_password_enrollment_not_authorized")
    transient = TransientUserSecret(
        application_id=credential_policy.application_id,
        principal_ref=credential_policy.principal_ref,
        credential_scope_ref=credential_policy.credential_scope_ref,
        credential_kind=CredentialKind.PASSWORD,
        secret_value=raw_password,
        captured_at=now,
    )
    receipt = vault.enroll(transient, now=now)
    vault_ref = validate_vault_enrollment(
        transient_secret=transient,
        receipt=receipt,
        policy=credential_policy,
    )
    resolved = resolve_enterprise_auth(
        challenge=challenge,
        auth_policy=auth_policy,
        credential_policy=credential_policy,
        vault=vault,
        application_display_name=application_display_name,
        now=now,
    )
    if resolved.bootstrap.status is not OktaCredentialBootstrapStatus.AUTH_READY:
        raise RuntimeError("enterprise_auth_not_ready_after_credential_enrollment")
    return resolved.model_copy(update={"credential_enrollment_ref": vault_ref})
