from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def _insert_version(
    session: AsyncSession, principal: Principal, content_id: UUID, payload: Any, version_number: int
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_content_versions (
            tenant_id, content_id, version_label, version_number, locale, mime_type,
            source_sha256, storage_key, delivery_key, size_bytes, duration_ms,
            accessibility_metadata, status, published_at, effective_at, created_by
        ) VALUES (
            :tenant_id, :content_id, :version_label, :version_number, :locale, :mime_type,
            :source_sha256, :storage_key, :delivery_key, :size_bytes, :duration_ms,
            CAST(:accessibility_metadata AS jsonb), CAST(:status AS varchar(20)),
            CASE WHEN CAST(:status AS varchar(20))='published' THEN CURRENT_TIMESTAMP END,
            CASE WHEN CAST(:status AS varchar(20))='published' THEN CURRENT_TIMESTAMP END, :created_by
        ) RETURNING id, content_id, version_label, version_number, locale, mime_type,
                    source_sha256, size_bytes, duration_ms, accessibility_metadata,
                    status, published_at, effective_at
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "content_id": content_id,
                    "version_label": payload.version_label,
                    "version_number": version_number,
                    "locale": payload.locale,
                    "mime_type": payload.mime_type,
                    "source_sha256": payload.source_sha256.lower()
                    if payload.source_sha256
                    else None,
                    "storage_key": payload.storage_key,
                    "delivery_key": payload.delivery_key,
                    "size_bytes": payload.size_bytes,
                    "duration_ms": payload.duration_ms,
                    "accessibility_metadata": json_text(payload.accessibility_metadata),
                    "status": payload.status,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


async def create_content(
    session: AsyncSession, principal: Principal, payload: Any
) -> dict[str, Any]:
    item = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_content_items (
            tenant_id, content_type, slug, title_i18n, description_i18n, status, created_by
        ) VALUES (
            :tenant_id, :content_type, :slug, CAST(:title_i18n AS jsonb),
            CAST(:description_i18n AS jsonb), :status, :created_by
        ) RETURNING id, content_type, slug, title_i18n, description_i18n, status
    """),
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
        )
        .mappings()
        .one()
    )
    version = await _insert_version(session, principal, item["id"], payload, 1)
    return {"content": dict(item), "version": version}


async def create_content_version(
    session: AsyncSession, principal: Principal, content_id: UUID, payload: Any
) -> dict[str, Any] | None:
    version_number = await session.scalar(
        text("""
        SELECT COALESCE(MAX(cv.version_number), 0) + 1
        FROM academy_content_items AS ci
        LEFT JOIN academy_content_versions AS cv
          ON cv.tenant_id=ci.tenant_id AND cv.content_id=ci.id
        WHERE ci.tenant_id=:tenant_id AND ci.id=:content_id
        HAVING COUNT(ci.id) > 0
    """),
        {"tenant_id": principal.tenant_id, "content_id": content_id},
    )
    if version_number is None:
        return None
    return await _insert_version(session, principal, content_id, payload, int(version_number))


async def create_media_asset(
    session: AsyncSession, principal: Principal, payload: Any
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_media_assets (
            tenant_id, content_version_id, asset_kind, storage_provider, storage_bucket,
            storage_key, delivery_key, manifest_path, checksum_sha256, size_bytes,
            duration_ms, transcode_status, delivery_mode, encryption_mode,
            segment_duration_seconds, created_by
        ) SELECT :tenant_id, cv.id, :asset_kind, :storage_provider, :storage_bucket,
                 :storage_key, :delivery_key, :manifest_path, :checksum_sha256, :size_bytes,
                 :duration_ms, :transcode_status, :delivery_mode, :encryption_mode,
                 :segment_duration_seconds, :created_by
          FROM academy_content_versions AS cv
          WHERE cv.tenant_id=:tenant_id AND cv.id=:content_version_id
        RETURNING id, content_version_id, asset_kind, storage_provider, delivery_key,
                  manifest_path, checksum_sha256, size_bytes, duration_ms, transcode_status,
                  delivery_mode, encryption_mode, segment_duration_seconds
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "content_version_id": payload.content_version_id,
                    "asset_kind": payload.asset_kind,
                    "storage_provider": payload.storage_provider,
                    "storage_bucket": payload.storage_bucket,
                    "storage_key": payload.storage_key,
                    "delivery_key": payload.delivery_key,
                    "manifest_path": payload.manifest_path,
                    "checksum_sha256": payload.checksum_sha256.lower(),
                    "size_bytes": payload.size_bytes,
                    "duration_ms": payload.duration_ms,
                    "transcode_status": payload.transcode_status,
                    "delivery_mode": payload.delivery_mode,
                    "encryption_mode": payload.encryption_mode,
                    "segment_duration_seconds": payload.segment_duration_seconds,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None
