from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine

from .schemas import FieldScope, LocationUpsert, MissionCreate, TargetSelector, TemplateCreate


class FieldRepositoryError(ValueError):
    pass


async def _set_tenant(connection, tenant_id: str) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


def _scope_allows_location(scope: FieldScope, location: dict[str, object]) -> bool:
    if scope.unrestricted:
        return True
    location_id = str(location["location_id"])
    region = str(location.get("region") or "")
    return location_id in scope.location_ids or (region and region in scope.regions)


def _structured_match(selector: TargetSelector, location: dict[str, object]) -> bool:
    checks: list[bool] = []
    if selector.all_active_locations:
        checks.append(True)
    if selector.countries:
        checks.append(str(location.get("country") or "") in selector.countries)
    if selector.regions:
        checks.append(str(location.get("region") or "") in selector.regions)
    if selector.cities:
        checks.append(str(location.get("city") or "") in selector.cities)
    if selector.districts:
        checks.append(str(location.get("district") or "") in selector.districts)
    if selector.location_groups:
        groups = set(location.get("groups") or ())
        checks.append(bool(groups & set(selector.location_groups)))
    return all(checks) if checks else False


def resolve_target_ids(
    locations: list[dict[str, object]],
    selector: TargetSelector,
    scope: FieldScope,
) -> tuple[str, ...]:
    excluded = set(selector.exclude_location_ids)
    selected: set[str] = set()
    includes = set(selector.include_location_ids)

    for location in locations:
        location_id = str(location["location_id"])
        if not bool(location["active"]) or location_id in excluded:
            continue
        if not _scope_allows_location(scope, location):
            continue
        if _structured_match(selector, location) or location_id in includes:
            selected.add(location_id)

    result = tuple(sorted(selected))
    if not result:
        raise FieldRepositoryError("mission target selector resolved to zero authorized active locations")
    return result


def target_fingerprint(tenant_id: str, target_ids: tuple[str, ...], created_at: datetime) -> str:
    canonical = json.dumps(
        {
            "tenant_id": tenant_id,
            "created_at": created_at.isoformat(),
            "location_ids": target_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def list_locations(tenant_id: str, scope: FieldScope) -> list[dict[str, object]]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT location_id, name, country, region, city, district, groups, active, source_ref, updated_at
                FROM field_locations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                ORDER BY active DESC, country NULLS LAST, region NULLS LAST, city NULLS LAST, name
                """
            ),
            {"tenant_id": tenant_id},
        )
        rows = [dict(row) for row in result.mappings().all()]
    return [row for row in rows if _scope_allows_location(scope, row)]


async def upsert_location(tenant_id: str, payload: LocationUpsert) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO field_locations (
                    tenant_id, location_id, name, country, region, city, district, groups, active, source_ref, updated_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), :location_id, :name, :country, :region, :city, :district,
                    CAST(:groups AS VARCHAR[]), :active, :source_ref, CURRENT_TIMESTAMP
                )
                ON CONFLICT (tenant_id, location_id) DO UPDATE SET
                    name=EXCLUDED.name, country=EXCLUDED.country, region=EXCLUDED.region,
                    city=EXCLUDED.city, district=EXCLUDED.district, groups=EXCLUDED.groups,
                    active=EXCLUDED.active, source_ref=EXCLUDED.source_ref, updated_at=CURRENT_TIMESTAMP
                RETURNING location_id, name, country, region, city, district, groups, active, source_ref, updated_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "location_id": payload.location_id,
                "name": payload.name,
                "country": payload.country,
                "region": payload.region,
                "city": payload.city,
                "district": payload.district,
                "groups": list(payload.groups),
                "active": payload.active,
                "source_ref": payload.source_ref,
            },
        )
        return dict(result.mappings().one())


async def list_templates(tenant_id: str) -> list[dict[str, object]]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT template_id, version, status, name_i18n, schema, created_by, created_at
                FROM field_templates
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                ORDER BY template_id, version DESC
                """
            ),
            {"tenant_id": tenant_id},
        )
        return [dict(row) for row in result.mappings().all()]


async def create_template(tenant_id: str, actor: str, payload: TemplateCreate) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                INSERT INTO field_templates (tenant_id, template_id, version, status, name_i18n, schema, created_by)
                VALUES (CAST(:tenant_id AS UUID), :template_id, :version, :status, CAST(:name_i18n AS JSONB), CAST(:schema AS JSONB), :created_by)
                RETURNING template_id, version, status, name_i18n, schema, created_by, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "template_id": payload.template_id,
                "version": payload.version,
                "status": payload.status,
                "name_i18n": json.dumps(payload.name.values, ensure_ascii=False),
                "schema": json.dumps(payload.schema, ensure_ascii=False),
                "created_by": actor,
            },
        )
        return dict(result.mappings().one())


async def create_mission(
    tenant_id: str,
    actor: str,
    payload: MissionCreate,
    scope: FieldScope,
) -> dict[str, object]:
    created_at = datetime.now(payload.assigned_at.tzinfo)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        template = await connection.execute(
            text(
                """
                SELECT status FROM field_templates
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND template_id=:template_id AND version=:version
                """
            ),
            {"tenant_id": tenant_id, "template_id": payload.template_id, "version": payload.template_version},
        )
        template_row = template.mappings().first()
        if template_row is None or template_row["status"] != "active":
            raise FieldRepositoryError("mission requires an active template version")

        location_result = await connection.execute(
            text(
                """
                SELECT location_id, name, country, region, city, district, groups, active
                FROM field_locations
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id},
        )
        locations = [dict(row) for row in location_result.mappings().all()]
        target_ids = resolve_target_ids(locations, payload.target_selector, scope)
        fingerprint = target_fingerprint(tenant_id, target_ids, created_at)
        status_value = "active" if payload.activate else "draft"

        mission_result = await connection.execute(
            text(
                """
                INSERT INTO field_missions (
                    tenant_id, template_id, template_version, title_i18n, instructions_i18n,
                    status, priority, selector, target_fingerprint, target_count,
                    assigned_at, deadline_at, created_by, created_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), :template_id, :template_version,
                    CAST(:title_i18n AS JSONB), CAST(:instructions_i18n AS JSONB),
                    :status, :priority, CAST(:selector AS JSONB), :fingerprint, :target_count,
                    :assigned_at, :deadline_at, :created_by, :created_at
                )
                RETURNING id, status, priority, target_fingerprint, target_count, assigned_at, deadline_at, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "template_id": payload.template_id,
                "template_version": payload.template_version,
                "title_i18n": json.dumps(payload.title.values, ensure_ascii=False),
                "instructions_i18n": json.dumps(payload.instructions.values if payload.instructions else {}, ensure_ascii=False),
                "status": status_value,
                "priority": payload.priority,
                "selector": payload.target_selector.model_dump_json(),
                "fingerprint": fingerprint,
                "target_count": len(target_ids),
                "assigned_at": payload.assigned_at,
                "deadline_at": payload.deadline_at,
                "created_by": actor,
                "created_at": created_at,
            },
        )
        mission = dict(mission_result.mappings().one())
        mission_id = mission["id"]
        for location_id in target_ids:
            await connection.execute(
                text(
                    """
                    INSERT INTO field_mission_targets (tenant_id, mission_id, location_id, status)
                    VALUES (CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id, 'unseen')
                    """
                ),
                {"tenant_id": tenant_id, "mission_id": str(mission_id), "location_id": location_id},
            )

    mission["id"] = str(mission["id"])
    mission["target_location_ids"] = target_ids
    return mission


async def list_missions(tenant_id: str, scope: FieldScope, limit: int = 100) -> list[dict[str, object]]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        return []

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT
                    m.id, m.template_id, m.template_version, m.title_i18n, m.status, m.priority,
                    m.target_fingerprint, m.target_count, m.assigned_at, m.deadline_at, m.created_by, m.created_at,
                    COALESCE(count(*) FILTER (WHERE t.status='verified'),0) AS verified,
                    COALESCE(count(*) FILTER (WHERE t.status='submitted'),0) AS submitted,
                    COALESCE(count(*) FILTER (WHERE t.status='rework'),0) AS rework,
                    COALESCE(count(*) FILTER (WHERE t.status='overdue'),0) AS overdue,
                    COALESCE(count(*) FILTER (WHERE t.status='unseen'),0) AS unseen
                FROM field_missions m
                JOIN field_mission_targets t ON t.tenant_id=m.tenant_id AND t.mission_id=m.id
                WHERE m.tenant_id=CAST(:tenant_id AS UUID)
                  AND t.location_id = ANY(CAST(:allowed_ids AS VARCHAR[]))
                GROUP BY m.tenant_id, m.id
                ORDER BY m.created_at DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "allowed_ids": sorted(allowed_ids), "limit": limit},
        )
        rows = []
        for row in result.mappings().all():
            item = dict(row)
            item["id"] = str(item["id"])
            rows.append(item)
        return rows
