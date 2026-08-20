from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def list_locale_settings(
    session: AsyncSession,
    principal: Principal,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT locale, enabled, required, is_default,
                           allow_machine_draft, created_by, updated_by,
                           created_at, updated_at
                    FROM academy_locale_settings
                    WHERE tenant_id = :tenant_id
                    ORDER BY is_default DESC, required DESC, locale
                    """
                ),
                {"tenant_id": principal.tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def upsert_locale_setting(
    session: AsyncSession,
    principal: Principal,
    *,
    locale: str,
    enabled: bool,
    required: bool,
    is_default: bool,
    allow_machine_draft: bool,
) -> dict[str, Any] | None:
    # Switching the default is atomic inside the request transaction. A direct
    # attempt to demote/disable the current default returns no row and fails closed.
    await session.execute(
        text(
            """
            UPDATE academy_locale_settings
            SET is_default = false,
                updated_by = CAST(:actor AS varchar(255)),
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = :tenant_id
              AND locale <> CAST(:locale AS varchar(16))
              AND is_default IS TRUE
              AND :is_default IS TRUE
            """
        ),
        {
            "tenant_id": principal.tenant_id,
            "locale": locale,
            "is_default": is_default,
            "actor": principal.subject,
        },
    )
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_locale_settings (
                        tenant_id, locale, enabled, required, is_default,
                        allow_machine_draft, created_by, updated_by
                    ) VALUES (
                        :tenant_id,
                        CAST(:locale AS varchar(16)),
                        :enabled,
                        :required,
                        :is_default,
                        :allow_machine_draft,
                        CAST(:actor AS varchar(255)),
                        CAST(:actor AS varchar(255))
                    )
                    ON CONFLICT (tenant_id, locale)
                    DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        required = EXCLUDED.required,
                        is_default = EXCLUDED.is_default,
                        allow_machine_draft = EXCLUDED.allow_machine_draft,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE NOT academy_locale_settings.is_default
                       OR EXCLUDED.is_default IS TRUE
                    RETURNING locale, enabled, required, is_default,
                              allow_machine_draft, created_by, updated_by,
                              created_at, updated_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "locale": locale,
                    "enabled": enabled,
                    "required": required,
                    "is_default": is_default,
                    "allow_machine_draft": allow_machine_draft,
                    "actor": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def create_translation_lineage(
    session: AsyncSession,
    principal: Principal,
    *,
    source_version_id: UUID,
    target_version_id: UUID,
    translation_method: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_translation_lineage (
                        tenant_id, content_id,
                        source_version_id, source_locale,
                        target_version_id, target_locale,
                        translation_method, translator_subject,
                        source_sha256_snapshot, created_by
                    )
                    SELECT
                        source.tenant_id,
                        source.content_id,
                        source.id,
                        source.locale,
                        target.id,
                        target.locale,
                        CAST(:translation_method AS varchar(30)),
                        CAST(:translator_subject AS varchar(255)),
                        source.source_sha256,
                        CAST(:translator_subject AS varchar(255))
                    FROM academy_content_versions AS source
                    JOIN academy_content_versions AS target
                      ON target.tenant_id = source.tenant_id
                     AND target.content_id = source.content_id
                    JOIN academy_locale_settings AS setting
                      ON setting.tenant_id = target.tenant_id
                     AND setting.locale = target.locale
                    WHERE source.tenant_id = :tenant_id
                      AND source.id = :source_version_id
                      AND target.id = :target_version_id
                      AND source.id <> target.id
                      AND source.locale <> target.locale
                      AND source.status = 'published'
                      AND target.status IN ('draft', 'published')
                      AND setting.enabled IS TRUE
                      AND (
                          CAST(:translation_method AS varchar(30)) <> 'machine_draft'
                          OR setting.allow_machine_draft IS TRUE
                      )
                    RETURNING id, content_id,
                              source_version_id, source_locale,
                              target_version_id, target_locale,
                              translation_method, translator_subject,
                              source_sha256_snapshot, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "source_version_id": source_version_id,
                    "target_version_id": target_version_id,
                    "translation_method": translation_method,
                    "translator_subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def submit_translation(
    session: AsyncSession,
    principal: Principal,
    *,
    translation_id: UUID,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_translation_review_events (
                        tenant_id, translation_id, event_type,
                        actor_subject, reason, request_id
                    )
                    SELECT
                        lineage.tenant_id,
                        lineage.id,
                        'submitted',
                        CAST(:actor_subject AS varchar(255)),
                        NULL,
                        CAST(:request_id AS varchar(128))
                    FROM academy_translation_lineage AS lineage
                    WHERE lineage.tenant_id = :tenant_id
                      AND lineage.id = :translation_id
                      AND lineage.translator_subject =
                          CAST(:actor_subject AS varchar(255))
                    RETURNING id, translation_id, event_type,
                              actor_subject, reason, request_id, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "translation_id": translation_id,
                    "actor_subject": principal.subject,
                    "request_id": request_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def review_translation(
    session: AsyncSession,
    principal: Principal,
    *,
    translation_id: UUID,
    decision: str,
    reason: str | None,
    request_id: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO academy_translation_review_events (
                        tenant_id, translation_id, event_type,
                        actor_subject, reason, request_id
                    )
                    SELECT
                        lineage.tenant_id,
                        lineage.id,
                        CAST(:decision AS varchar(20)),
                        CAST(:actor_subject AS varchar(255)),
                        CAST(:reason AS text),
                        CAST(:request_id AS varchar(128))
                    FROM academy_translation_lineage AS lineage
                    WHERE lineage.tenant_id = :tenant_id
                      AND lineage.id = :translation_id
                      AND lineage.translator_subject <>
                          CAST(:actor_subject AS varchar(255))
                    RETURNING id, translation_id, event_type,
                              actor_subject, reason, request_id, created_at
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "translation_id": translation_id,
                    "decision": decision,
                    "actor_subject": principal.subject,
                    "reason": reason,
                    "request_id": request_id,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


async def list_translation_authority(
    session: AsyncSession,
    principal: Principal,
    *,
    content_id: UUID | None = None,
) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT translation_id, content_id,
                           source_version_id, source_locale,
                           target_version_id, target_locale,
                           translation_method, translator_subject,
                           workflow_status, reviewer_subject,
                           review_reason, reviewed_at,
                           latest_published_source_version_id,
                           stale, authoritative
                    FROM academy_translation_authority
                    WHERE tenant_id = :tenant_id
                      AND (
                          CAST(:content_id AS uuid) IS NULL
                          OR content_id = CAST(:content_id AS uuid)
                      )
                    ORDER BY content_id, source_locale, target_locale, translation_id
                    """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "content_id": content_id,
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
