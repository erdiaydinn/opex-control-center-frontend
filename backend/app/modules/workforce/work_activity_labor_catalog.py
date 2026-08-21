"""Tenant-scoped labor-standard authority for generic Workforce activities.

Labor timings are never inferred from starter templates. Every standard must be
explicitly approved, effective-dated and tied to a governed activity version.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from threading import Lock
from zoneinfo import ZoneInfo

from . import persistence
from .work_activity_authority import ActivityLaborStandardVersion, WorkActivityAuthorityError
from .work_activity_catalog import WorkActivityCatalogError, resolve_catalog_activity


_COLLECTION = "workforce_activity_labor_standards"
_LOCK = Lock()


class ActivityLaborCatalogError(ValueError):
    """Raised when labor-standard authority cannot be resolved safely."""


def _at(day: str) -> datetime:
    return datetime.fromisoformat(f"{day}T00:00:00+03:00")


def _row_to_authority(row: dict) -> ActivityLaborStandardVersion:
    return ActivityLaborStandardVersion(
        tenant_id=str(row["tenant_id"]),
        activity_key=str(row["activity_key"]),
        version=int(row["version"]),
        seconds_per_unit=Decimal(str(row["seconds_per_unit"])),
        people=Decimal(str(row["people"])),
        effective_from=datetime.fromisoformat(str(row["effective_from"])),
        effective_until=datetime.fromisoformat(str(row["effective_until"])) if row.get("effective_until") else None,
        source_ref=str(row["source_ref"]),
        approved_by=str(row["approved_by"]),
        status=str(row.get("status") or "APPROVED"),
    )


def list_labor_standards(*, activity_key: str | None = None, include_retired: bool = False) -> list[dict]:
    rows = persistence.load_collection(_COLLECTION)
    if activity_key:
        rows = [row for row in rows if str(row.get("activity_key")) == str(activity_key)]
    if not include_retired:
        rows = [row for row in rows if row.get("status") == "APPROVED"]
    return deepcopy(sorted(rows, key=lambda row: (str(row.get("activity_key")), int(row.get("version", 0)))))


def approve_labor_standard(payload: dict, actor: str) -> dict:
    tenant_id = persistence.tenant_id()
    key = str(payload["activity_key"]).strip()
    effective_from = _at(str(payload["effective_from"]))
    try:
        activity = resolve_catalog_activity(key, str(payload["effective_from"]))
    except WorkActivityCatalogError as error:
        raise ActivityLaborCatalogError(
            f"Labor standard requires approved work activity authority: {key}"
        ) from error

    with _LOCK:
        rows = persistence.load_collection(_COLLECTION)
        versions = [row for row in rows if str(row.get("activity_key")) == key]
        version = max((int(row.get("version", 0)) for row in versions), default=0) + 1
        try:
            authority = ActivityLaborStandardVersion(
                tenant_id=tenant_id,
                activity_key=key,
                version=version,
                seconds_per_unit=Decimal(str(payload["seconds_per_unit"])),
                people=Decimal(str(payload.get("people", 1))),
                effective_from=effective_from,
                source_ref=str(payload["source_ref"]),
                approved_by=actor,
            )
        except WorkActivityAuthorityError as error:
            raise ActivityLaborCatalogError(str(error)) from error

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
            "id": f"LAB-{key}-V{version}",
            "tenant_id": tenant_id,
            "activity_key": key,
            "activity_authority_ref": str(activity.get("id")),
            "version": version,
            "seconds_per_unit": str(authority.seconds_per_unit),
            "people": str(authority.people),
            "effective_from": effective_from.isoformat(),
            "effective_until": None,
            "status": "APPROVED",
            "source_ref": authority.source_ref,
            "approved_by": actor,
            "approved_at": now,
        }
        rows.append(record)
        try:
            persistence.persist_snapshot_with_audit(
                {_COLLECTION: rows},
                "WORKFORCE_ACTIVITY_LABOR_STANDARD_APPROVED",
                actor,
                activity_key=key,
                activity_version=int(activity["version"]),
                labor_standard_version=version,
                source_ref=authority.source_ref,
                effective_from=effective_from.isoformat(),
            )
        except persistence.ConcurrentWriteError as error:
            raise ActivityLaborCatalogError(
                "Labor standard catalog changed concurrently; approval stopped safely, retry."
            ) from error
        return deepcopy(record)


def retire_labor_standard(activity_key: str, actor: str) -> dict:
    with _LOCK:
        rows = persistence.load_collection(_COLLECTION)
        candidates = [
            row for row in rows
            if str(row.get("activity_key")) == str(activity_key) and row.get("status") == "APPROVED"
        ]
        if not candidates:
            raise ActivityLaborCatalogError("Active labor standard was not found.")
        current = max(candidates, key=lambda row: int(row.get("version", 0)))
        current["status"] = "RETIRED"
        current["retired_at"] = datetime.now(ZoneInfo("UTC")).isoformat()
        current["retired_by"] = actor
        try:
            persistence.persist_snapshot_with_audit(
                {_COLLECTION: rows},
                "WORKFORCE_ACTIVITY_LABOR_STANDARD_RETIRED",
                actor,
                activity_key=str(activity_key),
                labor_standard_version=int(current.get("version", 0)),
            )
        except persistence.ConcurrentWriteError as error:
            raise ActivityLaborCatalogError(
                "Labor standard catalog changed concurrently; retirement stopped safely, retry."
            ) from error
        return deepcopy(current)


def resolve_labor_standard(activity_key: str, day: str) -> dict:
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
        raise ActivityLaborCatalogError(
            f"Approved effective labor standard not found: {activity_key}"
        )
    if len(candidates) > 1:
        refs = ", ".join(str(row.get("id")) for row in candidates)
        raise ActivityLaborCatalogError(
            f"Ambiguous labor standard authority for {activity_key}: {refs}"
        )
    return deepcopy(candidates[0])


def resolve_labor_bundle(activity_keys: list[str], day: str) -> list[dict]:
    keys = [str(key).strip() for key in activity_keys if str(key).strip()]
    if len(keys) != len(set(keys)):
        raise ActivityLaborCatalogError("Labor-standard activity keys must be unique.")
    return [resolve_labor_standard(key, day) for key in keys]
