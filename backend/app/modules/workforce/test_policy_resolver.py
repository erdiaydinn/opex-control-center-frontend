from datetime import datetime, timedelta, timezone

import pytest

from app.modules.workforce.policy_model import WorkforceSchedulingPolicy
from app.modules.workforce.policy_resolver import WorkforcePolicyResolutionError, resolve_scheduling_policy

NOW = datetime(2026, 8, 16, 14, 0, tzinfo=timezone.utc)


def policy(policy_id: str, *, tenant="tenant-a", version=1, country=None, region=None, business_unit=None):
    return WorkforceSchedulingPolicy(
        tenant_id=tenant,
        policy_id=policy_id,
        version=version,
        allowed_shift_minutes=(480,),
        max_daily_work_minutes=480,
        min_rest_minutes=660,
        effective_from=NOW - timedelta(days=30),
        country=country,
        region=region,
        business_unit=business_unit,
    )


def test_more_specific_company_scope_wins_over_tenant_default():
    selected = resolve_scheduling_policy(
        (
            policy("tenant-default", version=5),
            policy("tr-darkstore", version=2, country="TR", business_unit="darkstore"),
        ),
        tenant_id="tenant-a",
        country="TR",
        business_unit="darkstore",
        at=NOW,
    )
    assert selected.policy_id == "tr-darkstore"


def test_cross_tenant_policy_is_never_selected():
    with pytest.raises(WorkforcePolicyResolutionError, match="no effective"):
        resolve_scheduling_policy(
            (policy("other", tenant="tenant-b"),),
            tenant_id="tenant-a",
            at=NOW,
        )


def test_equal_rank_conflict_fails_closed():
    with pytest.raises(WorkforcePolicyResolutionError, match="ambiguous equally authoritative"):
        resolve_scheduling_policy(
            (
                policy("country-policy", version=2, country="TR"),
                policy("bu-policy", version=2, business_unit="darkstore"),
            ),
            tenant_id="tenant-a",
            country="TR",
            business_unit="darkstore",
            at=NOW,
        )
