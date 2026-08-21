from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.security import Principal
from app.modules.academy.learning_os import SkillGap

GroundedAnswerFn = Callable[..., Awaitable[dict[str, Any]]]


async def academy_tutor_answer(
    *,
    grounded_answer_fn: GroundedAnswerFn,
    session: object,
    principal: Principal,
    question: str,
    locale: str,
    skill_gaps: tuple[SkillGap, ...] = (),
) -> dict[str, Any]:
    grounded = await grounded_answer_fn(
        session,
        principal,
        question=question,
        locale=locale,
        top_k=5,
    )
    if not grounded.get("supported"):
        return {
            "supported": False,
            "answer": None,
            "sources": [],
            "skill_context": [],
            "reason": "No accessible approved Academy source supports this question.",
        }

    sources = grounded.get("sources") or []
    if not sources or any(
        not source.get("source_sha256") or not source.get("content_version_id")
        for source in sources
    ):
        return {
            "supported": False,
            "answer": None,
            "sources": [],
            "skill_context": [],
            "reason": "Academy provenance is incomplete.",
        }

    context = [
        {
            "skill_key": gap.skill_key,
            "current_level": gap.current_level,
            "required_level": gap.required_level,
            "gap": gap.gap,
        }
        for gap in skill_gaps
    ]
    return {
        "supported": True,
        "answer": grounded["answer"],
        "sources": sources,
        "skill_context": context,
        "mode": "academy-approved-grounded-tutor-v1",
        "reason": None,
    }
