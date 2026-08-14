from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import roles_json


async def grounded_document_answer(
    session: AsyncSession,
    principal: Principal,
    *,
    question: str,
    locale: str,
    top_k: int,
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                text(
                    """
                WITH actor_roles AS (
                    SELECT jsonb_array_elements_text(CAST(:roles AS jsonb)) AS role_key
                ), allowed_versions AS (
                    SELECT lpi.content_version_id
                    FROM academy_enrollments AS e
                    JOIN academy_learning_path_items AS lpi
                      ON lpi.tenant_id = e.tenant_id AND lpi.path_id = e.path_id
                    WHERE e.tenant_id = :tenant_id AND e.subject = :subject
                      AND e.status IN ('assigned', 'in_progress', 'completed')
                    UNION
                    SELECT cv.id
                    FROM academy_content_versions AS cv
                    JOIN academy_entitlements AS ae
                      ON ae.tenant_id = cv.tenant_id
                     AND ae.resource_type = 'content'
                     AND ae.resource_id = cv.content_id
                     AND ae.permission IN ('view', 'learn', 'manage')
                    LEFT JOIN actor_roles AS ar
                      ON ae.principal_type = 'role' AND lower(ae.principal_key) = ar.role_key
                    WHERE cv.tenant_id = :tenant_id
                      AND (ae.starts_at IS NULL OR ae.starts_at <= CURRENT_TIMESTAMP)
                      AND (ae.ends_at IS NULL OR ae.ends_at > CURRENT_TIMESTAMP)
                      AND (
                          (ae.principal_type = 'subject' AND ae.principal_key = :subject)
                          OR ar.role_key IS NOT NULL
                      )
                ), question_terms AS (
                    SELECT tsvector_to_array(to_tsvector('simple', :question)) AS terms
                ), ranked AS (
                    SELECT dc.id AS chunk_id, dc.content_version_id, dc.chunk_ordinal,
                           dc.locale, dc.heading, dc.text_content, dc.source_page,
                           dc.source_anchor, cv.version_label, cv.version_number,
                           cv.source_sha256, ci.id AS content_id, ci.slug,
                           ci.title_i18n,
                           ts_rank_cd(
                               dc.search_vector,
                               to_tsquery('simple', array_to_string(q.terms, ' | '))
                           ) AS rank
                    FROM academy_document_chunks AS dc
                    JOIN academy_content_versions AS cv
                      ON cv.tenant_id = dc.tenant_id AND cv.id = dc.content_version_id
                    JOIN academy_content_items AS ci
                      ON ci.tenant_id = cv.tenant_id AND ci.id = cv.content_id
                    CROSS JOIN question_terms AS q
                    WHERE dc.tenant_id = :tenant_id
                      AND dc.locale = :locale
                      AND cv.status = 'published'
                      AND ci.status = 'published'
                      AND dc.content_version_id IN (SELECT content_version_id FROM allowed_versions)
                      AND cardinality(q.terms) > 0
                      AND dc.search_vector @@ to_tsquery(
                          'simple', array_to_string(q.terms, ' | ')
                      )
                      AND cardinality(
                          ARRAY(
                              SELECT unnest(q.terms)
                              INTERSECT
                              SELECT unnest(tsvector_to_array(dc.search_vector))
                          )
                      ) >= LEAST(2, cardinality(q.terms))
                )
                SELECT * FROM ranked
                ORDER BY rank DESC, content_id, chunk_ordinal
                LIMIT :top_k
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "subject": principal.subject,
                    "roles": roles_json(principal),
                    "question": question.strip(),
                    "locale": locale,
                    "top_k": top_k,
                },
            )
        )
        .mappings()
        .all()
    )

    if not rows:
        return {
            "supported": False,
            "answer": None,
            "mode": "extractive-grounded-v1",
            "sources": [],
            "reason": "No accessible published source supports this question.",
        }

    sources: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    for row in rows:
        excerpt = str(row["text_content"]).strip()
        answer_parts.append(excerpt)
        sources.append(
            {
                "content_id": row["content_id"],
                "content_version_id": row["content_version_id"],
                "slug": row["slug"],
                "title_i18n": row["title_i18n"],
                "version_label": row["version_label"],
                "version_number": row["version_number"],
                "source_sha256": row["source_sha256"],
                "chunk_id": row["chunk_id"],
                "chunk_ordinal": row["chunk_ordinal"],
                "source_page": row["source_page"],
                "source_anchor": row["source_anchor"],
                "rank": float(row["rank"]),
            }
        )

    return {
        "supported": True,
        "answer": "\n\n".join(answer_parts),
        "mode": "extractive-grounded-v1",
        "sources": sources,
        "reason": None,
    }
