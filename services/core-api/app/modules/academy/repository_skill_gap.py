from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


async def get_skill_gap_context(
    session: AsyncSession,
    principal: Principal,
) -> dict[str, list[dict[str, object]]]:
    role_keys = sorted({str(role) for role in principal.roles if str(role).strip()})
    if not role_keys:
        return {"requirements": [], "proficiencies": [], "outcomes": []}

    roles_json = json.dumps(role_keys)
    requirements = (
        await session.execute(
            text(
                """
                SELECT
                    skill.skill_key,
                    skill.title_i18n,
                    skill.description_i18n,
                    MAX(requirement.required_level)::integer AS required_level,
                    ARRAY_AGG(DISTINCT requirement.role_key ORDER BY requirement.role_key) AS role_keys
                FROM academy_role_skill_requirement AS requirement
                JOIN academy_skills AS skill
                  ON skill.tenant_id = requirement.tenant_id
                 AND skill.id = requirement.skill_id
                WHERE requirement.tenant_id = :tenant_id
                  AND skill.status = 'active'
                  AND requirement.role_key IN (
                      SELECT jsonb_array_elements_text(CAST(:roles_json AS jsonb))
                  )
                  AND requirement.effective_from <= CURRENT_DATE
                  AND (
                      requirement.effective_to IS NULL
                      OR requirement.effective_to >= CURRENT_DATE
                  )
                GROUP BY skill.skill_key, skill.title_i18n, skill.description_i18n
                ORDER BY skill.skill_key
                """
            ),
            {"tenant_id": principal.tenant_id, "roles_json": roles_json},
        )
    ).mappings().all()

    proficiencies = (
        await session.execute(
            text(
                """
                SELECT
                    skill.skill_key,
                    proficiency.observed_level::integer AS observed_level,
                    proficiency.evidence_type,
                    proficiency.evidence_ref,
                    proficiency.observed_at
                FROM academy_subject_skill_proficiency AS proficiency
                JOIN academy_skills AS skill
                  ON skill.tenant_id = proficiency.tenant_id
                 AND skill.id = proficiency.skill_id
                WHERE proficiency.tenant_id = :tenant_id
                  AND proficiency.subject = :subject
                  AND skill.status = 'active'
                ORDER BY skill.skill_key
                """
            ),
            {"tenant_id": principal.tenant_id, "subject": principal.subject},
        )
    ).mappings().all()

    outcomes = (
        await session.execute(
            text(
                """
                SELECT DISTINCT
                    path.key AS path_key,
                    path.title_i18n,
                    skill.skill_key,
                    outcome.target_level::integer AS target_level
                FROM academy_path_skill_outcome AS outcome
                JOIN academy_learning_paths AS path
                  ON path.tenant_id = outcome.tenant_id
                 AND path.id = outcome.path_id
                JOIN academy_skills AS skill
                  ON skill.tenant_id = outcome.tenant_id
                 AND skill.id = outcome.skill_id
                JOIN academy_path_role_assignments AS assignment
                  ON assignment.tenant_id = path.tenant_id
                 AND assignment.path_id = path.id
                WHERE outcome.tenant_id = :tenant_id
                  AND path.status = 'published'
                  AND skill.status = 'active'
                  AND assignment.role_key IN (
                      SELECT jsonb_array_elements_text(CAST(:roles_json AS jsonb))
                  )
                ORDER BY path.key, skill.skill_key
                """
            ),
            {"tenant_id": principal.tenant_id, "roles_json": roles_json},
        )
    ).mappings().all()

    return {
        "requirements": [dict(row) for row in requirements],
        "proficiencies": [dict(row) for row in proficiencies],
        "outcomes": [dict(row) for row in outcomes],
    }
