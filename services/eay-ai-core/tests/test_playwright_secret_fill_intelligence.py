from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.credential_acquisition import CredentialKind
from app.credential_vault_adapter import CredentialSecretLease
from app.playwright_computer_runtime import (
    BrowserActionReceipt,
    BrowserLocator,
    BrowserActionKind,
    LocatorKind,
)
from app.playwright_secret_fill import SecretFillTarget, perform_managed_secret_fill

NOW = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class FakeSession:
    def __init__(self, *, fail=False):
        self.config = SimpleNamespace(application_id="carsi-portal")
        self.fail = fail
        self.seen_secret = None

    def perform(self, action):
        self.seen_secret = action.input_value
        if self.fail:
            raise RuntimeError("browser failed with value=" + str(action.input_value))
        return BrowserActionReceipt(
            action_id=action.action_id,
            application_id="carsi-portal",
            tenant_scope_ref="tenant:ys-tr",
            auth_context_ref="auth:carsi:erdi",
            locator_kind=action.locator.kind,
            action_kind=BrowserActionKind.FILL,
            completed=True,
            page_url_after="https://carsi-portal.yemeksepeti.com/tr/",
        )


def _lease(
    *,
    application_id="carsi-portal",
    principal_ref="principal:erdi",
    issued_at=None,
    expires_at=None,
):
    issued = issued_at or NOW
    return CredentialSecretLease(
        vault_ref="vault-item:keyring:" + "a" * 64,
        application_id=application_id,
        principal_ref=principal_ref,
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        secret_value="DO-NOT-LOG",
        issued_at=issued,
        expires_at=expires_at or issued + timedelta(seconds=60),
    )


def _target():
    return SecretFillTarget(
        action_id="okta-password-fill",
        locator=BrowserLocator(kind=LocatorKind.LABEL, value="Password"),
    )


def test_secret_fill_uses_lease_but_receipt_never_retains_password():
    session = FakeSession()
    receipt = perform_managed_secret_fill(
        session=session,
        lease=_lease(),
        target=_target(),
        expected_principal_ref="principal:erdi",
        now=NOW,
    )

    assert session.seen_secret == "DO-NOT-LOG"
    assert receipt.completed is True
    assert receipt.input_value_retained is False
    assert "DO-NOT-LOG" not in receipt.model_dump_json()
    assert "DO-NOT-LOG" not in _target().model_dump_json()


def test_secret_fill_rejects_expired_lease_and_wrong_identity():
    session = FakeSession()
    with pytest.raises(ValueError, match="credential_secret_lease_expired"):
        perform_managed_secret_fill(
            session=session,
            lease=_lease(
                issued_at=NOW - timedelta(seconds=60),
                expires_at=NOW - timedelta(seconds=1),
            ),
            target=_target(),
            expected_principal_ref="principal:erdi",
            now=NOW,
        )

    with pytest.raises(ValueError, match="secret_fill_principal_mismatch"):
        perform_managed_secret_fill(
            session=session,
            lease=_lease(),
            target=_target(),
            expected_principal_ref="principal:someone-else",
            now=NOW,
        )


def test_browser_error_is_sanitized_without_secret_exception_chain():
    session = FakeSession(fail=True)
    with pytest.raises(RuntimeError) as captured:
        perform_managed_secret_fill(
            session=session,
            lease=_lease(),
            target=_target(),
            expected_principal_ref="principal:erdi",
            now=NOW,
        )

    assert str(captured.value) == "playwright_secret_fill_failed"
    assert captured.value.__cause__ is None
    assert "DO-NOT-LOG" not in repr(captured.value)
