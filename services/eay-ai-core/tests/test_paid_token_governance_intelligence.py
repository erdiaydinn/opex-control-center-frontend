from datetime import datetime, timedelta, timezone

import pytest

from app.paid_token_governance import (
    PaidTokenDecision,
    PaidTokenGrant,
    PaidTokenGrantStatus,
    PaidTokenInvocationRequest,
    PaidTokenLedgerSnapshot,
    PlatformRole,
    ProviderRateCard,
    authorize_paid_token_invocation,
    settle_paid_token_usage,
)

NOW = datetime(2026, 8, 18, 9, 20, tzinfo=timezone.utc)


def _grant(**updates):
    payload = dict(
        grant_id="grant:user-42:frontier",
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        billing_account_ref="billing:customer-a:user-42",
        cost_center_ref="cost-center:ops",
        allowed_providers=frozenset({"openai_responses", "anthropic_messages"}),
        allowed_model_ids=frozenset({"gpt-5.6", "claude-opus-4-8"}),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        max_output_tokens_per_request=4000,
        max_total_tokens_per_request=12000,
        monthly_provider_cost_limit_microunits=50_000_000,
        monthly_billable_limit_microunits=75_000_000,
        chargeback_multiplier_basis_points=15000,
        approved_by_principal_ref="user:platform-owner",
        approver_role=PlatformRole.PLATFORM_ADMIN,
        admin_approval_ref="approval://paid-token/user-42/1",
    )
    payload.update(updates)
    return PaidTokenGrant(**payload)


def _card(**updates):
    payload = dict(
        rate_card_ref="rate-card:openai:gpt-5.6:2026-08",
        provider="openai_responses",
        model_id="gpt-5.6",
        currency="USD",
        input_cost_microunits_per_million_tokens=2_000_000,
        output_cost_microunits_per_million_tokens=8_000_000,
        effective_from=NOW - timedelta(days=1),
        effective_until=NOW + timedelta(days=30),
        approved_by_principal_ref="user:platform-owner",
        approver_role=PlatformRole.PLATFORM_ADMIN,
        admin_approval_ref="approval://rate-card/openai/1",
    )
    payload.update(updates)
    return ProviderRateCard(**payload)


def _request(**updates):
    payload = dict(
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        provider="openai_responses",
        model_id="gpt-5.6",
        estimated_input_tokens=1000,
        requested_max_output_tokens=2000,
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )
    payload.update(updates)
    return PaidTokenInvocationRequest(**payload)


def _ledger(**updates):
    payload = dict(
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        billing_account_ref="billing:customer-a:user-42",
        billing_cycle_ref="2026-08",
        provider_cost_microunits=1_000_000,
        billable_microunits=1_500_000,
    )
    payload.update(updates)
    return PaidTokenLedgerSnapshot(**payload)


def test_paid_frontier_defaults_to_deny_without_platform_admin_grant():
    authorization = authorize_paid_token_invocation(
        request=_request(), grants=(), rate_cards=(_card(),), ledger=None
    )

    assert authorization.decision is PaidTokenDecision.DENY
    assert authorization.blockers == ("paid_token_active_platform_admin_grant_missing",)
    assert authorization.billing_account_ref is None


def test_user_or_self_service_cannot_create_paid_token_grant():
    with pytest.raises(ValueError, match="paid_token_grant_requires_platform_admin"):
        _grant(approver_role=PlatformRole.USER)

    with pytest.raises(ValueError, match="paid_token_self_service_grant_forbidden"):
        _grant(self_service_grant_allowed=True)


def test_rate_card_also_requires_platform_admin_approval():
    with pytest.raises(ValueError, match="paid_token_rate_card_requires_platform_admin"):
        _card(approver_role=PlatformRole.USER)


def test_exact_user_tenant_provider_and_model_scope_is_enforced():
    grant = _grant()
    card = _card()
    for request in (
        _request(subject_user_ref="user:someone-else"),
        _request(tenant_ref="tenant:customer-b"),
        _request(provider="gemini_generate_content"),
        _request(model_id="gpt-other"),
    ):
        result = authorize_paid_token_invocation(
            request=request, grants=(grant,), rate_cards=(card,), ledger=None
        )
        assert result.decision is PaidTokenDecision.DENY
        assert "paid_token_active_platform_admin_grant_missing" in result.blockers


def test_revoked_or_expired_grant_cannot_spend():
    for grant in (
        _grant(status=PaidTokenGrantStatus.REVOKED),
        _grant(valid_until=NOW - timedelta(seconds=1), valid_from=NOW - timedelta(days=2)),
    ):
        result = authorize_paid_token_invocation(
            request=_request(), grants=(grant,), rate_cards=(_card(),), ledger=None
        )
        assert result.decision is PaidTokenDecision.DENY


def test_authorized_usage_reserves_budget_and_settles_provider_cost_and_chargeback_separately():
    grant = _grant(chargeback_multiplier_basis_points=15000)
    card = _card()
    authorization = authorize_paid_token_invocation(
        request=_request(), grants=(grant,), rate_cards=(card,), ledger=_ledger()
    )

    assert authorization.decision is PaidTokenDecision.ALLOW
    assert authorization.grant_id == grant.grant_id
    assert authorization.billing_account_ref == grant.billing_account_ref
    assert authorization.rate_card_ref == card.rate_card_ref
    assert authorization.reserved_provider_cost_microunits > 0
    assert authorization.reserved_billable_microunits > authorization.reserved_provider_cost_microunits

    usage = settle_paid_token_usage(
        authorization=authorization,
        grant=grant,
        rate_card=card,
        input_tokens=900,
        output_tokens=600,
        settled_at=NOW + timedelta(seconds=10),
        provider_response_ref="resp:123",
    )

    assert usage.provider_cost_microunits > 0
    assert usage.billable_microunits > usage.provider_cost_microunits
    assert usage.billable_microunits == (usage.provider_cost_microunits * 15000 + 9999) // 10000
    assert usage.billing_account_ref == "billing:customer-a:user-42"
    assert usage.provider_response_ref == "resp:123"


def test_monthly_provider_or_billable_budget_exhaustion_fails_closed():
    grant = _grant(
        monthly_provider_cost_limit_microunits=1_000_001,
        monthly_billable_limit_microunits=1_500_001,
    )
    result = authorize_paid_token_invocation(
        request=_request(), grants=(grant,), rate_cards=(_card(),), ledger=_ledger()
    )
    assert result.decision is PaidTokenDecision.DENY
    assert "paid_token_monthly_provider_cost_limit_exceeded" in result.blockers
    assert "paid_token_monthly_billable_limit_exceeded" in result.blockers


def test_request_limits_and_missing_rate_card_fail_before_spend():
    grant = _grant(max_output_tokens_per_request=1000, max_total_tokens_per_request=2000)
    output_denied = authorize_paid_token_invocation(
        request=_request(requested_max_output_tokens=1500, estimated_input_tokens=100),
        grants=(grant,),
        rate_cards=(_card(),),
        ledger=None,
    )
    assert output_denied.decision is PaidTokenDecision.DENY
    assert output_denied.blockers == ("paid_token_request_output_limit_exceeded",)

    missing_card = authorize_paid_token_invocation(
        request=_request(requested_max_output_tokens=500, estimated_input_tokens=500),
        grants=(grant,),
        rate_cards=(),
        ledger=None,
    )
    assert missing_card.decision is PaidTokenDecision.DENY
    assert missing_card.blockers == ("paid_token_active_rate_card_missing",)


def test_wrong_ledger_identity_is_rejected_and_usage_receipt_retains_no_prompt_or_secret():
    with pytest.raises(ValueError, match="paid_token_ledger_identity_or_cycle_mismatch"):
        authorize_paid_token_invocation(
            request=_request(),
            grants=(_grant(),),
            rate_cards=(_card(),),
            ledger=_ledger(subject_user_ref="user:other"),
        )

    grant = _grant()
    card = _card()
    authorization = authorize_paid_token_invocation(
        request=_request(), grants=(grant,), rate_cards=(card,), ledger=None
    )
    usage = settle_paid_token_usage(
        authorization=authorization,
        grant=grant,
        rate_card=card,
        input_tokens=1,
        output_tokens=1,
        settled_at=NOW + timedelta(seconds=1),
    )
    serialized = usage.model_dump_json()
    assert usage.raw_prompt_retained is False
    assert usage.provider_secret_retained is False
    assert "THIS-IS-A-RAW-PROMPT" not in serialized
    assert "sk-secret" not in serialized
