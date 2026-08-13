from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def create_content(
    session: AsyncSession,
    principal: Principal,
    payload: Any,
) -> dict[str, Any]:
    item = (
        await session.execute(
            text(
                """
                INSERT INTO academy_content_items (
                    tenant_id,
                    content_type,
                    slug,
                    title_i18n,
                    description_i18n,
                    status,
                    created_by
                )
                VALUES (
                    :tenant_id,
                    :content_type,
                    :slug,
                    CAST(:title_i18n AS jsonb),
                    CAST(:description_i18n AS jsonb),
                    :status,
                    :created_by
                )
                RETURNING id, content_type, slug, title_i18n, description_i18n, status
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "content_type": payload.content_type,
                "slug": payload.slug,
                "title_i18n": json_text(payload.title_i18n),
                "description_i18n": json_text(payload.description_i18n),
                "status": payload.status,
                "created_by": principal.subject,
            },
        )
    ).mappings().one()

    version = (
        await session.execute(
            text(
                """
                INSERT INTO academy_content_versions (
                    tenant_id,
                    content_id,
                    version_label,
                    locale,
                    mime_type,
                    source_sha256,
                    storage_key,
                    delivery_key,
                    size_bytes,
                    duration_ms,
                    accessibility_metadata,
                    status,
                    published_at,
                    effective_at,
                    created_by
                )
                VALUES (
                    :tenant_id,
                    :content_id,
                    :version_label,
                    :locale,
                    :mime_type,
                    :source_sha256,
                    :storage_key,
                    :delivery_key,
                    :size_bytes,
                    :duration_ms,
                    CAST(:accessibility_metadata AS jsonb),
                    :status,
                    CASE WHEN :status = 'published' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    CASE WHEN :status = 'published' THEN CURRENT_TIMESTAMP ELSE NULL END,
                    :created_by
                )
                RETURNING
                    id,
                    content_id,
                    version_label,
                    locale,
                    mime_type,
                    source_sha256,
                    size_bytes,
                    duration_ms,
                    accessibility_metadata,
                    status,
                    published_at,
                    effective_at
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "content_id": item["id"],
                "version_label": payload.version_label,
                "locale": payload.locale,
                "mime_type": payload.mime_type,
                "source_sha256": (
                    payload.source_sha256.lower() if payload.source_sha256 else None
                ),
                "storage_key": payload.storage_key,
                "delivery_key": payload.delivery_key,
                "size_bytes": payload.size_bytes,
                "duration_ms": payload.duration_ms,
                "accessibility_metadata": json_text(payload.accessibility_metadata),
                "status": payload.status,
                "created_by": principal.subject,
            },
        )
    ).mappings().one()

    return {
        "content": dict(item),
        "version": dict(version),
    }
