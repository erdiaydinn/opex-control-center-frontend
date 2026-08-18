"""Admin-gated paid frontier-token governance and chargeback accounting.

EAY is local-first by default. Paid frontier-model usage is denied unless an
active platform-admin grant exists for the exact user, tenant, provider/model,
billing account and time window. Users cannot self-authorize paid usage.

Provider cost and customer chargeback are separate amounts. Prices are never
hard-coded here; an immutable/versioned admin-approved rate card is required so
historical billing remains reproducible when providers change prices.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

PAID_TOKEN_GOVERNANCE_CONTRACT = "eay-paid-token-governance-v1"
_MICRO = 1_000_000


class PlatformRole(str, Enum):
    PLATFORM_ADMIN = "platform_admin"
    USER = "user"


class PaidTokenGrantStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PaidTokenDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ProviderRateCard(BaseModel):
    rate_card_ref: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    input_cost_microunits_per_million_tokens: int = Field(ge=0)
    output_cost_microunits_per_million_tokens: int = Field(ge=0)
    effective_from: datetime
    effective_until: datetime | None = None
    approved_by_principal_ref: str = Field(min_length=1)
    approver_role: PlatformRole
    admin_approval_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def card_requires_platform_admin_and_time_window(self) -> "ProviderRateCard":
        if self.approver_role is not PlatformRole.PLATFORM_ADMIN:
            raise ValueError("paid_token_rate_card_requires_platform_admin")
        if self.effective_from.tzinfo is None or self.effective_from.utcoffset() is None:
            raise ValueError("paid_token_rate_card_requires_timezone")
        if self.effective_until is not None:
            if self.effective_until.tzinfo is None or self.effective_until.utcoffset() is None:
                raise ValueError("paid_token_rate_card_requires_timezone")
            if self.effective_until <= self.effective_from:
                raise ValueError("paid_token_rate_card_time_window_invalid")
        object.__setattr__(self, "currency", self.currency.upper())
        return self

    def active_at(self, now: datetime) -> bool:
        return self.effective_from <= now and (self.effective_until is None or now < self.effective_until)


class PaidTokenGrant(BaseModel):
    grant_id: str = Field(min_length=1)
    subject_user_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    billing_account_ref: str = Field(min_length=1)
    cost_center_ref: str | None = None
    allowed_providers: frozenset[str] = Field(min_length=1)
    allowed_model_ids: frozenset[str] = Field(min_length=1)
    valid_from: datetime
    valid_until: datetime
    status: PaidTokenGrantStatus = PaidTokenGrantStatus.ACTIVE
    max_output_tokens_per_request: int = Field(default=8192, ge=1)
    max_total_tokens_per_request: int = Field(default=32768, ge=1)
    monthly_provider_cost_limit_microunits: int = Field(ge=0)
    monthly_billable_limit_microunits: int | None = Field(default=None, ge=0)
    chargeback_multiplier_basis_points: int = Field(default=10000, ge=0, le=100000)
    approved_by_principal_ref: str = Field(min_length=1)
    approver_role: PlatformRole
    admin_approval_ref: str = Field(min_length=1)
    self_service_grant_allowed: bool = False

    @model_validator(mode="after")
    def grant_is_admin_only_and_scoped(self) -> "PaidTokenGrant":
        if self.approver_role is not PlatformRole.PLATFORM_ADMIN:
            raise ValueError("paid_token_grant_requires_platform_admin")
        if self.self_service_grant_allowed:
            raise ValueError("paid_token_self_service_grant_forbidden")
        for value in (self.valid_from, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("paid_token_grant_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("paid_token_grant_time_window_invalid")
        if self.max_output_tokens_per_request > self.max_total_tokens_per_request:
            raise ValueError("paid_token_output_limit_cannot_exceed_total_limit")
        object.__setattr__(
            self,
            "allowed_providers",
            frozenset(item.casefold().strip() for item in self.allowed_providers),
        )
        return self

    def active_at(self, now: datetime) -> bool:
        return (
            self.status is PaidTokenGrantStatus.ACTIVE
            and self.valid_from <= now < self.valid_until
        )


class PaidTokenLedgerSnapshot(BaseModel):
    subject_user_ref: str
    tenant_ref: str
    billing_account_ref: str
    billing_cycle_ref: str = Field(min_length=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    provider_cost_microunits: int = Field(default=0, ge=0)
    billable_microunits: int = Field(default=0, ge=0)


class PaidTokenInvocationRequest(BaseModel):
    subject_user_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    estimated_input_tokens: int = Field(ge=0)
    requested_max_output_tokens: int = Field(ge=1)
    billing_cycle_ref: str = Field(min_length=1)
    requested_at: datetime

    @model_validator(mode="after")
    def request_requires_timezone(self) -> "PaidTokenInvocationRequest":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("paid_token_invocation_requires_timezone")
        object.__setattr__(self, "provider", self.provider.casefold().strip())
        return self


class PaidTokenAuthorization(BaseModel):
    contract: str = PAID_TOKEN_GOVERNANCE_CONTRACT
    authorization_ref: str = Field(pattern=r"^paid-token-auth:[0-9a-f]{64}$")
    decision: PaidTokenDecision
    subject_user_ref: str
    tenant_ref: str
    provider: str
    model_id: str
    billing_cycle_ref: str
    billing_account_ref: str | None = None
    grant_id: str | None = None
    rate_card_ref: str | None = None
    currency: str | None = None
    reserved_provider_cost_microunits: int = Field(default=0, ge=0)
    reserved_billable_microunits: int = Field(default=0, ge=0)
    requested_max_output_tokens: int = Field(ge=1)
    blockers: tuple[str, ...] = ()
    expires_at: datetime

    @model_validator(mode="after")
    def authorization_is_consistent(self) -> "PaidTokenAuthorization":
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("paid_token_authorization_requires_timezone")
        if self.decision is PaidTokenDecision.ALLOW:
            if self.blockers or not all(
                (self.billing_account_ref, self.grant_id, self.rate_card_ref, self.currency)
            ):
                raise ValueError("paid_token_allow_requires_billing_and_admin_grant")
        elif not self.blockers:
            raise ValueError("paid_token_deny_requires_blocker")
        return self


class PaidTokenUsageReceipt(BaseModel):
    contract: str = PAID_TOKEN_GOVERNANCE_CONTRACT
    usage_ref: str = Field(pattern=r"^paid-token-usage:[0-9a-f]{64}$")
    authorization_ref: str
    subject_user_ref: str
    tenant_ref: str
    billing_account_ref: str
    grant_id: str
    rate_card_ref: str
    provider: str
    model_id: str
    billing_cycle_ref: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    provider_cost_microunits: int = Field(ge=0)
    billable_microunits: int = Field(ge=0)
    currency: str
    provider_response_ref: str | None = None
    settled_at: datetime
    raw_prompt_retained: bool = False
    provider_secret_retained: bool = False

    @model_validator(mode="after")
    def usage_is_secret_safe(self) -> "PaidTokenUsageReceipt":
        if self.raw_prompt_retained or self.provider_secret_retained:
            raise ValueError("paid_token_usage_cannot_retain_prompt_or_provider_secret")
        if self.settled_at.tzinfo is None or self.settled_at.utcoffset() is None:
            raise ValueError("paid_token_usage_requires_timezone")
        return self


def _cost_microunits(*, tokens: int, rate_per_million: int) -> int:
    if not tokens or not rate_per_million:
        return 0
    return (tokens * rate_per_million + _MICRO - 1) // _MICRO


def _billable(provider_cost_microunits: int, multiplier_basis_points: int) -> int:
    if not provider_cost_microunits or not multiplier_basis_points:
        return 0
    return (provider_cost_microunits * multiplier_basis_points + 9999) // 10000


def _authorization_ref(request: PaidTokenInvocationRequest, grant_id: str | None, blockers: tuple[str, ...]) -> str:
    canonical = json.dumps(
        {
            "contract": PAID_TOKEN_GOVERNANCE_CONTRACT,
            "subject": request.subject_user_ref,
            "tenant": request.tenant_ref,
            "provider": request.provider,
            "model": request.model_id,
            "cycle": request.billing_cycle_ref,
            "requested_at": request.requested_at.isoformat(),
            "grant_id": grant_id,
            "blockers": blockers,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "paid-token-auth:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def authorize_paid_token_invocation(
    *,
    request: PaidTokenInvocationRequest,
    grants: tuple[PaidTokenGrant, ...],
    rate_cards: tuple[ProviderRateCard, ...],
    ledger: PaidTokenLedgerSnapshot | None,
) -> PaidTokenAuthorization:
    now = request.requested_at
    candidates = [
        grant
        for grant in grants
        if grant.subject_user_ref == request.subject_user_ref
        and grant.tenant_ref == request.tenant_ref
        and grant.active_at(now)
        and request.provider in grant.allowed_providers
        and request.model_id in grant.allowed_model_ids
    ]
    if not candidates:
        blockers = ("paid_token_active_platform_admin_grant_missing",)
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, None, blockers),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blockers,
            expires_at=now + timedelta(minutes=5),
        )
    if len(candidates) != 1:
        blockers = ("paid_token_multiple_active_grants_ambiguous",)
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, None, blockers),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blockers,
            expires_at=now + timedelta(minutes=5),
        )
    grant = candidates[0]
    if request.requested_max_output_tokens > grant.max_output_tokens_per_request:
        blockers = ("paid_token_request_output_limit_exceeded",)
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, grant.grant_id, blockers),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            billing_account_ref=grant.billing_account_ref,
            grant_id=grant.grant_id,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blockers,
            expires_at=now + timedelta(minutes=5),
        )
    if request.estimated_input_tokens + request.requested_max_output_tokens > grant.max_total_tokens_per_request:
        blockers = ("paid_token_request_total_limit_exceeded",)
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, grant.grant_id, blockers),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            billing_account_ref=grant.billing_account_ref,
            grant_id=grant.grant_id,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blockers,
            expires_at=now + timedelta(minutes=5),
        )

    cards = [
        card
        for card in rate_cards
        if card.provider.casefold().strip() == request.provider
        and card.model_id == request.model_id
        and card.active_at(now)
    ]
    if len(cards) != 1:
        blockers = (
            "paid_token_active_rate_card_missing"
            if not cards
            else "paid_token_multiple_active_rate_cards_ambiguous",
        )
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, grant.grant_id, blockers),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            billing_account_ref=grant.billing_account_ref,
            grant_id=grant.grant_id,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blockers,
            expires_at=now + timedelta(minutes=5),
        )
    card = cards[0]
    if ledger is None:
        ledger = PaidTokenLedgerSnapshot(
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            billing_account_ref=grant.billing_account_ref,
            billing_cycle_ref=request.billing_cycle_ref,
        )
    expected_ledger_identity = (
        request.subject_user_ref,
        request.tenant_ref,
        grant.billing_account_ref,
        request.billing_cycle_ref,
    )
    actual_ledger_identity = (
        ledger.subject_user_ref,
        ledger.tenant_ref,
        ledger.billing_account_ref,
        ledger.billing_cycle_ref,
    )
    if expected_ledger_identity != actual_ledger_identity:
        raise ValueError("paid_token_ledger_identity_or_cycle_mismatch")

    reserved_provider_cost = _cost_microunits(
        tokens=request.estimated_input_tokens,
        rate_per_million=card.input_cost_microunits_per_million_tokens,
    ) + _cost_microunits(
        tokens=request.requested_max_output_tokens,
        rate_per_million=card.output_cost_microunits_per_million_tokens,
    )
    reserved_billable = _billable(reserved_provider_cost, grant.chargeback_multiplier_basis_points)
    blockers: list[str] = []
    if ledger.provider_cost_microunits + reserved_provider_cost > grant.monthly_provider_cost_limit_microunits:
        blockers.append("paid_token_monthly_provider_cost_limit_exceeded")
    if (
        grant.monthly_billable_limit_microunits is not None
        and ledger.billable_microunits + reserved_billable > grant.monthly_billable_limit_microunits
    ):
        blockers.append("paid_token_monthly_billable_limit_exceeded")
    if blockers:
        blocker_tuple = tuple(blockers)
        return PaidTokenAuthorization(
            authorization_ref=_authorization_ref(request, grant.grant_id, blocker_tuple),
            decision=PaidTokenDecision.DENY,
            subject_user_ref=request.subject_user_ref,
            tenant_ref=request.tenant_ref,
            provider=request.provider,
            model_id=request.model_id,
            billing_cycle_ref=request.billing_cycle_ref,
            billing_account_ref=grant.billing_account_ref,
            grant_id=grant.grant_id,
            rate_card_ref=card.rate_card_ref,
            currency=card.currency,
            requested_max_output_tokens=request.requested_max_output_tokens,
            blockers=blocker_tuple,
            expires_at=now + timedelta(minutes=5),
        )

    return PaidTokenAuthorization(
        authorization_ref=_authorization_ref(request, grant.grant_id, ()),
        decision=PaidTokenDecision.ALLOW,
        subject_user_ref=request.subject_user_ref,
        tenant_ref=request.tenant_ref,
        provider=request.provider,
        model_id=request.model_id,
        billing_cycle_ref=request.billing_cycle_ref,
        billing_account_ref=grant.billing_account_ref,
        grant_id=grant.grant_id,
        rate_card_ref=card.rate_card_ref,
        currency=card.currency,
        reserved_provider_cost_microunits=reserved_provider_cost,
        reserved_billable_microunits=reserved_billable,
        requested_max_output_tokens=request.requested_max_output_tokens,
        expires_at=now + timedelta(minutes=5),
    )


def settle_paid_token_usage(
    *,
    authorization: PaidTokenAuthorization,
    grant: PaidTokenGrant,
    rate_card: ProviderRateCard,
    input_tokens: int,
    output_tokens: int,
    settled_at: datetime,
    provider_response_ref: str | None = None,
) -> PaidTokenUsageReceipt:
    if authorization.decision is not PaidTokenDecision.ALLOW:
        raise ValueError("paid_token_denied_authorization_cannot_settle_usage")
    if settled_at.tzinfo is None or settled_at.utcoffset() is None:
        raise ValueError("paid_token_usage_requires_timezone")
    if settled_at > authorization.expires_at:
        raise ValueError("paid_token_authorization_expired")
    if authorization.grant_id != grant.grant_id or authorization.rate_card_ref != rate_card.rate_card_ref:
        raise ValueError("paid_token_settlement_grant_or_rate_card_mismatch")
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("paid_token_usage_cannot_be_negative")
    if output_tokens > authorization.requested_max_output_tokens:
        raise ValueError("paid_token_provider_output_exceeded_authorized_limit")

    provider_cost = _cost_microunits(
        tokens=input_tokens,
        rate_per_million=rate_card.input_cost_microunits_per_million_tokens,
    ) + _cost_microunits(
        tokens=output_tokens,
        rate_per_million=rate_card.output_cost_microunits_per_million_tokens,
    )
    billable = _billable(provider_cost, grant.chargeback_multiplier_basis_points)
    canonical = json.dumps(
        {
            "authorization_ref": authorization.authorization_ref,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "provider_cost_microunits": provider_cost,
            "billable_microunits": billable,
            "provider_response_ref": provider_response_ref,
            "settled_at": settled_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return PaidTokenUsageReceipt(
        usage_ref="paid-token-usage:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        authorization_ref=authorization.authorization_ref,
        subject_user_ref=authorization.subject_user_ref,
        tenant_ref=authorization.tenant_ref,
        billing_account_ref=authorization.billing_account_ref or "",
        grant_id=grant.grant_id,
        rate_card_ref=rate_card.rate_card_ref,
        provider=authorization.provider,
        model_id=authorization.model_id,
        billing_cycle_ref=authorization.billing_cycle_ref,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        provider_cost_microunits=provider_cost,
        billable_microunits=billable,
        currency=rate_card.currency,
        provider_response_ref=provider_response_ref,
        settled_at=settled_at,
    )
