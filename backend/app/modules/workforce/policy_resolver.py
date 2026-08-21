from __future__ import annotations

from datetime import datetime

from .policy_model import WorkforceSchedulingPolicy


class WorkforcePolicyResolutionError(LookupError):
    pass


def _matches(
    policy: WorkforceSchedulingPolicy,
    *,
    tenant_id: str,
    country: str | None,
    region: str | None,
    business_unit: str | None,
    at: datetime,
) -> bool:
    if policy.tenant_id != tenant_id:
        return False
    if policy.effective_from > at or (policy.effective_to and policy.effective_to <= at):
        return False
    dimensions = (
        (policy.country, country),
        (policy.region, region),
        (policy.business_unit, business_unit),
    )
    return all(expected is None or expected == actual for expected, actual in dimensions)


def _rank(policy: WorkforceSchedulingPolicy) -> tuple[int, int]:
    specificity = sum(value is not None for value in (policy.country, policy.region, policy.business_unit))
    return specificity, policy.version


def resolve_scheduling_policy(
    policies: tuple[WorkforceSchedulingPolicy, ...],
    *,
    tenant_id: str,
    at: datetime,
    country: str | None = None,
    region: str | None = None,
    business_unit: str | None = None,
) -> WorkforceSchedulingPolicy:
    candidates = [
        policy
        for policy in policies
        if _matches(
            policy,
            tenant_id=tenant_id,
            country=country,
            region=region,
            business_unit=business_unit,
            at=at,
        )
    ]
    if not candidates:
        raise WorkforcePolicyResolutionError("no effective scheduling policy for tenant scope")
    candidates.sort(key=_rank, reverse=True)
    top_rank = _rank(candidates[0])
    top = [policy for policy in candidates if _rank(policy) == top_rank]
    identities = {(policy.policy_id, policy.version) for policy in top}
    if len(identities) > 1:
        raise WorkforcePolicyResolutionError("ambiguous equally authoritative scheduling policies")
    return candidates[0]
