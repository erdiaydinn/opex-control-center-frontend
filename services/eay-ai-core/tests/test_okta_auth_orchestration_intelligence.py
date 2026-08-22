from datetime import datetime, timedelta, timezone

import pytest

from app.okta_auth_orchestration import (
    EmailOtpExtractionPolicy,
    MailboxOtpMessage,
    OktaAuthMethod,
    OktaAuthenticationPolicy,
    OktaAuthPlanStatus,
    OktaAuthStepKind,
    OktaChallengeObservation,
    extract_email_otp,
    plan_okta_authentication,
)


NOW = datetime(2026, 8, 18, 8, 20, tzinfo=timezone.utc)
APP = "yemeksepeti-carsi-portal"


def _challenge(**overrides):
    payload = dict(
        application_id=APP,
        auth_context_ref="auth://managed-okta-session",
        challenge_ref="okta-challenge://carsi/1",
        observed_at=NOW,
        available_methods=(
            OktaAuthMethod.FASTPASS,
            OktaAuthMethod.PASSKEY_WEBAUTHN,
            OktaAuthMethod.EMAIL_OTP,
        ),
    )
    payload.update(overrides)
    return OktaChallengeObservation(**payload)


def _email_policy(**overrides):
    payload = dict(
        policy_id="policy://carsi-okta",
        application_id=APP,
        credential_vault_ref="vault://corporate/carsi-password",
        mailbox_connector_ref="mailbox://corporate-inbox",
        mailbox_sender_domains=frozenset({"okta.example.com"}),
        allow_email_otp_automation=True,
    )
    payload.update(overrides)
    return OktaAuthenticationPolicy(**payload)


def test_existing_managed_session_is_always_preferred_without_secret_steps():
    plan = plan_okta_authentication(
        challenge=_challenge(existing_session_authenticated=True),
        policy=_email_policy(),
    )

    assert plan.status is OktaAuthPlanStatus.READY
    assert plan.selected_method is OktaAuthMethod.EXISTING_SESSION
    assert [step.kind for step in plan.steps] == [OktaAuthStepKind.REUSE_EXISTING_SESSION]
    assert "password" not in plan.model_dump_json().casefold()


def test_phishing_resistant_methods_win_over_email_otp_when_observed():
    fastpass = plan_okta_authentication(challenge=_challenge(), policy=_email_policy())
    assert fastpass.selected_method is OktaAuthMethod.FASTPASS
    assert fastpass.steps[0].kind is OktaAuthStepKind.REQUEST_FASTPASS
    assert fastpass.steps[0].may_require_user_presence is True

    passkey = plan_okta_authentication(
        challenge=_challenge(available_methods=(OktaAuthMethod.PASSKEY_WEBAUTHN, OktaAuthMethod.EMAIL_OTP)),
        policy=_email_policy(),
    )
    assert passkey.selected_method is OktaAuthMethod.PASSKEY_WEBAUTHN
    assert passkey.steps[0].kind is OktaAuthStepKind.REQUEST_PASSKEY


def test_email_otp_requires_explicit_mailbox_authorization_sender_allowlist_and_vault_ref():
    challenge = _challenge(available_methods=(OktaAuthMethod.EMAIL_OTP,))

    blocked = plan_okta_authentication(
        challenge=challenge,
        policy=OktaAuthenticationPolicy(
            policy_id="policy://blocked",
            application_id=APP,
            allow_email_otp_automation=False,
        ),
    )
    assert blocked.status is OktaAuthPlanStatus.BLOCKED
    assert "okta_email_otp_automation_not_authorized" in blocked.blockers

    ready = plan_okta_authentication(challenge=challenge, policy=_email_policy())
    assert ready.status is OktaAuthPlanStatus.READY
    assert ready.selected_method is OktaAuthMethod.EMAIL_OTP
    assert [step.kind for step in ready.steps] == [
        OktaAuthStepKind.FILL_PASSWORD_FROM_VAULT,
        OktaAuthStepKind.REQUEST_EMAIL_OTP,
        OktaAuthStepKind.FETCH_EMAIL_OTP,
        OktaAuthStepKind.SUBMIT_EMAIL_OTP,
    ]
    serialized = ready.model_dump_json()
    assert "actual-password" not in serialized
    assert "actual-otp" not in serialized
    assert "vault://corporate/carsi-password" in serialized
    assert "mailbox://corporate-inbox" in serialized


def test_policy_cannot_enable_mfa_bypass():
    with pytest.raises(ValueError, match="okta_mfa_bypass_forbidden"):
        OktaAuthenticationPolicy(
            policy_id="policy://unsafe",
            application_id=APP,
            mfa_bypass_allowed=True,
        )


def test_email_otp_is_transient_and_receipt_contains_no_code_or_message_body():
    challenge = _challenge(available_methods=(OktaAuthMethod.EMAIL_OTP,))
    message = MailboxOtpMessage(
        message_ref="mail://message/42",
        sender_address="no-reply@okta.example.com",
        received_at=NOW + timedelta(seconds=15),
        subject="Your verification code 482731",
        body_text="Use 482731 to continue. Confidential business text.",
    )
    result = extract_email_otp(
        challenge=challenge,
        message=message,
        policy=EmailOtpExtractionPolicy(allowed_sender_domains=frozenset({"okta.example.com"})),
        now=NOW + timedelta(seconds=30),
    )

    assert result.code == "482731"
    serialized = result.model_dump_json()
    assert "482731" not in serialized
    assert "Confidential business text" not in serialized
    assert "no-reply@" not in serialized
    assert result.receipt.sender_domain == "okta.example.com"
    assert result.receipt.otp_value_retained is False
    assert result.receipt.message_body_retained is False


def test_email_otp_extraction_rejects_wrong_sender_stale_predating_and_ambiguous_codes():
    challenge = _challenge(available_methods=(OktaAuthMethod.EMAIL_OTP,))
    policy = EmailOtpExtractionPolicy(allowed_sender_domains=frozenset({"okta.example.com"}))

    wrong_sender = MailboxOtpMessage(
        message_ref="mail://wrong",
        sender_address="attacker@evil.example.net",
        received_at=NOW + timedelta(seconds=1),
        body_text="482731",
    )
    with pytest.raises(ValueError, match="okta_otp_sender_domain_not_allowlisted"):
        extract_email_otp(challenge=challenge, message=wrong_sender, policy=policy, now=NOW + timedelta(seconds=2))

    predating = MailboxOtpMessage(
        message_ref="mail://old-challenge",
        sender_address="no-reply@okta.example.com",
        received_at=NOW - timedelta(seconds=1),
        body_text="482731",
    )
    with pytest.raises(ValueError, match="okta_otp_message_predates_challenge"):
        extract_email_otp(challenge=challenge, message=predating, policy=policy, now=NOW + timedelta(seconds=2))

    stale = MailboxOtpMessage(
        message_ref="mail://stale",
        sender_address="no-reply@okta.example.com",
        received_at=NOW + timedelta(seconds=1),
        body_text="482731",
    )
    with pytest.raises(ValueError, match="okta_otp_message_expired"):
        extract_email_otp(challenge=challenge, message=stale, policy=policy, now=NOW + timedelta(minutes=6))

    ambiguous = MailboxOtpMessage(
        message_ref="mail://ambiguous",
        sender_address="no-reply@okta.example.com",
        received_at=NOW + timedelta(seconds=1),
        body_text="Codes 482731 and 593842",
    )
    with pytest.raises(ValueError, match="okta_otp_code_ambiguous"):
        extract_email_otp(challenge=challenge, message=ambiguous, policy=policy, now=NOW + timedelta(seconds=2))
