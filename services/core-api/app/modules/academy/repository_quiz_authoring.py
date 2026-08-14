from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def create_quiz(
    session: AsyncSession, principal: Principal, payload: Any
) -> dict[str, Any] | None:
    target = (
        (
            await session.execute(
                text("""
        SELECT cv.id, cv.duration_ms, ci.content_type
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
        )
        .mappings()
        .one_or_none()
    )
    if target is None:
        return None
    if payload.kind == "checkpoint":
        if target["content_type"] not in {"video", "live"}:
            raise ValueError("Checkpoint quizzes require video or live content")
        duration_ms = target["duration_ms"]
        if duration_ms is not None and payload.checkpoint_at_ms > int(duration_ms):
            raise ValueError("Checkpoint time exceeds content duration")

    version_number = 1
    if payload.supersedes_quiz_id:
        previous = (
            (
                await session.execute(
                    text("""
            SELECT id, content_version_id, version_number
            FROM academy_quizzes
            WHERE tenant_id=:tenant_id AND id=:quiz_id
            FOR UPDATE
        """),
                    {
                        "tenant_id": principal.tenant_id,
                        "quiz_id": payload.supersedes_quiz_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous is None or previous["content_version_id"] != payload.content_version_id:
            raise ValueError("Superseded quiz must exist for the same content version")
        version_number = int(previous["version_number"]) + 1

    quiz = (
        (
            await session.execute(
                text("""
        INSERT INTO academy_quizzes (
            tenant_id, content_version_id, kind, checkpoint_at_ms, pass_score,
            max_attempts, required, status, version_number, supersedes_quiz_id, created_by
        ) VALUES (
            :tenant_id, :content_version_id, :kind, :checkpoint_at_ms, :pass_score,
            :max_attempts, :required, :status, :version_number,
            :supersedes_quiz_id, :created_by
        )
        RETURNING id, content_version_id, kind, checkpoint_at_ms, pass_score,
                  max_attempts, required, status, version_number, supersedes_quiz_id
    """),
                {
                    "tenant_id": principal.tenant_id,
                    "content_version_id": payload.content_version_id,
                    "kind": payload.kind,
                    "checkpoint_at_ms": payload.checkpoint_at_ms,
                    "pass_score": payload.pass_score,
                    "max_attempts": payload.max_attempts,
                    "required": payload.required,
                    "status": payload.status,
                    "version_number": version_number,
                    "supersedes_quiz_id": payload.supersedes_quiz_id,
                    "created_by": principal.subject,
                },
            )
        )
        .mappings()
        .one()
    )

    if payload.supersedes_quiz_id:
        await session.execute(
            text("""
            UPDATE academy_quizzes SET status='retired'
            WHERE tenant_id=:tenant_id AND id=:quiz_id
        """),
            {
                "tenant_id": principal.tenant_id,
                "quiz_id": payload.supersedes_quiz_id,
            },
        )

    for q_ordinal, question in enumerate(payload.questions, 1):
        question_id = await session.scalar(
            text("""
            INSERT INTO academy_questions (
                tenant_id, quiz_id, ordinal, question_type, prompt_i18n, points, required
            ) VALUES (
                :tenant_id, :quiz_id, :ordinal, :question_type,
                CAST(:prompt_i18n AS jsonb), :points, :required
            ) RETURNING id
        """),
            {
                "tenant_id": principal.tenant_id,
                "quiz_id": quiz["id"],
                "ordinal": q_ordinal,
                "question_type": question.question_type,
                "prompt_i18n": json_text(question.prompt_i18n),
                "points": question.points,
                "required": question.required,
            },
        )
        for o_ordinal, choice in enumerate(question.options, 1):
            await session.execute(
                text("""
                INSERT INTO academy_question_options (
                    tenant_id, question_id, ordinal, label_i18n, is_correct
                ) VALUES (
                    :tenant_id, :question_id, :ordinal,
                    CAST(:label_i18n AS jsonb), :is_correct
                )
            """),
                {
                    "tenant_id": principal.tenant_id,
                    "question_id": question_id,
                    "ordinal": o_ordinal,
                    "label_i18n": json_text(choice.label_i18n),
                    "is_correct": choice.is_correct,
                },
            )
    return dict(quiz)
