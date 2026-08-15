from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .models import LocationRecord, TargetSelector, TargetSnapshot


class TargetResolutionError(ValueError):
    pass


def _matches_positive_scope(location: LocationRecord, selector: TargetSelector) -> bool:
    if selector.all_active_locations:
        return True
    checks = []
    if selector.countries:
        checks.append(location.country in selector.countries)
    if selector.regions:
        checks.append(location.region in selector.regions)
    if selector.cities:
        checks.append(location.city in selector.cities)
    if selector.districts:
        checks.append(location.district in selector.districts)
    if selector.location_groups:
        checks.append(bool(set(location.groups) & set(selector.location_groups)))
    if selector.include_location_ids:
        checks.append(location.location_id in selector.include_location_ids)
    return any(checks)


def resolve_target_snapshot(
    locations: list[LocationRecord],
    selector: TargetSelector,
    *,
    created_at: datetime,
) -> TargetSnapshot:
    selected: list[str] = []
    excluded = set(selector.exclude_location_ids)
    for location in locations:
        if location.tenant_id != selector.tenant_id:
            continue
        if not location.active:
            continue
        if location.location_id in excluded:
            continue
        if _matches_positive_scope(location, selector):
            selected.append(location.location_id)

    location_ids = tuple(sorted(set(selected)))
    if not location_ids:
        raise TargetResolutionError("mission target selector resolved to zero active locations")

    payload = {
        "tenant_id": selector.tenant_id,
        "created_at": created_at.isoformat(),
        "location_ids": location_ids,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TargetSnapshot(
        tenant_id=selector.tenant_id,
        created_at=created_at,
        location_ids=location_ids,
        fingerprint=fingerprint,
    )
