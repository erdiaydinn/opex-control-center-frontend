from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field

from .models import LocationRecord, TargetSelector, TargetSnapshot
from .targeting import TargetResolutionError, resolve_target_snapshot


class DynamicEligibilitySet(BaseModel):
    """Server-produced location eligibility from a governed KPI/signal rule."""

    tenant_id: str = Field(min_length=1)
    criterion_id: str = Field(min_length=3, max_length=160)
    source_ref: str = Field(min_length=3, max_length=300)
    observed_at: datetime
    location_ids: frozenset[str] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class DynamicTargetResolutionError(TargetResolutionError):
    pass


def build_dynamic_eligibility(
    *,
    tenant_id: str,
    criterion_id: str,
    source_ref: str,
    observed_at: datetime,
    location_ids: frozenset[str],
) -> DynamicEligibilitySet:
    if not location_ids:
        raise DynamicTargetResolutionError("dynamic criterion resolved to zero eligible locations")
    canonical = "|".join(
        [tenant_id, criterion_id, source_ref, observed_at.isoformat(), *sorted(location_ids)]
    )
    return DynamicEligibilitySet(
        tenant_id=tenant_id,
        criterion_id=criterion_id,
        source_ref=source_ref,
        observed_at=observed_at,
        location_ids=location_ids,
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def resolve_dynamic_target_snapshot(
    locations: list[LocationRecord],
    selector: TargetSelector,
    eligibility: DynamicEligibilitySet,
    *,
    created_at: datetime,
) -> TargetSnapshot:
    if eligibility.tenant_id != selector.tenant_id:
        raise DynamicTargetResolutionError("dynamic eligibility tenant does not match target selector")

    base = resolve_target_snapshot(locations, selector, created_at=created_at)
    eligible = set(eligibility.location_ids)
    selected = tuple(location_id for location_id in base.location_ids if location_id in eligible)
    if not selected:
        raise DynamicTargetResolutionError("structured and dynamic targeting intersection is empty")

    canonical = "|".join(
        [
            selector.tenant_id,
            created_at.isoformat(),
            base.fingerprint,
            eligibility.fingerprint,
            *selected,
        ]
    )
    return TargetSnapshot(
        tenant_id=selector.tenant_id,
        created_at=created_at,
        location_ids=selected,
        fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
