from datetime import datetime, timezone

from app.credential_acquisition import (
    CredentialKind,
    CredentialPersistencePolicy,
    CredentialState,
    ManagedCredentialObservation,
)
from app.okta_auth_orchestration import (
    OktaAuthMethod,
    OktaAuthenticationPolicy,
    OktaChallengeObservation,
)
from app.okta_credential_bootstrap import (
    OktaCredentialBootstrapStatus,
    plan_okta_with_credential_bootstrap,
)

NOW = datetime(2026, 8, 18, 8, 45, tzinfo=timezone.utc)


def _challenge():
    return OktaChallengeObservation(
        application_id="carsi-portal",
        auth_context_ref="auth:carsi:erdi",
        challenge_ref="challenge:okta:1",
        observed_at=NOW,
        available_methods=(OktaAuthMethod.EMAIL_OTP,),
        password_required_before_email_otp=True,
    )


def _auth_policy(*, credential_vault_ref=None):
    return OktaAuthenticationPolicy(
        policy_id="okta:carsi:v1",
        application_id="carsi-portal",
        allowed_methods=frozenset({OktaAuthMethod.EMAIL_OTP}),
        credential_vault_ref=credential_vault_ref,
        mailbox_connector_ref="gmail:authorized:erdi",
        mailbox_sender_domains=frozenset({"okta.com", "yemeksepeti.com"}),
        prefer_phishing_resistant=True,
        allow_email_otp_automation=True,
    )


def _credential_policy():
    return CredentialPersistencePolicy(
        policy_id="carsi-password-v1",
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        approved_vault_ref="vault:eay-enterprise-credentials",
        user_authorized_persistent_enrollment=True,
        allow_user_secret_prompt=True,
    )


def _observation(state: CredentialState, *, vault_ref=None):
    return ManagedCredentialObservation(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        state=state,
        vault_ref=vault_ref,
        observed_at=NOW,
    )


def test_okta_missing_password_becomes_user_secret_request_instead_of_dead_end():
    plan = plan_okta_with_credential_bootstrap(
        challenge=_challenge(),
        auth_policy=_auth_policy(),
        credential_observation=_observation(CredentialState.MISSING),
        credential_policy=_credential_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is OktaCredentialBootstrapStatus.NEEDS_USER_SECRET
    assert plan.credential_plan is not None
    assert "ÇarşıPortal şifre istedi" in plan.credential_plan.user_prompt
    assert "okta_password_vault_ref_missing" in plan.auth_plan.blockers


def test_okta_existing_vault_password_replans_to_ready_without_prompt():
    plan = plan_okta_with_credential_bootstrap(
        challenge=_challenge(),
        auth_policy=_auth_policy(),
        credential_observation=_observation(
            CredentialState.AVAILABLE,
            vault_ref="vault-item:carsi:erdi",
        ),
        credential_policy=_credential_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is OktaCredentialBootstrapStatus.AUTH_READY
    assert plan.credential_plan is None
    assert plan.auth_plan.selected_method is OktaAuthMethod.EMAIL_OTP
    password_steps = [step for step in plan.auth_plan.steps if step.secret_ref]
    assert len(password_steps) == 1
    assert password_steps[0].secret_ref == "vault-item:carsi:erdi"
    assert plan.secret_value_retained is False


def test_existing_authenticated_session_never_prompts_for_password():
    challenge = _challenge().model_copy(
        update={"existing_session_authenticated": True, "available_methods": ()}
    )
    plan = plan_okta_with_credential_bootstrap(
        challenge=challenge,
        auth_policy=_auth_policy(),
        credential_observation=_observation(CredentialState.MISSING),
        credential_policy=_credential_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is OktaCredentialBootstrapStatus.AUTH_READY
    assert plan.auth_plan.selected_method is OktaAuthMethod.EXISTING_SESSION
    assert plan.credential_plan is None
