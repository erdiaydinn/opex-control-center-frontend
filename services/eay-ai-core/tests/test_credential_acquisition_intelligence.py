from datetime import datetime, timezone

import pytest

from app.credential_acquisition import (
    CredentialAcquisitionStatus,
    CredentialKind,
    CredentialPersistencePolicy,
    CredentialState,
    ManagedCredentialObservation,
    TransientUserSecret,
    VaultEnrollmentReceipt,
    plan_credential_acquisition,
    validate_vault_enrollment,
)

NOW = datetime(2026, 8, 18, 8, 45, tzinfo=timezone.utc)


def _policy(**updates):
    payload = dict(
        policy_id="carsi-password-v1",
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        approved_vault_ref="vault:eay-enterprise-credentials",
        user_authorized_persistent_enrollment=True,
        allow_user_secret_prompt=True,
    )
    payload.update(updates)
    return CredentialPersistencePolicy(**payload)


def _observation(state: CredentialState, *, vault_ref=None, evidence=None):
    return ManagedCredentialObservation(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        state=state,
        vault_ref=vault_ref,
        observed_at=NOW,
        rejection_evidence_ref=evidence,
    )


def _receipt(**updates):
    payload = dict(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        vault_provider_ref="vault:eay-enterprise-credentials",
        vault_ref="vault-item:carsi:erdi",
        enrolled_at=NOW,
        enrollment_evidence_ref="evidence://vault/enrollment/1",
    )
    payload.update(updates)
    return VaultEnrollmentReceipt(**payload)


def test_missing_password_prompts_once_and_explains_future_reuse():
    plan = plan_credential_acquisition(
        observation=_observation(CredentialState.MISSING),
        policy=_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is CredentialAcquisitionStatus.NEEDS_USER_SECRET
    assert "ÇarşıPortal şifre istedi" in plan.user_prompt
    assert "tekrar sormayacağım" in plan.user_prompt
    assert plan.remember_after_capture is True
    assert plan.vault_ref is None
    assert plan.secret_value_retained is False


def test_available_managed_password_is_reused_without_prompt():
    plan = plan_credential_acquisition(
        observation=_observation(CredentialState.AVAILABLE, vault_ref="vault-item:carsi:erdi"),
        policy=_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is CredentialAcquisitionStatus.READY
    assert plan.vault_ref == "vault-item:carsi:erdi"
    assert plan.user_prompt is None


def test_rejected_password_never_blind_retries_and_requires_user_reentry():
    plan = plan_credential_acquisition(
        observation=_observation(
            CredentialState.REJECTED,
            evidence="evidence://okta/password-rejected/1",
        ),
        policy=_policy(),
        application_display_name="ÇarşıPortal",
    )

    assert plan.status is CredentialAcquisitionStatus.NEEDS_USER_SECRET
    assert "Şifreni söyler misin" in plan.user_prompt

    with pytest.raises(ValueError, match="credential_policy_cannot_retry_rejected_secret_without_user"):
        _policy(retry_rejected_secret_without_user=True)


def test_transient_secret_never_serializes_and_valid_enrollment_returns_reference_only():
    transient = TransientUserSecret(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        secret_value="THIS-MUST-NEVER-LEAK",
        captured_at=NOW,
    )
    serialized = transient.model_dump_json()
    assert "THIS-MUST-NEVER-LEAK" not in serialized
    assert "secret_value" not in serialized

    receipt = _receipt()
    assert validate_vault_enrollment(
        transient_secret=transient,
        receipt=receipt,
        policy=_policy(),
    ) == "vault-item:carsi:erdi"
    assert "THIS-MUST-NEVER-LEAK" not in receipt.model_dump_json()


def test_vault_enrollment_must_use_exact_approved_provider():
    transient = TransientUserSecret(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        secret_value="TRANSIENT",
        captured_at=NOW,
    )
    with pytest.raises(ValueError, match="vault_enrollment_provider_not_approved"):
        validate_vault_enrollment(
            transient_secret=transient,
            receipt=_receipt(vault_provider_ref="vault:unapproved"),
            policy=_policy(),
        )


def test_persistent_enrollment_requires_explicit_user_authorization():
    transient = TransientUserSecret(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        secret_value="TRANSIENT",
        captured_at=NOW,
    )
    with pytest.raises(ValueError, match="persistent_credential_enrollment_not_authorized"):
        validate_vault_enrollment(
            transient_secret=transient,
            receipt=_receipt(),
            policy=_policy(user_authorized_persistent_enrollment=False),
        )


def test_blank_secret_is_rejected_before_vault_enrollment():
    with pytest.raises(ValueError, match="transient_user_secret_cannot_be_blank"):
        TransientUserSecret(
            application_id="carsi-portal",
            principal_ref="principal:erdi",
            credential_scope_ref="credential-scope:carsi-portal:erdi",
            credential_kind=CredentialKind.PASSWORD,
            secret_value="   ",
            captured_at=NOW,
        )
