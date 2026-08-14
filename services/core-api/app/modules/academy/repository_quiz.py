from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.repository_utils import json_text


async def get_quiz_definition_for_attempt(
    session: AsyncSession,
    principal: Principal,
    quiz_id: UUID,
    enrollment_id: UUID,
) -> dict[str, Any] | None:
    enrollment = (
        (
            await session.execute(
                text(
                    """
                SELECT e.id, e.path_id
                FROM academy_enrollments AS e
                WHERE e.tenant_id = :tenant_id
                  AND e.id = :enrollment_id
                  AND e.subject = :subject
                  AND e.status IN ('assigned', 'in_progress')
                FOR UPDATE OF e
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if enrollment is None:
        return None

    quiz = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    q.id,
                    q.content_version_id,
                    q.kind,
                    q.checkpoint_at_ms,
                    q.pass_score,
                    q.max_attempts,
                    q.required,
                    COALESCE(
                        (
                            SELECT MAX(qa.attempt_number)
                            FROM academy_quiz_attempts AS qa
                            WHERE qa.tenant_id = q.tenant_id
                              AND qa.quiz_id = q.id
                              AND qa.subject = :subject
                        ),
                        0
                    ) AS previous_attempts
                FROM academy_quizzes AS q
                JOIN academy_learning_path_items AS lpi
                  ON lpi.tenant_id = q.tenant_id
                 AND lpi.content_version_id = q.content_version_id
                 AND lpi.path_id = :path_id
                WHERE q.tenant_id = :tenant_id
                  AND q.id = :quiz_id
                  AND q.status = 'published'
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "quiz_id": quiz_id,
                    "path_id": enrollment["path_id"],
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if quiz is None:
        return None

    question_rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    q.id AS question_id,
                    q.question_type,
                    q.points,
                    q.required,
                    o.id AS option_id,
                    o.is_correct
                FROM academy_questions AS q
                JOIN academy_question_options AS o
                  ON o.tenant_id = q.tenant_id
                 AND o.question_id = q.id
                WHERE q.tenant_id = :tenant_id
                  AND q.quiz_id = :quiz_id
                ORDER BY q.ordinal, o.ordinal
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "quiz_id": quiz_id,
                },
            )
        )
        .mappings()
        .all()
    )

    questions: dict[UUID, dict[str, Any]] = {}
    for row in question_rows:
        question = questions.setdefault(
            row["question_id"],
            {
                "question_id": row["question_id"],
                "question_type": row["question_type"],
                "points": float(row["points"]),
                "required": row["required"],
                "option_ids": set(),
                "correct_option_ids": set(),
            },
        )
        question["option_ids"].add(row["option_id"])
        if row["is_correct"]:
            question["correct_option_ids"].add(row["option_id"])

    return {
        **dict(quiz),
        "enrollment_id": enrollment_id,
        "path_id": enrollment["path_id"],
        "questions": list(questions.values()),
    }


async def save_quiz_attempt(
    session: AsyncSession,
    principal: Principal,
    *,
    attempt_id: UUID,
    quiz_id: UUID,
    enrollment_id: UUID,
    attempt_number: int,
    score: float,
    passed: bool,
    graded_answers: list[dict[str, Any]],
) -> dict[str, Any]:
    attempt = (
        (
            await session.execute(
                text(
                    """
                INSERT INTO academy_quiz_attempts (
                    id,
                    tenant_id,
                    enrollment_id,
                    quiz_id,
                    subject,
                    attempt_number,
                    score,
                    passed
                )
                VALUES (
                    :attempt_id,
                    :tenant_id,
                    :enrollment_id,
                    :quiz_id,
                    :subject,
                    :attempt_number,
                    :score,
                    :passed
                )
                RETURNING id, attempt_number, score, passed, submitted_at
                """
                ),
                {
                    "attempt_id": attempt_id,
                    "tenant_id": principal.tenant_id,
                    "enrollment_id": enrollment_id,
                    "quiz_id": quiz_id,
                    "subject": principal.subject,
                    "attempt_number": attempt_number,
                    "score": score,
                    "passed": passed,
                },
            )
        )
        .mappings()
        .one()
    )

    for answer in graded_answers:
        await session.execute(
            text(
                """
                INSERT INTO academy_quiz_answers (
                    tenant_id,
                    attempt_id,
                    question_id,
                    selected_option_ids,
                    is_correct,
                    awarded_points
                )
                VALUES (
                    :tenant_id,
                    :attempt_id,
                    :question_id,
                    CAST(:selected_option_ids AS jsonb),
                    :is_correct,
                    :awarded_points
                )
                """
            ),
            {
                "tenant_id": principal.tenant_id,
                "attempt_id": attempt["id"],
                "question_id": answer["question_id"],
                "selected_option_ids": json_text(
                    [str(value) for value in answer["selected_option_ids"]]
                ),
                "is_correct": answer["is_correct"],
                "awarded_points": answer["awarded_points"],
            },
        )

    return dict(attempt)


async def get_quiz_attempt_by_id(
    session: AsyncSession,
    principal: Principal,
    attempt_id: UUID,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    enrollment_id,
                    quiz_id,
                    attempt_number,
                    score,
                    passed,
                    submitted_at
                FROM academy_quiz_attempts
                WHERE tenant_id = :tenant_id
                  AND id = :attempt_id
                  AND subject = :subject
                """
                ),
                {
                    "tenant_id": principal.tenant_id,
                    "attempt_id": attempt_id,
                    "subject": principal.subject,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row else None
