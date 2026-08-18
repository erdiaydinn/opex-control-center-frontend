"""Secret-safe Okta authentication orchestration for managed enterprise apps.

Jarvis may reduce login friction, but it must never bypass an Okta challenge.
The planner prefers an already-authenticated managed browser session, then
phishing-resistant authenticators exposed by the live Okta flow, and uses
password + email OTP only as an explicitly allowed fallback.

Secrets are references, not prompt data:
- passwords are represented only by a credential-vault reference;
- mailbox access is represented only by an authorized connector reference;
- OTP values are transient and excluded from serialization;
- challenge receipts retain only metadata/evidence references.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

OKTA_AUTH_ORCHESTRATION_CONTRACT = "eay-okta-auth-orchestration-v1"
_EMAIL_RE = re.compile(r"^[^@\s]+@([^@\s]+)$")


class OktaAuthMethod(str, Enum):
    EXISTING_SESSION = "existing_session"
    FASTPASS = "okta_fastpass"
    PASSKEY_WEBAUTHN = "passkey_webauthn"
    EMAIL_OTP = "email_otp"


class OktaAuthPlanStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class OktaAuthStepKind(str, Enum):
    REUSE_EXISTING_SESSION = "reuse_existing_session"
    REQUEST_FASTPASS = "request_fastpass"
    REQUEST_PASSKEY = "request_passkey"
    FILL_PASSWORD_FROM_VAULT = "fill_password_from_vault"
    REQUEST_EMAIL_OTP = "request_email_otp"
    FETCH_EMAIL_OTP = "fetch_email_otp"
    SUBMIT_EMAIL_OTP = "submit_email_otp"


class OktaChallengeObservation(BaseModel):
    application_id: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)
    challenge_ref: str = Field(min_length=1)
    observed_at: datetime
    existing_session_authenticated: bool = False
    available_methods: tuple[OktaAuthMethod, ...] = ()
    password_required_before_email_otp: bool = True

    @model_validator(mode="after")
    def challenge_is_time_bound(self) -> "OktaChallengeObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("okta_challenge_requires_timezone")
        if OktaAuthMethod.EXISTING_SESSION in self.available_methods:
            raise ValueError("existing_session_is_state_not_challenge_method")
        return self


class OktaAuthenticationPolicy(BaseModel):
    policy_id: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    allowed_methods: frozenset[OktaAuthMethod] = Field(
        default_factory=lambda: frozenset(
            {
                OktaAuthMethod.FASTPASS,
                OktaAuthMethod.PASSKEY_WEBAUTHN,
                OktaAuthMethod.EMAIL_OTP,
            }
        )
    )
    credential_vault_ref: str | None = None
    mailbox_connector_ref: str | None = None
    mailbox_sender_domains: frozenset[str] = frozenset()
    prefer_phishing_resistant: bool = True
    allow_email_otp_automation: bool = False
    mfa_bypass_allowed: bool = False

    @model_validator(mode="after")
    def policy_never_allows_mfa_bypass(self) -> "OktaAuthenticationPolicy":
        if self.mfa_bypass_allowed:
            raise ValueError("okta_mfa_bypass_forbidden")
        normalized = frozenset(item.casefold().rstrip(".") for item in self.mailbox_sender_domains)
        object.__setattr__(self, "mailbox_sender_domains", normalized)
        if self.allow_email_otp_automation:
            if OktaAuthMethod.EMAIL_OTP not in self.allowed_methods:
                raise ValueError("okta_email_otp_automation_requires_email_method")
            if not self.mailbox_connector_ref:
                raise ValueError("okta_email_otp_automation_requires_mailbox_connector")
            if not normalized:
                raise ValueError("okta_email_otp_automation_requires_sender_allowlist")
        return self


class OktaAuthPlanStep(BaseModel):
    kind: OktaAuthStepKind
    secret_ref: str | None = None
    connector_ref: str | None = None
    challenge_ref: str | None = None
    may_require_user_presence: bool = False
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def plan_step_is_secret_safe(self) -> "OktaAuthPlanStep":
        if self.secret_value_retained:
            raise ValueError("okta_auth_plan_must_not_retain_secret_values")
        if self.kind is OktaAuthStepKind.FILL_PASSWORD_FROM_VAULT and not self.secret_ref:
            raise ValueError("okta_password_step_requires_vault_ref")
        if self.kind is OktaAuthStepKind.FETCH_EMAIL_OTP and not self.connector_ref:
            raise ValueError("okta_email_otp_fetch_requires_connector_ref")
        return self


class OktaAuthPlan(BaseModel):
    contract: str = OKTA_AUTH_ORCHESTRATION_CONTRACT
    application_id: str
    challenge_ref: str
    selected_method: OktaAuthMethod | None = None
    status: OktaAuthPlanStatus
    steps: tuple[OktaAuthPlanStep, ...] = ()
    blockers: tuple[str, ...] = ()
    mfa_bypass_allowed: bool = False
    secret_values_retained: bool = False

    @model_validator(mode="after")
    def ready_plan_cannot_ignore_blockers_or_bypass(self) -> "OktaAuthPlan":
        if self.mfa_bypass_allowed or self.secret_values_retained:
            raise ValueError("okta_auth_plan_truth_boundary_violated")
        if self.status is OktaAuthPlanStatus.READY:
            if self.blockers or self.selected_method is None or not self.steps:
                raise ValueError("ready_okta_plan_requires_method_steps_without_blockers")
        elif not self.blockers:
            raise ValueError("blocked_okta_plan_requires_blocker")
        return self


def plan_okta_authentication(
    *,
    challenge: OktaChallengeObservation,
    policy: OktaAuthenticationPolicy,
) -> OktaAuthPlan:
    if challenge.application_id != policy.application_id:
        raise ValueError("okta_auth_application_policy_mismatch")

    if challenge.existing_session_authenticated:
        return OktaAuthPlan(
            application_id=challenge.application_id,
            challenge_ref=challenge.challenge_ref,
            selected_method=OktaAuthMethod.EXISTING_SESSION,
            status=OktaAuthPlanStatus.READY,
            steps=(OktaAuthPlanStep(kind=OktaAuthStepKind.REUSE_EXISTING_SESSION),),
        )

    available = set(challenge.available_methods) & set(policy.allowed_methods)
    if policy.prefer_phishing_resistant:
        if OktaAuthMethod.FASTPASS in available:
            return OktaAuthPlan(
                application_id=challenge.application_id,
                challenge_ref=challenge.challenge_ref,
                selected_method=OktaAuthMethod.FASTPASS,
                status=OktaAuthPlanStatus.READY,
                steps=(
                    OktaAuthPlanStep(
                        kind=OktaAuthStepKind.REQUEST_FASTPASS,
                        challenge_ref=challenge.challenge_ref,
                        may_require_user_presence=True,
                    ),
                ),
            )
        if OktaAuthMethod.PASSKEY_WEBAUTHN in available:
            return OktaAuthPlan(
                application_id=challenge.application_id,
                challenge_ref=challenge.challenge_ref,
                selected_method=OktaAuthMethod.PASSKEY_WEBAUTHN,
                status=OktaAuthPlanStatus.READY,
                steps=(
                    OktaAuthPlanStep(
                        kind=OktaAuthStepKind.REQUEST_PASSKEY,
                        challenge_ref=challenge.challenge_ref,
                        may_require_user_presence=True,
                    ),
                ),
            )

    if OktaAuthMethod.EMAIL_OTP in available:
        blockers: list[str] = []
        if not policy.allow_email_otp_automation:
            blockers.append("okta_email_otp_automation_not_authorized")
        if not policy.mailbox_connector_ref:
            blockers.append("okta_email_otp_mailbox_connector_missing")
        if not policy.mailbox_sender_domains:
            blockers.append("okta_email_otp_sender_allowlist_missing")
        if challenge.password_required_before_email_otp and not policy.credential_vault_ref:
            blockers.append("okta_password_vault_ref_missing")
        if blockers:
            return OktaAuthPlan(
                application_id=challenge.application_id,
                challenge_ref=challenge.challenge_ref,
                status=OktaAuthPlanStatus.BLOCKED,
                blockers=tuple(dict.fromkeys(blockers)),
            )

        steps: list[OktaAuthPlanStep] = []
        if challenge.password_required_before_email_otp:
            steps.append(
                OktaAuthPlanStep(
                    kind=OktaAuthStepKind.FILL_PASSWORD_FROM_VAULT,
                    secret_ref=policy.credential_vault_ref,
                    challenge_ref=challenge.challenge_ref,
                )
            )
        steps.extend(
            [
                OktaAuthPlanStep(
                    kind=OktaAuthStepKind.REQUEST_EMAIL_OTP,
                    challenge_ref=challenge.challenge_ref,
                ),
                OktaAuthPlanStep(
                    kind=OktaAuthStepKind.FETCH_EMAIL_OTP,
                    connector_ref=policy.mailbox_connector_ref,
                    challenge_ref=challenge.challenge_ref,
                ),
                OktaAuthPlanStep(
                    kind=OktaAuthStepKind.SUBMIT_EMAIL_OTP,
                    challenge_ref=challenge.challenge_ref,
                ),
            ]
        )
        return OktaAuthPlan(
            application_id=challenge.application_id,
            challenge_ref=challenge.challenge_ref,
            selected_method=OktaAuthMethod.EMAIL_OTP,
            status=OktaAuthPlanStatus.READY,
            steps=tuple(steps),
        )

    if not policy.prefer_phishing_resistant:
        for method, step_kind in (
            (OktaAuthMethod.FASTPASS, OktaAuthStepKind.REQUEST_FASTPASS),
            (OktaAuthMethod.PASSKEY_WEBAUTHN, OktaAuthStepKind.REQUEST_PASSKEY),
        ):
            if method in available:
                return OktaAuthPlan(
                    application_id=challenge.application_id,
                    challenge_ref=challenge.challenge_ref,
                    selected_method=method,
                    status=OktaAuthPlanStatus.READY,
                    steps=(
                        OktaAuthPlanStep(
                            kind=step_kind,
                            challenge_ref=challenge.challenge_ref,
                            may_require_user_presence=True,
                        ),
                    ),
                )

    return OktaAuthPlan(
        application_id=challenge.application_id,
        challenge_ref=challenge.challenge_ref,
        status=OktaAuthPlanStatus.BLOCKED,
        blockers=("okta_no_authorized_observed_authentication_method",),
    )


class MailboxOtpMessage(BaseModel):
    message_ref: str = Field(min_length=1)
    sender_address: str = Field(exclude=True)
    received_at: datetime
    subject: str = Field(default="", exclude=True)
    body_text: str = Field(default="", exclude=True)

    @model_validator(mode="after")
    def message_is_time_bound(self) -> "MailboxOtpMessage":
        if self.received_at.tzinfo is None or self.received_at.utcoffset() is None:
            raise ValueError("okta_mail_message_requires_timezone")
        if not _EMAIL_RE.fullmatch(self.sender_address.strip()):
            raise ValueError("okta_mail_sender_address_invalid")
        return self

    @property
    def sender_domain(self) -> str:
        match = _EMAIL_RE.fullmatch(self.sender_address.strip())
        if match is None:  # pragma: no cover - validator guarantees this
            raise ValueError("okta_mail_sender_address_invalid")
        return match.group(1).casefold().rstrip(".")


class EmailOtpExtractionPolicy(BaseModel):
    allowed_sender_domains: frozenset[str] = Field(min_length=1)
    code_length: int = Field(default=6, ge=4, le=10)
    maximum_age_seconds: int = Field(default=300, ge=30, le=900)

    @model_validator(mode="after")
    def normalize_domains(self) -> "EmailOtpExtractionPolicy":
        object.__setattr__(
            self,
            "allowed_sender_domains",
            frozenset(item.casefold().rstrip(".") for item in self.allowed_sender_domains),
        )
        return self


class EmailOtpReceipt(BaseModel):
    contract: str = OKTA_AUTH_ORCHESTRATION_CONTRACT
    challenge_ref: str
    message_ref: str
    sender_domain: str
    received_at: datetime
    code_length: int
    otp_value_retained: bool = False
    message_body_retained: bool = False

    @model_validator(mode="after")
    def receipt_is_secret_safe(self) -> "EmailOtpReceipt":
        if self.otp_value_retained or self.message_body_retained:
            raise ValueError("okta_otp_receipt_cannot_retain_secret_or_message_body")
        return self


class TransientEmailOtp(BaseModel):
    code: str = Field(exclude=True)
    receipt: EmailOtpReceipt
    must_not_be_persisted: bool = True


def extract_email_otp(
    *,
    challenge: OktaChallengeObservation,
    message: MailboxOtpMessage,
    policy: EmailOtpExtractionPolicy,
    now: datetime,
) -> TransientEmailOtp:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("okta_otp_extraction_requires_timezone")
    if message.sender_domain not in policy.allowed_sender_domains:
        raise ValueError("okta_otp_sender_domain_not_allowlisted")
    if message.received_at < challenge.observed_at:
        raise ValueError("okta_otp_message_predates_challenge")
    age_seconds = (now - message.received_at).total_seconds()
    if age_seconds < 0:
        raise ValueError("okta_otp_message_from_future")
    if age_seconds > policy.maximum_age_seconds:
        raise ValueError("okta_otp_message_expired")

    pattern = re.compile(rf"(?<!\d)\d{{{policy.code_length}}}(?!\d)")
    matches = set(pattern.findall(message.subject + "\n" + message.body_text))
    if not matches:
        raise ValueError("okta_otp_code_not_found")
    if len(matches) != 1:
        raise ValueError("okta_otp_code_ambiguous")
    code = next(iter(matches))
    return TransientEmailOtp(
        code=code,
        receipt=EmailOtpReceipt(
            challenge_ref=challenge.challenge_ref,
            message_ref=message.message_ref,
            sender_domain=message.sender_domain,
            received_at=message.received_at,
            code_length=len(code),
        ),
    )
