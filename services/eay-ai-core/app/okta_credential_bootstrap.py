"""Compose Okta authentication with ask-once credential bootstrap.

The Okta planner remains the source of truth for authentication method order.
This layer only handles one recoverable blocker: a password is genuinely
required before an authorized email-OTP flow, but no managed password vault
reference exists yet. In that case Jarvis can ask the authenticated user once,
enroll the supplied secret into an approved vault, and re-plan using only the
vault reference.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .credential_acquisition import (
    CredentialAcquisitionPlan,
    CredentialAcquisitionStatus,
    CredentialPersistencePolicy,
    ManagedCredentialObservation,
    plan_credential_acquisition,
)
from .okta_auth_orchestration import (
    OktaAuthPlan,
    OktaAuthPlanStatus,
    OktaAuthenticationPolicy,
    OktaChallengeObservation,
    plan_okta_authentication,
)

OKTA_CREDENTIAL_BOOTSTRAP_CONTRACT = "eay-okta-credential-bootstrap-v1"


class OktaCredentialBootstrapStatus(str, Enum):
    AUTH_READY = "auth_ready"
    NEEDS_USER_SECRET = "needs_user_secret"
    BLOCKED = "blocked"


class OktaCredentialBootstrapPlan(BaseModel):
    contract: str = OKTA_CREDENTIAL_BOOTSTRAP_CONTRACT
    application_id: str = Field(min_length=1)
    status: OktaCredentialBootstrapStatus
    auth_plan: OktaAuthPlan
    credential_plan: CredentialAcquisitionPlan | None = None
    blockers: tuple[str, ...] = ()
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def composition_is_consistent(self) -> "OktaCredentialBootstrapPlan":
        if self.secret_value_retained:
            raise ValueError("okta_credential_bootstrap_cannot_retain_secret")
        if self.status is OktaCredentialBootstrapStatus.AUTH_READY:
            if self.auth_plan.status is not OktaAuthPlanStatus.READY or self.credential_plan is not None or self.blockers:
                raise ValueError("okta_credential_bootstrap_ready_state_inconsistent")
        elif self.status is OktaCredentialBootstrapStatus.NEEDS_USER_SECRET:
            if self.credential_plan is None or self.credential_plan.status is not CredentialAcquisitionStatus.NEEDS_USER_SECRET:
                raise ValueError("okta_credential_bootstrap_user_secret_plan_required")
            if self.blockers:
                raise ValueError("okta_credential_bootstrap_user_secret_state_cannot_have_blockers")
        elif not self.blockers:
            raise ValueError("okta_credential_bootstrap_blocked_requires_blocker")
        return self


def plan_okta_with_credential_bootstrap(
    *,
    challenge: OktaChallengeObservation,
    auth_policy: OktaAuthenticationPolicy,
    credential_observation: ManagedCredentialObservation,
    credential_policy: CredentialPersistencePolicy,
    application_display_name: str,
) -> OktaCredentialBootstrapPlan:
    auth_plan = plan_okta_authentication(challenge=challenge, policy=auth_policy)
    if auth_plan.status is OktaAuthPlanStatus.READY:
        return OktaCredentialBootstrapPlan(
            application_id=challenge.application_id,
            status=OktaCredentialBootstrapStatus.AUTH_READY,
            auth_plan=auth_plan,
        )

    password_missing = "okta_password_vault_ref_missing" in auth_plan.blockers
    other_blockers = tuple(item for item in auth_plan.blockers if item != "okta_password_vault_ref_missing")
    if not password_missing:
        return OktaCredentialBootstrapPlan(
            application_id=challenge.application_id,
            status=OktaCredentialBootstrapStatus.BLOCKED,
            auth_plan=auth_plan,
            blockers=auth_plan.blockers,
        )
    if other_blockers:
        return OktaCredentialBootstrapPlan(
            application_id=challenge.application_id,
            status=OktaCredentialBootstrapStatus.BLOCKED,
            auth_plan=auth_plan,
            blockers=other_blockers,
        )

    credential_plan = plan_credential_acquisition(
        observation=credential_observation,
        policy=credential_policy,
        application_display_name=application_display_name,
    )
    if credential_plan.status is CredentialAcquisitionStatus.READY:
        replanned_policy = auth_policy.model_copy(update={"credential_vault_ref": credential_plan.vault_ref})
        replanned = plan_okta_authentication(challenge=challenge, policy=replanned_policy)
        if replanned.status is not OktaAuthPlanStatus.READY:
            return OktaCredentialBootstrapPlan(
                application_id=challenge.application_id,
                status=OktaCredentialBootstrapStatus.BLOCKED,
                auth_plan=replanned,
                credential_plan=credential_plan,
                blockers=replanned.blockers or ("okta_auth_replan_failed_after_credential_resolution",),
            )
        return OktaCredentialBootstrapPlan(
            application_id=challenge.application_id,
            status=OktaCredentialBootstrapStatus.AUTH_READY,
            auth_plan=replanned,
        )

    if credential_plan.status is CredentialAcquisitionStatus.NEEDS_USER_SECRET:
        return OktaCredentialBootstrapPlan(
            application_id=challenge.application_id,
            status=OktaCredentialBootstrapStatus.NEEDS_USER_SECRET,
            auth_plan=auth_plan,
            credential_plan=credential_plan,
        )

    return OktaCredentialBootstrapPlan(
        application_id=challenge.application_id,
        status=OktaCredentialBootstrapStatus.BLOCKED,
        auth_plan=auth_plan,
        credential_plan=credential_plan,
        blockers=credential_plan.blockers,
    )
