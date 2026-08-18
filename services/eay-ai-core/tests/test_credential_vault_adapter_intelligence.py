from datetime import datetime, timezone

import pytest

from app.credential_acquisition import CredentialKind, CredentialState, TransientUserSecret
from app.credential_vault_adapter import NativeCredentialVault

NOW = datetime(2026, 8, 18, 8, 50, tzinfo=timezone.utc)


class FakeKeyring:
    def __init__(self):
        self.values = {}
        self.fail_with_secret = False

    def set_password(self, service_name, username, password):
        if self.fail_with_secret:
            raise RuntimeError("backend failed with secret=" + password)
        self.values[(service_name, username)] = password

    def get_password(self, service_name, username):
        return self.values.get((service_name, username))

    def delete_password(self, service_name, username):
        self.values.pop((service_name, username), None)


def _secret(value="NEVER-LOG-ME"):
    return TransientUserSecret(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        credential_kind=CredentialKind.PASSWORD,
        secret_value=value,
        captured_at=NOW,
    )


def test_native_vault_enroll_observe_and_lease_without_serializing_secret():
    backend = FakeKeyring()
    vault = NativeCredentialVault(backend=backend)

    before = vault.observe(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        now=NOW,
    )
    assert before.state is CredentialState.MISSING

    receipt = vault.enroll(_secret(), now=NOW)
    assert receipt.vault_ref.startswith("vault-item:keyring:")
    assert "NEVER-LOG-ME" not in receipt.model_dump_json()

    after = vault.observe(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        now=NOW,
    )
    assert after.state is CredentialState.AVAILABLE
    assert after.vault_ref == receipt.vault_ref

    lease = vault.lease(
        vault_ref=receipt.vault_ref,
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        now=NOW,
        ttl_seconds=60,
    )
    assert lease.secret_value == "NEVER-LOG-ME"
    serialized = lease.model_dump_json()
    assert "NEVER-LOG-ME" not in serialized
    assert "secret_value" not in serialized


def test_vault_reference_cannot_be_reused_for_different_scope():
    backend = FakeKeyring()
    vault = NativeCredentialVault(backend=backend)
    receipt = vault.enroll(_secret(), now=NOW)

    with pytest.raises(ValueError, match="credential_vault_ref_identity_or_scope_mismatch"):
        vault.lease(
            vault_ref=receipt.vault_ref,
            application_id="carsi-portal",
            principal_ref="principal:erdi",
            credential_scope_ref="credential-scope:another-app:erdi",
            now=NOW,
        )


def test_backend_exception_chain_does_not_leak_secret():
    backend = FakeKeyring()
    backend.fail_with_secret = True
    vault = NativeCredentialVault(backend=backend)

    with pytest.raises(RuntimeError) as captured:
        vault.enroll(_secret("HIGHLY-SENSITIVE"), now=NOW)

    assert str(captured.value) == "credential_vault_enrollment_failed"
    assert captured.value.__cause__ is None
    assert "HIGHLY-SENSITIVE" not in repr(captured.value)


def test_revoke_removes_saved_password_and_future_observation_is_missing():
    backend = FakeKeyring()
    vault = NativeCredentialVault(backend=backend)
    receipt = vault.enroll(_secret(), now=NOW)

    vault.revoke(
        vault_ref=receipt.vault_ref,
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
    )
    observed = vault.observe(
        application_id="carsi-portal",
        principal_ref="principal:erdi",
        credential_scope_ref="credential-scope:carsi-portal:erdi",
        now=NOW,
    )
    assert observed.state is CredentialState.MISSING
