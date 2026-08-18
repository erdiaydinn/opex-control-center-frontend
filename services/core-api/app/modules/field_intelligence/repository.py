from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .schemas import (
    EvidenceReview,
    EvidenceSubmit,
    FieldScope,
    LocationUpsert,
    MissionCreate,
    NotificationIntentCreate,
    TargetSelector,
    TemplateCreate,
)


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
        raise FieldRepositoryError(
            "mission target selector resolved to zero authorized active locations"
        )
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


def _canonical_fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_numeric(value: object, field_key: str, config: dict[str, object]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FieldRepositoryError(f"field {field_key} must be numeric")
    minimum = config.get("min")
    maximum = config.get("max")
    if isinstance(minimum, (int, float)) and value < minimum:
        raise FieldRepositoryError(f"field {field_key} is below configured minimum")
    if isinstance(maximum, (int, float)) and value > maximum:
        raise FieldRepositoryError(f"field {field_key} exceeds configured maximum")


def _validate_evidence_payload(
    template_schema: dict[str, object], payload: dict[str, object]
) -> None:
    raw_fields = template_schema.get("fields")
    if not isinstance(raw_fields, list):
        raise FieldRepositoryError("template schema is missing governed fields")

    field_definitions: dict[str, dict[str, object]] = {}
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict) or not isinstance(raw_field.get("key"), str):
            raise FieldRepositoryError("template schema contains an invalid field definition")
        field_definitions[str(raw_field["key"])] = raw_field

    unknown = set(payload) - set(field_definitions)
    if unknown:
        raise FieldRepositoryError(
            f"evidence contains unknown fields: {', '.join(sorted(unknown))}"
        )

    for key, definition in field_definitions.items():
        required = bool(definition.get("required"))
        if key not in payload:
            if required:
                raise FieldRepositoryError(f"required field missing: {key}")
            continue

        value = payload[key]
        field_type = str(definition.get("type") or "")
        config = definition.get("config") if isinstance(definition.get("config"), dict) else {}

        if field_type in {"text", "barcode", "qr", "lot", "batch"}:
            if not isinstance(value, str) or not value.strip():
                raise FieldRepositoryError(f"field {key} must be a non-blank string")
        elif field_type == "select":
            options = definition.get("options")
            if not isinstance(value, str) or not isinstance(options, list) or value not in options:
                raise FieldRepositoryError(f"field {key} must use a configured option")
        elif field_type in {"number", "quantity", "measurement"}:
            _validate_numeric(value, key, config)
            if field_type == "quantity" and value < 0:
                raise FieldRepositoryError(f"field {key} cannot be negative")
        elif field_type == "expiry":
            if not isinstance(value, str):
                raise FieldRepositoryError(f"field {key} must be an ISO date")
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise FieldRepositoryError(f"field {key} must be an ISO date") from exc
        elif field_type == "yes_no":
            if not isinstance(value, bool):
                raise FieldRepositoryError(f"field {key} must be true or false")
        elif field_type == "gps":
            if not isinstance(value, dict):
                raise FieldRepositoryError(f"field {key} must be a GPS observation")
            latitude = value.get("latitude")
            longitude = value.get("longitude")
            accuracy = value.get("accuracy_m")
            if any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in (latitude, longitude, accuracy)
            ):
                raise FieldRepositoryError(f"field {key} GPS coordinates are invalid")
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or accuracy < 0:
                raise FieldRepositoryError(f"field {key} GPS coordinates are out of range")
        elif field_type == "multi_row":
            if not isinstance(value, list):
                raise FieldRepositoryError(f"field {key} must be a row list")
            max_rows = config.get("max_rows", 100)
            if not isinstance(max_rows, int) or max_rows < 1:
                max_rows = 100
            if len(value) > max_rows or any(not isinstance(row, dict) for row in value):
                raise FieldRepositoryError(f"field {key} contains invalid rows")
        elif field_type == "photo":
            # Raw/base64/browser file payloads are intentionally rejected. Until the
            # private evidence transport is wired, photo capture must supply an opaque
            # private evidence reference and its content fingerprint.
            if not isinstance(value, dict):
                raise FieldRepositoryError(f"field {key} requires a private evidence reference")
            evidence_reference = value.get("evidence_reference")
            fingerprint = value.get("fingerprint")
            if not isinstance(evidence_reference, str) or not evidence_reference.strip():
                raise FieldRepositoryError(f"field {key} requires a private evidence reference")
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or any(character not in "0123456789abcdef" for character in fingerprint)
            ):
                raise FieldRepositoryError(f"field {key} evidence fingerprint is invalid")
        else:
            raise FieldRepositoryError(f"template field type is unsupported: {field_type}")


async def list_locations(tenant_id: str, scope: FieldScope) -> list[dict[str, object]]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                SELECT location_id, name, country, region, city, district, groups, active,
                source_ref, updated_at
                FROM field_locations
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                ORDER BY active DESC, country NULLS LAST, region NULLS LAST, city NULLS LAST,
                name
                """),
            {"tenant_id": tenant_id},
        )
        rows = [dict(row) for row in result.mappings().all()]
    return [row for row in rows if _scope_allows_location(scope, row)]


async def upsert_location(tenant_id: str, payload: LocationUpsert) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                INSERT INTO field_locations (
                    tenant_id, location_id, name, country, region, city, district, groups,
                    active, source_ref, updated_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), :location_id, :name, :country, :region, :city,
                    :district,
                    CAST(:groups AS VARCHAR[]), :active, :source_ref, CURRENT_TIMESTAMP
                )
                ON CONFLICT (tenant_id, location_id) DO UPDATE SET
                    name=EXCLUDED.name, country=EXCLUDED.country, region=EXCLUDED.region,
                    city=EXCLUDED.city, district=EXCLUDED.district, groups=EXCLUDED.groups,
                    active=EXCLUDED.active, source_ref=EXCLUDED.source_ref,
                    updated_at=CURRENT_TIMESTAMP
                RETURNING location_id, name, country, region, city, district, groups, active,
                source_ref, updated_at
                """),
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
            text("""
                SELECT template_id, version, status, name_i18n, schema, created_by, created_at
                FROM field_templates
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                ORDER BY template_id, version DESC
                """),
            {"tenant_id": tenant_id},
        )
        return [dict(row) for row in result.mappings().all()]


async def create_template(tenant_id: str, actor: str, payload: TemplateCreate) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                INSERT INTO field_templates (tenant_id, template_id, version, status, name_i18n,
                schema, created_by)
                VALUES (CAST(:tenant_id AS UUID), :template_id, :version, :status,
                CAST(:name_i18n AS JSONB), CAST(:schema AS JSONB), :created_by)
                RETURNING template_id, version, status, name_i18n, schema, created_by,
                created_at
                """),
            {
                "tenant_id": tenant_id,
                "template_id": payload.template_id,
                "version": payload.version,
                "status": payload.status,
                "name_i18n": json.dumps(payload.name.values, ensure_ascii=False),
                "schema": json.dumps(payload.schema.model_dump(mode="json"), ensure_ascii=False),
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
    created_at = datetime.now(UTC)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        template = await connection.execute(
            text("""
                SELECT status FROM field_templates
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND template_id=:template_id AND
                version=:version
                """),
            {
                "tenant_id": tenant_id,
                "template_id": payload.template_id,
                "version": payload.template_version,
            },
        )
        template_row = template.mappings().first()
        if template_row is None or template_row["status"] != "active":
            raise FieldRepositoryError("mission requires an active template version")

        location_result = await connection.execute(
            text("""
                SELECT location_id, name, country, region, city, district, groups, active
                FROM field_locations
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                """),
            {"tenant_id": tenant_id},
        )
        locations = [dict(row) for row in location_result.mappings().all()]
        target_ids = resolve_target_ids(locations, payload.target_selector, scope)
        fingerprint = target_fingerprint(tenant_id, target_ids, created_at)
        status_value = "active" if payload.activate else "draft"

        mission_result = await connection.execute(
            text("""
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
                RETURNING id, status, priority, target_fingerprint, target_count, assigned_at,
                deadline_at, created_at
                """),
            {
                "tenant_id": tenant_id,
                "template_id": payload.template_id,
                "template_version": payload.template_version,
                "title_i18n": json.dumps(payload.title.values, ensure_ascii=False),
                "instructions_i18n": json.dumps(
                    payload.instructions.values if payload.instructions else {}, ensure_ascii=False
                ),
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
                text("""
                    INSERT INTO field_mission_targets (tenant_id, mission_id, location_id,
                    status)
                    VALUES (CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                    'unseen')
                    """),
                {"tenant_id": tenant_id, "mission_id": str(mission_id), "location_id": location_id},
            )

    mission["id"] = str(mission["id"])
    mission["target_location_ids"] = target_ids
    return mission


async def list_missions(
    tenant_id: str, scope: FieldScope, limit: int = 100
) -> list[dict[str, object]]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        return []

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                SELECT
                    m.id, m.template_id, m.template_version, m.title_i18n, m.status, m.priority,
                    m.target_fingerprint, count(*) AS target_count, m.assigned_at,
                    m.deadline_at, m.created_by, m.created_at,
                    COALESCE(count(*) FILTER (WHERE t.status='verified'),0) AS verified,
                    COALESCE(count(*) FILTER (WHERE t.status='submitted'),0) AS submitted,
                    COALESCE(count(*) FILTER (WHERE t.status='rework'),0) AS rework,
                    COALESCE(count(*) FILTER (WHERE t.status='overdue'),0) AS overdue,
                    COALESCE(count(*) FILTER (WHERE t.status='unseen'),0) AS unseen,
                    COALESCE(count(*) FILTER (WHERE t.status='started'),0) AS started,
                    COALESCE(count(*) FILTER (WHERE t.status='partial'),0) AS partial,
                    COALESCE(count(*) FILTER (WHERE t.status='exempt'),0) AS exempt
                FROM field_missions m
                JOIN field_mission_targets t ON t.tenant_id=m.tenant_id AND t.mission_id=m.id
                WHERE m.tenant_id=CAST(:tenant_id AS UUID)
                  AND t.location_id = ANY(CAST(:allowed_ids AS VARCHAR[]))
                GROUP BY m.tenant_id, m.id
                ORDER BY m.created_at DESC
                LIMIT :limit
                """),
            {"tenant_id": tenant_id, "allowed_ids": sorted(allowed_ids), "limit": limit},
        )
        rows = []
        for row in result.mappings().all():
            item = dict(row)
            item["id"] = str(item["id"])
            item["is_deadline_overdue"] = bool(
                item["status"] == "active" and item["deadline_at"] < datetime.now(UTC)
            )
            rows.append(item)
        return rows


async def get_mission_detail(
    tenant_id: str, scope: FieldScope, mission_id: str
) -> dict[str, object] | None:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        return None

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        mission_result = await connection.execute(
            text("""
                SELECT m.id, m.template_id, m.template_version, m.title_i18n,
                m.instructions_i18n,
                       m.status, m.priority, m.selector, m.target_fingerprint,
                       m.assigned_at, m.deadline_at, m.created_by, m.created_at,
                       ft.name_i18n AS template_name_i18n, ft.schema AS template_schema
                FROM field_missions m
                JOIN field_templates ft ON ft.tenant_id=m.tenant_id
                  AND ft.template_id=m.template_id AND ft.version=m.template_version
                WHERE m.tenant_id=CAST(:tenant_id AS UUID) AND m.id=CAST(:mission_id AS UUID)
                  AND EXISTS (
                    SELECT 1 FROM field_mission_targets scoped
                    WHERE scoped.tenant_id=m.tenant_id AND scoped.mission_id=m.id
                      AND scoped.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                  )
                """),
            {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": sorted(allowed_ids)},
        )
        mission_row = mission_result.mappings().first()
        if mission_row is None:
            return None

        target_result = await connection.execute(
            text("""
                SELECT t.location_id, l.name AS location_name, l.country, l.region, l.city,
                l.district,
                       t.status, t.updated_at,
                       latest.id AS latest_evidence_id, latest.submitted_at AS
                       latest_submitted_at,
                       review.decision AS latest_review_decision, review.reason AS
                       latest_review_reason,
                       review.reviewed_at AS latest_reviewed_at
                FROM field_mission_targets t
                JOIN field_locations l ON l.tenant_id=t.tenant_id AND
                l.location_id=t.location_id
                LEFT JOIN LATERAL (
                    SELECT e.id, e.submitted_at
                    FROM field_evidence e
                    WHERE e.tenant_id=t.tenant_id AND e.mission_id=t.mission_id AND
                    e.location_id=t.location_id
                    ORDER BY e.submitted_at DESC, e.id DESC LIMIT 1
                ) latest ON TRUE
                LEFT JOIN LATERAL (
                    SELECT r.decision, r.reason, r.reviewed_at
                    FROM field_reviews r
                    WHERE r.tenant_id=t.tenant_id AND r.evidence_id=latest.id
                    ORDER BY r.reviewed_at DESC, r.id DESC LIMIT 1
                ) review ON TRUE
                WHERE t.tenant_id=CAST(:tenant_id AS UUID) AND t.mission_id=CAST(:mission_id AS
                UUID)
                  AND t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                ORDER BY l.name, t.location_id
                """),
            {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": sorted(allowed_ids)},
        )

        mission = dict(mission_row)
        mission["id"] = str(mission["id"])
        targets: list[dict[str, object]] = []
        for row in target_result.mappings().all():
            target = dict(row)
            if target.get("latest_evidence_id") is not None:
                target["latest_evidence_id"] = str(target["latest_evidence_id"])
            targets.append(target)
        mission["targets"] = targets
        mission["target_count"] = len(targets)
        mission["is_deadline_overdue"] = bool(
            mission["status"] == "active" and mission["deadline_at"] < datetime.now(UTC)
        )
        return mission


async def set_mission_status(
    tenant_id: str,
    scope: FieldScope,
    mission_id: str,
    *,
    transition: str,
) -> dict[str, object]:
    detail = await get_mission_detail(tenant_id, scope, mission_id)
    if detail is None:
        raise FieldRepositoryError("mission not found in authorized scope")
    current_status = str(detail["status"])
    if transition == "activate":
        if current_status != "draft":
            raise FieldRepositoryError("only draft missions can be activated")
        next_status = "active"
    elif transition == "cancel":
        if current_status not in {"draft", "active"}:
            raise FieldRepositoryError("mission cannot be cancelled from its current status")
        next_status = "cancelled"
    else:
        raise FieldRepositoryError("unsupported mission transition")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                UPDATE field_missions SET status=:next_status
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND id=CAST(:mission_id AS UUID) AND
                status=:current_status
                RETURNING id, status, target_fingerprint, target_count, assigned_at, deadline_at
                """),
            {
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "current_status": current_status,
                "next_status": next_status,
            },
        )
        row = result.mappings().first()
        if row is None:
            raise FieldRepositoryError("mission transition lost a concurrent update race")
        item = dict(row)
        item["id"] = str(item["id"])
        return item


async def submit_evidence(
    tenant_id: str,
    actor: str,
    scope: FieldScope,
    mission_id: str,
    location_id: str,
    payload: EvidenceSubmit,
) -> dict[str, object]:
    allowed_locations = await list_locations(tenant_id, scope)
    if location_id not in {str(item["location_id"]) for item in allowed_locations}:
        raise FieldRepositoryError("target location is outside authorized scope")

    submitted_at = datetime.now(UTC)
    fingerprint_payload = {
        "tenant_id": tenant_id,
        "mission_id": mission_id,
        "location_id": location_id,
        "actor": actor,
        "client_submission_id": str(payload.client_submission_id),
        "payload": payload.payload,
    }
    fingerprint = _canonical_fingerprint(fingerprint_payload)

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        target_result = await connection.execute(
            text("""
                SELECT t.status, m.status AS mission_status, ft.schema AS template_schema
                FROM field_mission_targets t
                JOIN field_missions m ON m.tenant_id=t.tenant_id AND m.id=t.mission_id
                JOIN field_templates ft ON ft.tenant_id=m.tenant_id AND
                ft.template_id=m.template_id AND ft.version=m.template_version
                WHERE t.tenant_id=CAST(:tenant_id AS UUID) AND t.mission_id=CAST(:mission_id AS
                UUID)
                  AND t.location_id=:location_id
                FOR UPDATE OF t
                """),
            {"tenant_id": tenant_id, "mission_id": mission_id, "location_id": location_id},
        )
        target = target_result.mappings().first()
        if target is None:
            raise FieldRepositoryError("mission target not found")
        if target["mission_status"] != "active":
            raise FieldRepositoryError("evidence can only be submitted to an active mission")
        if target["status"] in {"verified", "exempt"}:
            raise FieldRepositoryError("verified or exempt targets cannot accept new evidence")

        _validate_evidence_payload(dict(target["template_schema"]), payload.payload)

        existing_result = await connection.execute(
            text("""
                SELECT id, fingerprint, submitted_at
                FROM field_evidence
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND mission_id=CAST(:mission_id AS
                UUID)
                  AND location_id=:location_id AND client_submission_id=:client_submission_id
                """),
            {
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "location_id": location_id,
                "client_submission_id": str(payload.client_submission_id),
            },
        )
        existing = existing_result.mappings().first()
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                raise FieldRepositoryError("client submission id replayed with different evidence")
            return {
                "id": str(existing["id"]),
                "fingerprint": existing["fingerprint"],
                "submitted_at": existing["submitted_at"],
                "target_status": "submitted",
                "idempotent_replay": True,
            }

        try:
            evidence_result = await connection.execute(
                text("""
                    INSERT INTO field_evidence (
                        tenant_id, mission_id, location_id, actor_subject, device_id,
                        client_submission_id, fingerprint, payload, submitted_at
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                        :actor_subject, :device_id,
                        :client_submission_id, :fingerprint, CAST(:payload AS JSONB),
                        :submitted_at
                    )
                    RETURNING id, fingerprint, submitted_at
                    """),
                {
                    "tenant_id": tenant_id,
                    "mission_id": mission_id,
                    "location_id": location_id,
                    "actor_subject": actor,
                    "device_id": payload.device_id,
                    "client_submission_id": str(payload.client_submission_id),
                    "fingerprint": fingerprint,
                    "payload": json.dumps(payload.payload, ensure_ascii=False, sort_keys=True),
                    "submitted_at": submitted_at,
                },
            )
        except IntegrityError as exc:
            raise FieldRepositoryError(
                "evidence submission collided with a concurrent replay; retry safely"
            ) from exc

        await connection.execute(
            text("""
                UPDATE field_mission_targets SET status='submitted',
                updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND mission_id=CAST(:mission_id AS
                UUID) AND location_id=:location_id
                """),
            {"tenant_id": tenant_id, "mission_id": mission_id, "location_id": location_id},
        )
        evidence = dict(evidence_result.mappings().one())
        evidence["id"] = str(evidence["id"])
        evidence["target_status"] = "submitted"
        evidence["idempotent_replay"] = False
        evidence["observed_at"] = payload.observed_at
        evidence["device_trust"] = (
            "unverified_client_claim" if payload.device_id else "not_supplied"
        )
        return evidence


async def list_evidence(
    tenant_id: str,
    scope: FieldScope,
    *,
    mission_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        return []

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                SELECT e.id, e.mission_id, e.location_id, l.name AS location_name,
                e.actor_subject,
                       e.device_id, e.client_submission_id, e.fingerprint, e.payload,
                       e.submitted_at,
                       r.decision AS review_decision, r.reason AS review_reason,
                       r.reviewer_subject, r.reviewed_at
                FROM field_evidence e
                JOIN field_locations l ON l.tenant_id=e.tenant_id AND
                l.location_id=e.location_id
                LEFT JOIN LATERAL (
                    SELECT decision, reason, reviewer_subject, reviewed_at
                    FROM field_reviews review
                    WHERE review.tenant_id=e.tenant_id AND review.evidence_id=e.id
                    ORDER BY review.reviewed_at DESC, review.id DESC LIMIT 1
                ) r ON TRUE
                WHERE e.tenant_id=CAST(:tenant_id AS UUID)
                  AND e.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                  AND (:mission_id IS NULL OR e.mission_id=CAST(:mission_id AS UUID))
                ORDER BY e.submitted_at DESC, e.id DESC
                LIMIT :limit
                """),
            {
                "tenant_id": tenant_id,
                "allowed_ids": sorted(allowed_ids),
                "mission_id": mission_id,
                "limit": limit,
            },
        )
        items: list[dict[str, object]] = []
        for row in result.mappings().all():
            item = dict(row)
            item["id"] = str(item["id"])
            item["mission_id"] = str(item["mission_id"])
            items.append(item)
        return items


async def review_evidence(
    tenant_id: str,
    actor: str,
    scope: FieldScope,
    evidence_id: str,
    payload: EvidenceReview,
) -> dict[str, object]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        raise FieldRepositoryError("no authorized Field locations")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        evidence_result = await connection.execute(
            text("""
                SELECT e.id, e.mission_id, e.location_id, t.status AS target_status,
                       latest.id AS latest_evidence_id,
                       EXISTS (
                         SELECT 1 FROM field_reviews existing
                         WHERE existing.tenant_id=e.tenant_id AND existing.evidence_id=e.id
                       ) AS already_reviewed
                FROM field_evidence e
                JOIN field_mission_targets t ON t.tenant_id=e.tenant_id
                  AND t.mission_id=e.mission_id AND t.location_id=e.location_id
                JOIN LATERAL (
                    SELECT candidate.id
                    FROM field_evidence candidate
                    WHERE candidate.tenant_id=e.tenant_id AND candidate.mission_id=e.mission_id
                      AND candidate.location_id=e.location_id
                    ORDER BY candidate.submitted_at DESC, candidate.id DESC LIMIT 1
                ) latest ON TRUE
                WHERE e.tenant_id=CAST(:tenant_id AS UUID) AND e.id=CAST(:evidence_id AS UUID)
                  AND e.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                FOR UPDATE OF t
                """),
            {
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "allowed_ids": sorted(allowed_ids),
            },
        )
        evidence = evidence_result.mappings().first()
        if evidence is None:
            raise FieldRepositoryError("evidence not found in authorized scope")
        if str(evidence["latest_evidence_id"]) != str(evidence["id"]):
            raise FieldRepositoryError("stale evidence cannot determine current target truth")
        if evidence["already_reviewed"]:
            raise FieldRepositoryError("evidence already has a review decision")
        if evidence["target_status"] != "submitted":
            raise FieldRepositoryError("only submitted evidence can be reviewed")

        review_result = await connection.execute(
            text("""
                INSERT INTO field_reviews (
                    tenant_id, evidence_id, mission_id, location_id,
                    reviewer_subject, decision, reason
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:evidence_id AS UUID), CAST(:mission_id AS
                    UUID), :location_id,
                    :reviewer_subject, :decision, :reason
                )
                RETURNING id, evidence_id, mission_id, location_id, reviewer_subject, decision,
                reason, reviewed_at
                """),
            {
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "mission_id": str(evidence["mission_id"]),
                "location_id": evidence["location_id"],
                "reviewer_subject": actor,
                "decision": payload.decision,
                "reason": payload.reason.strip() if payload.reason else None,
            },
        )
        next_status = "verified" if payload.decision == "accept" else "rework"
        await connection.execute(
            text("""
                UPDATE field_mission_targets SET status=:next_status,
                updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=CAST(:tenant_id AS UUID) AND mission_id=CAST(:mission_id AS
                UUID) AND location_id=:location_id
                """),
            {
                "tenant_id": tenant_id,
                "mission_id": str(evidence["mission_id"]),
                "location_id": evidence["location_id"],
                "next_status": next_status,
            },
        )
        review = dict(review_result.mappings().one())
        for key in ("id", "evidence_id", "mission_id"):
            review[key] = str(review[key])
        review["target_status"] = next_status
        return review


async def queue_notification_intents(
    tenant_id: str,
    actor: str,
    scope: FieldScope,
    mission_id: str,
    payload: NotificationIntentCreate,
) -> dict[str, object]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    requested_ids = set(payload.location_ids)
    if requested_ids and not requested_ids <= allowed_ids:
        raise FieldRepositoryError("notification target includes an unauthorized location")

    now = datetime.now(UTC)
    five_minute_bucket = int(now.timestamp() // 300)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        target_result = await connection.execute(
            text("""
                SELECT t.location_id, t.status, m.status AS mission_status
                FROM field_mission_targets t
                JOIN field_missions m ON m.tenant_id=t.tenant_id AND m.id=t.mission_id
                WHERE t.tenant_id=CAST(:tenant_id AS UUID) AND t.mission_id=CAST(:mission_id AS
                UUID)
                  AND t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                  AND t.status NOT IN ('verified','exempt')
                ORDER BY t.location_id
                """),
            {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": sorted(allowed_ids)},
        )
        targets = [dict(row) for row in target_result.mappings().all()]
        if not targets:
            raise FieldRepositoryError("mission has no actionable targets in authorized scope")
        if any(target["mission_status"] != "active" for target in targets):
            raise FieldRepositoryError("notifications can only be queued for an active mission")

        selected = [
            target
            for target in targets
            if not requested_ids or target["location_id"] in requested_ids
        ]
        if requested_ids and len(selected) != len(requested_ids):
            raise FieldRepositoryError("notification target is not actionable for this mission")

        intent_ids: list[str] = []
        for target in selected:
            idempotency_key = _canonical_fingerprint(
                {
                    "tenant_id": tenant_id,
                    "mission_id": mission_id,
                    "location_id": target["location_id"],
                    "kind": payload.kind,
                    "reason_code": payload.reason_code,
                    "target_status": target["status"],
                    "bucket": five_minute_bucket,
                }
            )
            intent_result = await connection.execute(
                text("""
                    INSERT INTO field_notification_intents (
                        tenant_id, mission_id, location_id, kind, reason_code,
                        requested_by, idempotency_key, status
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                        :kind, :reason_code,
                        :requested_by, :idempotency_key, 'queued'
                    )
                    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                    RETURNING id
                    """),
                {
                    "tenant_id": tenant_id,
                    "mission_id": mission_id,
                    "location_id": target["location_id"],
                    "kind": payload.kind,
                    "reason_code": payload.reason_code,
                    "requested_by": actor,
                    "idempotency_key": idempotency_key,
                },
            )
            inserted = intent_result.scalar_one_or_none()
            if inserted is not None:
                intent_ids.append(str(inserted))

        return {
            "mission_id": mission_id,
            "kind": payload.kind,
            "requested_targets": len(selected),
            "queued_count": len(intent_ids),
            "intent_ids": intent_ids,
            "delivery_state": "queued_not_dispatched",
            "provider_authority": "shared_notification_center_required",
        }


async def field_analytics(tenant_id: str, scope: FieldScope) -> dict[str, object]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    if not allowed_ids:
        return {
            "mission_count": 0,
            "active_mission_count": 0,
            "target_count": 0,
            "status_counts": {},
            "completion_percent": 0.0,
            "deadline_overdue_targets": 0,
        }

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        summary_result = await connection.execute(
            text("""
                SELECT
                    count(DISTINCT m.id) AS mission_count,
                    count(DISTINCT m.id) FILTER (WHERE m.status='active') AS
                    active_mission_count,
                    count(*) AS target_count,
                    count(*) FILTER (WHERE t.status='verified') AS verified,
                    count(*) FILTER (WHERE t.status='submitted') AS submitted,
                    count(*) FILTER (WHERE t.status='rework') AS rework,
                    count(*) FILTER (WHERE t.status='overdue') AS overdue,
                    count(*) FILTER (WHERE t.status='unseen') AS unseen,
                    count(*) FILTER (WHERE t.status='seen') AS seen,
                    count(*) FILTER (WHERE t.status='started') AS started,
                    count(*) FILTER (WHERE t.status='partial') AS partial,
                    count(*) FILTER (WHERE t.status='exempt') AS exempt,
                    count(*) FILTER (
                        WHERE m.status='active' AND m.deadline_at<CURRENT_TIMESTAMP
                          AND t.status NOT IN ('verified','exempt')
                    ) AS deadline_overdue_targets
                FROM field_mission_targets t
                JOIN field_missions m ON m.tenant_id=t.tenant_id AND m.id=t.mission_id
                WHERE t.tenant_id=CAST(:tenant_id AS UUID)
                  AND t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                """),
            {"tenant_id": tenant_id, "allowed_ids": sorted(allowed_ids)},
        )
        row = dict(summary_result.mappings().one())
        target_count = int(row.get("target_count") or 0)
        verified = int(row.get("verified") or 0)
        exempt = int(row.get("exempt") or 0)
        status_counts = {
            status: int(row.get(status) or 0)
            for status in (
                "unseen",
                "seen",
                "started",
                "partial",
                "submitted",
                "rework",
                "verified",
                "overdue",
                "exempt",
            )
        }
        return {
            "mission_count": int(row.get("mission_count") or 0),
            "active_mission_count": int(row.get("active_mission_count") or 0),
            "target_count": target_count,
            "status_counts": status_counts,
            "completion_percent": (
                round(((verified + exempt) / target_count * 100.0), 2) if target_count else 0.0
            ),
            "deadline_overdue_targets": int(row.get("deadline_overdue_targets") or 0),
        }
