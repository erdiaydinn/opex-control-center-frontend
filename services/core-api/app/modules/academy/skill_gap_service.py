from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.modules.academy.learning_os import (
    LearningPathOutcome,
    SkillProficiency,
    SkillRequirement,
    compute_skill_gaps,
    recommend_learning_paths,
)
from app.modules.academy.repository_credentials import list_my_badge_credentials


async def get_my_skill_gap_snapshot(
    session: AsyncSession,
    principal: Principal,
) -> dict[str, object]:
    raw_context = await list_my_badge_credentials(
        session,
        principal,
        include_learning_context=True,
    )
    if not isinstance(raw_context, dict):
        raise RuntimeError("Academy skill-gap context unavailable")
    context = raw_context

    requirements = tuple(
        SkillRequirement(
            skill_key=str(item["skill_key"]),
            required_level=int(item["required_level"]),
        )
        for item in context["requirements"]
    )
    proficiencies = tuple(
        SkillProficiency(
            skill_key=str(item["skill_key"]),
            observed_level=int(item["observed_level"]),
            evidence_ref=str(item["evidence_ref"]),
        )
        for item in context["proficiencies"]
    )
    outcomes = tuple(
        LearningPathOutcome(
            path_key=str(item["path_key"]),
            skill_key=str(item["skill_key"]),
            target_level=int(item["target_level"]),
        )
        for item in context["outcomes"]
    )

    gaps = compute_skill_gaps(requirements, proficiencies)
    recommended_keys = recommend_learning_paths(gaps, outcomes)

    requirement_by_key = {
        str(item["skill_key"]): item for item in context["requirements"]
    }
    proficiency_by_key = {
        str(item["skill_key"]): item for item in context["proficiencies"]
    }
    outcome_by_path: dict[str, list[dict[str, object]]] = {}
    path_title_by_key: dict[str, object] = {}
    for item in context["outcomes"]:
        path_key = str(item["path_key"])
        path_title_by_key[path_key] = item["title_i18n"]
        outcome_by_path.setdefault(path_key, []).append(
            {
                "skill_key": str(item["skill_key"]),
                "target_level": int(item["target_level"]),
            }
        )

    gap_items: list[dict[str, object]] = []
    for gap in gaps:
        requirement = requirement_by_key[gap.skill_key]
        proficiency = proficiency_by_key.get(gap.skill_key)
        gap_items.append(
            {
                "skill_key": gap.skill_key,
                "title_i18n": requirement["title_i18n"],
                "description_i18n": requirement["description_i18n"],
                "required_level": gap.required_level,
                "current_level": gap.current_level,
                "gap": gap.gap,
                "required_by_roles": list(requirement["role_keys"] or []),
                "latest_evidence": (
                    {
                        "evidence_type": proficiency["evidence_type"],
                        "evidence_ref": proficiency["evidence_ref"],
                        "observed_at": proficiency["observed_at"],
                    }
                    if proficiency is not None
                    else None
                ),
            }
        )

    recommendations = [
        {
            "path_key": path_key,
            "title_i18n": path_title_by_key.get(path_key, {}),
            "outcomes": outcome_by_path.get(path_key, []),
        }
        for path_key in recommended_keys
    ]

    return {
        "subject": principal.subject,
        "roles": sorted({str(role) for role in principal.roles}),
        "gap_count": len(gap_items),
        "gaps": gap_items,
        "recommended_paths": recommendations,
        "recommendation_policy": "deterministic_role_skill_gap_v1",
    }
