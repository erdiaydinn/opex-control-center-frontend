"""Native secure credential-vault adapter for Jarvis enterprise sessions.

The adapter is intentionally model-blind. Raw credentials only cross the
boundary between a transient user-secret object and an operating-system keyring
backend. Persistent EAY state receives opaque item references and receipts.

A real system backend is loaded lazily through the optional ``keyring`` Python
package. There is no plaintext-file fallback: if a secure backend is not
available, credential persistence fails closed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .credential_acquisition import (
    CredentialKind,
    CredentialState,
    ManagedCredentialObservation,
    TransientUserSecret,
    VaultEnrollmentReceipt,
)

CREDENTIAL_VAULT_ADAPTER_CONTRACT = "eay-native-credential-vault-v1"
SYSTEM_KEYRING_PROVIDER_REF = "vault:eay-enterprise-credentials"
DEFAULT_SERVICE_NAME = "EAY Jarvis Enterprise Credentials"
_VAULT_REF_PREFIX = "vault-item:keyring:"


class KeyringBackend(Protocol):
    def set_password(self, service_name: str, username: str, password: str) -> None: ...
    def get_password(self, service_name: str, username: str) -> str | None: ...
    def delete_password(self, service_name: str, username: str) -> None: ...


class CredentialSecretLease(BaseModel):
    contract: str = CREDENTIAL_VAULT_ADAPTER_CONTRACT
    vault_ref: str = Field(min_length=1)
    application_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    credential_scope_ref: str = Field(min_length=1)
    credential_kind: CredentialKind
    secret_value: str = Field(min_length=1, exclude=True)
    issued_at: datetime
    expires_at: datetime
    must_not_be_persisted: bool = True

    @model_validator(mode="after")
    def lease_is_short_lived_and_secret_safe(self) -> "CredentialSecretLease":
        for value in (self.issued_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("credential_secret_lease_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("credential_secret_lease_expiry_invalid")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("credential_secret_lease_too_long")
        if not self.secret_value.strip():
            raise ValueError("credential_secret_lease_cannot_be_blank")
        if not self.must_not_be_persisted:
            raise ValueError("credential_secret_lease_must_not_be_persisted")
        return self


def _opaque_item_id(*, application_id: str, principal_ref: str, credential_scope_ref: str) -> str:
    material = "\x1f".join((application_id, principal_ref, credential_scope_ref)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _vault_ref(item_id: str) -> str:
    return _VAULT_REF_PREFIX + item_id


def _item_id_from_vault_ref(vault_ref: str) -> str:
    if not vault_ref.startswith(_VAULT_REF_PREFIX):
        raise ValueError("credential_vault_ref_provider_mismatch")
    item_id = vault_ref[len(_VAULT_REF_PREFIX):]
    if len(item_id) != 64 or any(ch not in "0123456789abcdef" for ch in item_id):
        raise ValueError("credential_vault_ref_invalid")
    return item_id


class NativeCredentialVault:
    def __init__(
        self,
        *,
        backend: KeyringBackend,
        service_name: str = DEFAULT_SERVICE_NAME,
        provider_ref: str = SYSTEM_KEYRING_PROVIDER_REF,
    ) -> None:
        if not service_name.strip() or not provider_ref.strip():
            raise ValueError("credential_vault_identity_required")
        self._backend = backend
        self.service_name = service_name
        self.provider_ref = provider_ref

    def enroll(self, secret: TransientUserSecret, *, now: datetime | None = None) -> VaultEnrollmentReceipt:
        item_id = _opaque_item_id(
            application_id=secret.application_id,
            principal_ref=secret.principal_ref,
            credential_scope_ref=secret.credential_scope_ref,
        )
        try:
            self._backend.set_password(self.service_name, item_id, secret.secret_value)
        except Exception:
            raise RuntimeError("credential_vault_enrollment_failed") from None
        enrolled_at = now or datetime.now(timezone.utc)
        return VaultEnrollmentReceipt(
            application_id=secret.application_id,
            principal_ref=secret.principal_ref,
            credential_scope_ref=secret.credential_scope_ref,
            credential_kind=secret.credential_kind,
            vault_provider_ref=self.provider_ref,
            vault_ref=_vault_ref(item_id),
            enrolled_at=enrolled_at,
            enrollment_evidence_ref="evidence://credential-vault/enrollment/" + item_id[:16],
        )

    def observe(
        self,
        *,
        application_id: str,
        principal_ref: str,
        credential_scope_ref: str,
        credential_kind: CredentialKind = CredentialKind.PASSWORD,
        now: datetime | None = None,
    ) -> ManagedCredentialObservation:
        item_id = _opaque_item_id(
            application_id=application_id,
            principal_ref=principal_ref,
            credential_scope_ref=credential_scope_ref,
        )
        try:
            secret = self._backend.get_password(self.service_name, item_id)
        except Exception:
            raise RuntimeError("credential_vault_lookup_failed") from None
        return ManagedCredentialObservation(
            application_id=application_id,
            principal_ref=principal_ref,
            credential_kind=credential_kind,
            credential_scope_ref=credential_scope_ref,
            state=CredentialState.AVAILABLE if secret else CredentialState.MISSING,
            vault_ref=_vault_ref(item_id) if secret else None,
            observed_at=now or datetime.now(timezone.utc),
        )

    def lease(
        self,
        *,
        vault_ref: str,
        application_id: str,
        principal_ref: str,
        credential_scope_ref: str,
        credential_kind: CredentialKind = CredentialKind.PASSWORD,
        now: datetime | None = None,
        ttl_seconds: int = 60,
    ) -> CredentialSecretLease:
        if ttl_seconds < 1 or ttl_seconds > 300:
            raise ValueError("credential_secret_lease_ttl_out_of_bounds")
        expected_item_id = _opaque_item_id(
            application_id=application_id,
            principal_ref=principal_ref,
            credential_scope_ref=credential_scope_ref,
        )
        actual_item_id = _item_id_from_vault_ref(vault_ref)
        if actual_item_id != expected_item_id:
            raise ValueError("credential_vault_ref_identity_or_scope_mismatch")
        try:
            secret = self._backend.get_password(self.service_name, actual_item_id)
        except Exception:
            raise RuntimeError("credential_vault_lookup_failed") from None
        if not secret:
            raise KeyError("credential_vault_item_missing")
        issued_at = now or datetime.now(timezone.utc)
        return CredentialSecretLease(
            vault_ref=vault_ref,
            application_id=application_id,
            principal_ref=principal_ref,
            credential_scope_ref=credential_scope_ref,
            credential_kind=credential_kind,
            secret_value=secret,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(seconds=ttl_seconds),
        )

    def revoke(
        self,
        *,
        vault_ref: str,
        application_id: str,
        principal_ref: str,
        credential_scope_ref: str,
    ) -> None:
        expected_item_id = _opaque_item_id(
            application_id=application_id,
            principal_ref=principal_ref,
            credential_scope_ref=credential_scope_ref,
        )
        actual_item_id = _item_id_from_vault_ref(vault_ref)
        if actual_item_id != expected_item_id:
            raise ValueError("credential_vault_ref_identity_or_scope_mismatch")
        try:
            self._backend.delete_password(self.service_name, actual_item_id)
        except Exception:
            raise RuntimeError("credential_vault_revoke_failed") from None


def load_system_native_credential_vault() -> NativeCredentialVault:
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError:
        raise RuntimeError("credential_vault_optional_keyring_dependency_not_installed") from None

    backend = keyring.get_keyring()
    priority = getattr(backend, "priority", 0)
    try:
        usable = float(priority) > 0
    except (TypeError, ValueError):
        usable = False
    if not usable:
        raise RuntimeError("credential_vault_secure_system_backend_unavailable")
    return NativeCredentialVault(backend=keyring)
