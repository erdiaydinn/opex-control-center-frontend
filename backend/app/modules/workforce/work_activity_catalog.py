"""Governed tenant work-activity catalog backed by Workforce persistence.

Starter industry templates remain non-authoritative. This catalog is the explicit
human-approved boundary that open shifts and generic demand can consume.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo

from . import persistence
from .industry_activity_templates import starter_candidates
from .work_activity_authority import WorkActivityAuthorityError, WorkActivityVersion


_COLLECTION = "workforce_activity_catalog"
_LOCK = Lock()


class WorkActivityCatalogError(ValueError):
    """Raised when the governed activity catalog cannot resolve authority safely."""


def _at(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T00:00:00+03:00")


def _row_to_authority(row: dict) -> WorkActivityVersion:
    return WorkActivityVersion(
        tenant_id=str(row["tenant_id"]),
        activity_key=str(row["activity_key"]),
        version=int(row["version"]),
        display_name=str(row["display_name"]),
        category=str(row["category"]),
        unit_key=str(row["unit_key"]),
        demand_mode=str(row["demand_mode"]),
        effective_from=datetime.fromisoformat(str(row["effective_from"])),
        source_ref=str(row["source_ref"]),
        approved_by=str(row["approved_by"]),
        required_skill_keys=tuple(row.get("required_skill_keys") or ()),
        required_certification_keys=tuple(row.get("required_certification_keys") or ()),
        required_equipment_keys=tuple(row.get("required_equipment_keys") or ()),
        safety_tags=tuple(row.get("safety_tags") or ()),
        location_types=tuple(row.get("location_types") or ()),
        effective_until=datetime.fromisoformat(str(row["effective_until"])) if row.get("effective_until") else None,
        status=str(row.get("status") or "APPROVED"),
    )


def list_activity_catalog(*, include_retired: bool = False) -> list[dict]:
    rows = persistence.load_collection(_COLLECTION)
    if not include_retired:
        rows = [row for row in rows if row.get("status") == "APPROVED"]
    return deepcopy(sorted(rows, key=lambda row: (str(row.get("activity_key")), int(row.get("version", 0))), reverse=False))


def list_template_candidates(template_key: str) -> tuple[dict[str, object], ...]:
    return starter_candidates(template_key)


def approve_activity(payload: dict, actor: str) -> dict:
    """Create a new approved effective-dated activity version."""
    tenant_id = persistence.tenant_id()
    effective_from = _at(str(payload["effective_from"]))
    key = str(payload["activity_key"]).strip()

    with _LOCK:
        rows = persistence.load_collection(_COLLECTION)
        versions = [row for row in rows if str(row.get("activity_key")) == key]
        version = max((int(row.get("version", 0)) for row in versions), default=0) + 1
        authority = WorkActivityVersion(
            tenant_id=tenant_id,
            activity_key=key,
            version=version,
            display_name=str(payload["display_name"]),
            category=str(payload["category"]),
            unit_key=str(payload["unit_key"]),
            demand_mode=str(payload["demand_mode"]),
            effective_from=effective_from,
            source_ref=str(payload["source_ref"]),
            approved_by=actor,
            required_skill_keys=tuple(payload.get("required_skill_keys") or ()),
            required_certification_keys=tuple(payload.get("required_certification_keys") or ()),
            required_equipment_keys=tuple(payload.get("required_equipment_keys") or ()),
            safety_tags=tuple(payload.get("safety_tags") or ()),
            location_types=tuple(payload.get("location_types") or ()),
        )
        for row in versions:
            if row.get("status") != "APPROVED":
                continue
            previous_from = datetime.fromisoformat(str(row["effective_from"]))
            previous_until = datetime.fromisoformat(str(row["effective_until"])) if row.get("effective_until") else None
            if previous_from < effective_from and (previous_until is None or effective_from < previous_until):
                row["effective_until"] = effective_from.isoformat()
                row["superseded_by_version"] = version
                row["superseded_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
                row["superseded_by"] = actor
            elif previous_from == effective_from:
                row["status"] = "RETIRED"
                row["retired_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
                row["retired_by"] = actor
                row["superseded_by_version"] = version

        now = datetime.now(ZoneInfo("UTC")).isoformat()
        record = {
            "id": f"ACT-{key}-V{version}",
            "tenant_id": tenant_id,
            "activity_key": authority.activity_key,
            "version": authority.version,
            "display_name": authority.display_name,
            "category": authority.category,
            "unit_key": authority.unit_key,
            "demand_mode": authority.demand_mode,
            "required_skill_keys": list(authority.required_skill_keys),
            "required_certification_keys": list(authority.required_certification_keys),
            "required_equipment_keys": list(authority.required_equipment_keys),
            "safety_tags": list(authority.safety_tags),
            "location_types": list(authority.location_types),
            "effective_from": authority.effective_from.isoformat(),
            "effective_until": None,
            "status": authority.status,
            "source_ref": authority.source_ref,
            "approved_by": actor,
            "approved_at": now,
        }
        rows.append(record)
        try:
            persistence.persist_snapshot_with_audit(
                {_COLLECTION: rows},
                "WORKFORCE_ACTIVITY_APPROVED",
                actor,
                activity_key=key,
                activity_version=version,
                effective_from=authority.effective_from.isoformat(),
                source_ref=authority.source_ref,
            )
        except persistence.ConcurrentWriteError as error:
            raise WorkActivityCatalogError(
                "Work activity catalog changed concurrently; approval stopped safely, retry."
            ) from error
        return deepcopy(record)


def retire_activity(activity_key: str, actor: str) -> dict:
    with _LOCK:
        rows = persistence.load_collection(_COLLECTION)
        candidates = [
            row for row in rows
            if str(row.get("activity_key")) == str(activity_key) and row.get("status") == "APPROVED"
        ]
        if not candidates:
            raise WorkActivityCatalogError("Active work activity was not found.")
        current = max(candidates, key=lambda row: int(row.get("version", 0)))
        current["status"] = "RETIRED"
        current["retired_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        current["retired_by"] = actor
        try:
            persistence.persist_snapshot_with_audit(
                {_COLLECTION: rows},
                "WORKFORCE_ACTIVITY_RETIRED",
                actor,
                activity_key=str(activity_key),
                activity_version=int(current.get("version", 0)),
            )
        except persistence.ConcurrentWriteError as error:
            raise WorkActivityCatalogError(
                "Work activity catalog changed concurrently; retirement stopped safely, retry."
            ) from error
        return deepcopy(current)


def resolve_catalog_activity(activity_key: str, day: str) -> dict:
    tenant_id = persistence.tenant_id()
    at = _at(day)
    candidates: list[dict] = []
    for row in persistence.load_collection(_COLLECTION):
        if str(row.get("activity_key")) != str(activity_key):
            continue
        try:
            authority = _row_to_authority(row)
        except (KeyError, TypeError, ValueError, WorkActivityAuthorityError):
            continue
        if authority.is_effective(tenant_id=tenant_id, at=at):
            candidates.append(row)
    if not candidates:
        raise WorkActivityCatalogError(
            f"Approved effective work activity not found: {activity_key}"
        )
    if len(candidates) > 1:
        refs = ", ".join(str(row.get("id")) for row in candidates)
        raise WorkActivityCatalogError(
            f"Ambiguous work activity authority for {activity_key}: {refs}"
        )
    return deepcopy(candidates[0])


def resolve_activity_bundle(activity_keys: list[str], day: str) -> list[dict]:
    keys = [str(key).strip() for key in activity_keys if str(key).strip()]
    if len(keys) != len(set(keys)):
        raise WorkActivityCatalogError("Open-shift activity keys must be unique.")
    return [resolve_catalog_activity(key, day) for key in keys]
