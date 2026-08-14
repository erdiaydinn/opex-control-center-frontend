from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def create_learning_path(
    session: AsyncSession, principal: Principal, payload: Any
) -> dict[str, Any]:
    role_keys = [assignment.role_key.strip().lower() for assignment in payload.role_assignments]
    if len(role_keys) != len(set(role_keys)):
        raise ValueError("Learning path contains duplicate role assignment")
    if role_keys:
        registered_role_keys = set(
            (
                await session.execute(
                    text("""
                    SELECT key
                    FROM roles
                    WHERE tenant_id=:tenant_id
                    """),
                    {"tenant_id": principal.tenant_id},
                )
            )
            .scalars()
            .all()
        )
        authenticated_role_keys = {
            role.strip().lower() for role in principal.roles if role.strip()
        }
        known_role_keys = registered_role_keys | authenticated_role_keys
        if set(role_keys) - known_role_keys:
            raise ValueError("Learning path contains unknown role assignment")

    content_version_ids = [item.content_version_id for item in payload.items]
    if len(content_version_ids) != len(set(content_version_ids)):
        raise ValueError("Learning path contains duplicate content version")

    path = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_learning_paths (
            tenant_id, key, title_i18n, description_i18n, certificate_enabled,
            completion_policy, status, created_by
        ) VALUES (
            :tenant_id, :key, CAST(:title_i18n AS jsonb), CAST(:description_i18n AS jsonb),
            :certificate_enabled, CAST(:completion_policy AS jsonb), :status, :created_by
        ) RETURNING id, key, title_i18n, description_i18n, certificate_enabled,
                    completion_policy, status
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "key": payload.key,
                    "title_i18n": json_text(payload.title_i18n),
                    "description_i18n": json_text(payload.description_i18n),
                    "certificate_enabled": payload.certificate_enabled,
                    "completion_policy": json_text(payload.completion_policy),
                    "status": payload.status,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one()
    )
    for ordinal, item in enumerate(payload.items, 1):
        inserted = await session.scalar(
            text("""
            INSERT INTO academy_learning_path_items (
                tenant_id, path_id, content_version_id, ordinal, required, completion_policy
            ) SELECT :tenant_id, :path_id, cv.id, :ordinal, :required,
                     CAST(:completion_policy AS jsonb)
              FROM academy_content_versions AS cv
              WHERE cv.tenant_id=:tenant_id AND cv.id=:content_version_id
                AND cv.status='published'
            RETURNING content_version_id
        """),
            {
                "tenant_id": principal.tenant_id,
                "path_id": path["id"],
                "content_version_id": item.content_version_id,
                "ordinal": ordinal,
                "required": item.required,
                "completion_policy": json_text(item.completion_policy),
            },
        )
        if inserted is None:
            raise ValueError("Learning path contains missing or unpublished content version")
    for assignment, role_key in zip(payload.role_assignments, role_keys, strict=True):
        await session.execute(
            text("""
            INSERT INTO academy_path_role_assignments (
                tenant_id, path_id, role_key, required, due_days
            ) VALUES (:tenant_id, :path_id, :role_key, :required, :due_days)
        """),
            {
                "tenant_id": principal.tenant_id,
                "path_id": path["id"],
                "role_key": role_key,
                "required": assignment.required,
                "due_days": assignment.due_days,
            },
        )
    return dict(path)


async def grant_entitlement(
    session: AsyncSession, principal: Principal, payload: Any
) -> dict[str, Any]:
    principal_key = payload.principal_key.strip()
    if payload.principal_type == "role":
        principal_key = principal_key.lower()
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_entitlements (
            tenant_id, resource_type, resource_id, principal_type, principal_key,
            permission, starts_at, ends_at, created_by
        ) VALUES (
            :tenant_id, :resource_type, :resource_id, :principal_type, :principal_key,
            :permission, :starts_at, :ends_at, :created_by
        ) ON CONFLICT (
            tenant_id, resource_type, resource_id, principal_type, principal_key, permission
        ) DO UPDATE SET starts_at=EXCLUDED.starts_at, ends_at=EXCLUDED.ends_at
        RETURNING id, resource_type, resource_id, principal_type, principal_key,
                  permission, starts_at, ends_at
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "resource_type": payload.resource_type,
                    "resource_id": payload.resource_id,
                    "principal_type": payload.principal_type,
                    "principal_key": principal_key,
                    "permission": payload.permission,
                    "starts_at": payload.starts_at,
                    "ends_at": payload.ends_at,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one()
    )
    return dict(row)
