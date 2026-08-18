from datetime import datetime, timezone

from app.credential_acquisition import CredentialPersistencePolicy
from app.credential_vault_adapter import NativeCredentialVault
from app.enterprise_auth_runtime import enroll_user_password_and_resume, resolve_enterprise_auth
from app.okta_auth_orchestration import OktaAuthMethod, OktaAuthenticationPolicy, OktaChallengeObservation
from app.okta_credential_bootstrap import OktaCredentialBootstrapStatus

NOW = datetime(2026, 8, 18, 8, 55, tzinfo=timezone.utc)


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def set_password(self, service_name, username, password):
        self.values[(service_name, username)] = password

    def get_password(self, service_name, username):
        return self.values.get((service_name, username))

    def delete_password(self, service_name, username):
        self.values.pop((service_name, username), None)


def _challenge():
    return OktaChallengeObservation(
        application_id="carsi-portal",
        auth_context_ref="auth:carsi:erdi",
        challenge_ref="challenge:okta:1",
        observed_at=NOW,
        available_methods=(OktaAuthMethod.EMAIL_OTP,),
        password_required_before_email_otp=True,
    )


def _auth_policy():
    return OktaAuthenticationPolicy(
        policy_id="okta:carsi:v1",
        application_id="carsi-portal",
        allowed_methods=frozenset({OktaAuthMethod.EMAIL_OTP}),
        mailbox_connector_ref="gmail:authorized:erdi",
        mailbox_sender_domains=frozenset({"okta.com", "yemeksepeti.com"}),
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


def test_first_missing_password_asks_once_then_enrolls_and_future_run_is_silent():
    vault = NativeCredentialVault(backend=FakeKeyring())

    first = resolve_enterprise_auth(
        challenge=_challenge(),
        auth_policy=_auth_policy(),
        credential_policy=_credential_policy(),
        vault=vault,
        application_display_name="ÇarşıPortal",
        now=NOW,
    )
    assert first.bootstrap.status is OktaCredentialBootstrapStatus.NEEDS_USER_SECRET
    assert "Şifreni söyler misin" in first.user_prompt

    resumed = enroll_user_password_and_resume(
        raw_password="USER-PROVIDED-ONCE",
        challenge=_challenge(),
        auth_policy=_auth_policy(),
        credential_policy=_credential_policy(),
        vault=vault,
        application_display_name="ÇarşıPortal",
        now=NOW,
    )
    assert resumed.bootstrap.status is OktaCredentialBootstrapStatus.AUTH_READY
    assert resumed.user_prompt is None
    assert resumed.credential_enrollment_ref.startswith("vault-item:keyring:")
    assert "USER-PROVIDED-ONCE" not in resumed.model_dump_json()

    later = resolve_enterprise_auth(
        challenge=_challenge(),
        auth_policy=_auth_policy(),
        credential_policy=_credential_policy(),
        vault=vault,
        application_display_name="ÇarşıPortal",
        now=NOW,
    )
    assert later.bootstrap.status is OktaCredentialBootstrapStatus.AUTH_READY
    assert later.user_prompt is None
    assert later.bootstrap.auth_plan.selected_method is OktaAuthMethod.EMAIL_OTP
    password_steps = [step for step in later.bootstrap.auth_plan.steps if step.secret_ref]
    assert len(password_steps) == 1
    assert password_steps[0].secret_ref.startswith("vault-item:keyring:")
