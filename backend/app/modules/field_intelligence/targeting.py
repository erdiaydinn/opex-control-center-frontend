from __future__ import annotations

import hashlib
import json
from datetime import datetime

from .models import LocationRecord, TargetSelector, TargetSnapshot


class TargetResolutionError(ValueError):
    pass


def _matches_structured_scope(location: LocationRecord, selector: TargetSelector) -> bool:
    if selector.all_active_locations:
        return True

    scoped = False
    if selector.countries:
        scoped = True
        if location.country not in selector.countries:
            return False
    if selector.regions:
        scoped = True
        if location.region not in selector.regions:
            return False
    if selector.cities:
        scoped = True
        if location.city not in selector.cities:
            return False
    if selector.districts:
        scoped = True
        if location.district not in selector.districts:
            return False
    if selector.location_groups:
        scoped = True
        if not (set(location.groups) & set(selector.location_groups)):
            return False
    return scoped


def _matches_positive_scope(location: LocationRecord, selector: TargetSelector) -> bool:
    if location.location_id in selector.include_location_ids:
        return True
    return _matches_structured_scope(location, selector)


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
