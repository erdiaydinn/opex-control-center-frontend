from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def ingest_document_chunks(session: AsyncSession, principal: Principal, payload: Any) -> int:
    content_type = await session.scalar(
        text("""
        SELECT ci.content_type
        FROM academy_content_versions AS cv
        JOIN academy_content_items AS ci
          ON ci.tenant_id=cv.tenant_id AND ci.id=cv.content_id
        WHERE cv.tenant_id=:tenant_id AND cv.id=:content_version_id
    """),
        {
            "tenant_id": principal.tenant_id,
            "content_version_id": payload.content_version_id,
        },
    )
    if content_type not in {"document", "sop"}:
        raise ValueError("Document/SOP content version not found")

    await session.execute(
        text("""
        DELETE FROM academy_document_chunks
        WHERE tenant_id=:tenant_id AND content_version_id=:content_version_id
    """),
        {
            "tenant_id": principal.tenant_id,
            "content_version_id": payload.content_version_id,
        },
    )
    for chunk in payload.chunks:
        await session.execute(
            text("""
            INSERT INTO academy_document_chunks (
                tenant_id, content_version_id, chunk_ordinal, locale, heading,
                text_content, source_page, source_anchor, metadata
            ) VALUES (
                :tenant_id, :content_version_id, :chunk_ordinal, :locale, :heading,
                :text_content, :source_page, :source_anchor, CAST(:metadata AS jsonb)
            )
        """),
            {
                "tenant_id": principal.tenant_id,
                "content_version_id": payload.content_version_id,
                "chunk_ordinal": chunk.chunk_ordinal,
                "locale": chunk.locale,
                "heading": chunk.heading,
                "text_content": chunk.text_content,
                "source_page": chunk.source_page,
                "source_anchor": chunk.source_anchor,
                "metadata": json_text(chunk.metadata),
            },
        )
    return len(payload.chunks)
