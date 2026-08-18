"""Secret-safe bridge from credential leases to managed Playwright fills.

The raw password never becomes a returned BrowserAction or receipt. It is read
from a short-lived credential lease, used inside this function to construct one
transient fill action, and any browser exception is replaced with a sanitized
error without retaining the original exception chain.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .credential_vault_adapter import CredentialSecretLease
from .playwright_computer_runtime import (
    BrowserAction,
    BrowserActionKind,
    BrowserActionReceipt,
    BrowserLocator,
    ManagedPlaywrightSession,
)

PLAYWRIGHT_SECRET_FILL_CONTRACT = "eay-playwright-secret-fill-v1"


class SecretFillTarget(BaseModel):
    contract: str = PLAYWRIGHT_SECRET_FILL_CONTRACT
    action_id: str = Field(min_length=1)
    locator: BrowserLocator
    timeout_ms: int = Field(default=15000, ge=100, le=60000)
    settle_ms: int = Field(default=300, ge=0, le=5000)
    secret_value_retained: bool = False

    @model_validator(mode="after")
    def target_never_contains_secret(self) -> "SecretFillTarget":
        if self.secret_value_retained:
            raise ValueError("secret_fill_target_cannot_retain_secret")
        return self


def perform_managed_secret_fill(
    *,
    session: ManagedPlaywrightSession,
    lease: CredentialSecretLease,
    target: SecretFillTarget,
    expected_principal_ref: str,
    now: datetime,
) -> BrowserActionReceipt:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("secret_fill_requires_timezone")
    if lease.expires_at <= now:
        raise ValueError("credential_secret_lease_expired")
    if lease.application_id != session.config.application_id:
        raise ValueError("secret_fill_application_mismatch")
    if lease.principal_ref != expected_principal_ref:
        raise ValueError("secret_fill_principal_mismatch")

    try:
        receipt = session.perform(
            BrowserAction(
                action_id=target.action_id,
                kind=BrowserActionKind.FILL,
                locator=target.locator,
                input_value=lease.secret_value,
                timeout_ms=target.timeout_ms,
                settle_ms=target.settle_ms,
            )
        )
    except Exception:
        raise RuntimeError("playwright_secret_fill_failed") from None

    if not receipt.completed:
        raise RuntimeError("playwright_secret_fill_not_completed")
    if receipt.input_value_retained:
        raise RuntimeError("playwright_secret_fill_receipt_retained_input")
    if receipt.application_id != lease.application_id:
        raise RuntimeError("playwright_secret_fill_receipt_application_mismatch")
    return receipt
