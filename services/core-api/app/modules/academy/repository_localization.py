from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.localization import CORE_RELEASE_LOCALES, DEFAULT_LOCALE


async def get_localization_policy(
    session: AsyncSession,
    principal: Principal,
) -> dict[str, Any]:
    result = await session.execute(
        text(
            """
            SELECT default_locale, enabled_locales, revision, updated_by, updated_at
            FROM academy_localization_policies
            WHERE tenant_id = :tenant_id
            """
        ),
        {"tenant_id": principal.tenant_id},
    )
    row = result.mappings().first()
    if row is None:
        return {
            "default_locale": DEFAULT_LOCALE,
            "enabled_locales": list(CORE_RELEASE_LOCALES),
            "revision": 0,
            "configured": False,
            "updated_by": None,
            "updated_at": None,
        }
    return {
        "default_locale": row["default_locale"],
        "enabled_locales": list(row["enabled_locales"]),
        "revision": int(row["revision"]),
        "configured": True,
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


async def save_localization_policy(
    session: AsyncSession,
    principal: Principal,
    *,
    default_locale: str,
    enabled_locales: list[str],
    expected_revision: int,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            INSERT INTO academy_localization_policies (
                tenant_id, default_locale, enabled_locales, revision, updated_by
            )
            SELECT
                :tenant_id,
                :default_locale,
                CAST(:enabled_locales AS varchar(16)[]),
                1,
                :updated_by
            WHERE :expected_revision = 0
            ON CONFLICT (tenant_id) DO UPDATE SET
                default_locale = EXCLUDED.default_locale,
                enabled_locales = EXCLUDED.enabled_locales,
                revision = academy_localization_policies.revision + 1,
                updated_by = EXCLUDED.updated_by,
                updated_at = CURRENT_TIMESTAMP
            WHERE academy_localization_policies.revision = :expected_revision
            RETURNING default_locale, enabled_locales, revision, updated_by, updated_at
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "default_locale": default_locale,
            "enabled_locales": enabled_locales,
            "expected_revision": expected_revision,
            "updated_by": principal.subject,
        },
    )
    row = result.mappings().first()
    if row is None:
        return None
    return {
        "default_locale": row["default_locale"],
        "enabled_locales": list(row["enabled_locales"]),
        "revision": int(row["revision"]),
        "configured": True,
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }
