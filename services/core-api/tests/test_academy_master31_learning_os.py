# Canonical exact-head proof activation marker: v1

from pathlib import Path
from uuid import UUID

import pytest

from app.core.security import Principal
from app.modules.academy import skill_gap_service
from app.modules.academy.learning_os import (
    LearningPathOutcome,
    SkillProficiency,
    SkillRequirement,
    compute_skill_gaps,
    recommend_learning_paths,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/0041_academy_learning_os.py"
)


def test_role_skill_gap_is_evidence_bound_and_deterministic() -> None:
    requirements = [
        SkillRequirement("inventory.count", 4),
        SkillRequirement("safety.haccp", 3),
    ]
    proficiencies = [SkillProficiency("inventory.count", 2, "assessment:7")]

    gaps = compute_skill_gaps(requirements, proficiencies)

    assert [
        (gap.skill_key, gap.current_level, gap.required_level) for gap in gaps
    ] == [
        ("inventory.count", 2, 4),
        ("safety.haccp", 0, 3),
    ]


def test_path_recommendation_covers_gap_without_role_database_dependency() -> None:
    gaps = compute_skill_gaps(
        [SkillRequirement("a", 3), SkillRequirement("b", 2)],
        [],
    )
    outcomes = [
        LearningPathOutcome("path-b", "b", 2),
        LearningPathOutcome("path-both", "a", 3),
        LearningPathOutcome("path-both", "b", 2),
    ]

    assert recommend_learning_paths(gaps, outcomes) == ("path-both",)


@pytest.mark.asyncio
async def test_skill_gap_snapshot_is_principal_scoped_and_evidence_bound(monkeypatch) -> None:
    principal = Principal(
        subject="academy-learner-31",
        tenant_id=UUID("00000000-0000-0000-0000-000000003131"),
        roles=("picker", "inventory_specialist"),
        permissions=("module:academy:view",),
        permission_assignments=(),
        auth_mode="development",
    )

    async def fake_learning_context(session, supplied_principal, *, include_learning_context=False):
        assert session is session_sentinel
        assert supplied_principal is principal
        assert include_learning_context is True
        return {
            "requirements": [
                {
                    "skill_key": "inventory.count",
                    "title_i18n": {"en": "Inventory count"},
                    "description_i18n": {"en": "Count accurately"},
                    "required_level": 4,
                    "role_keys": ["inventory_specialist"],
                },
                {
                    "skill_key": "safety.haccp",
                    "title_i18n": {"en": "HACCP safety"},
                    "description_i18n": {"en": "Food safety evidence"},
                    "required_level": 3,
                    "role_keys": ["picker"],
                },
            ],
            "proficiencies": [
                {
                    "skill_key": "inventory.count",
                    "observed_level": 2,
                    "evidence_type": "assessment",
                    "evidence_ref": "assessment:verified-31",
                    "observed_at": "2026-08-21T00:00:00+00:00",
                }
            ],
            "outcomes": [
                {
                    "path_key": "picker-safe-counting",
                    "title_i18n": {"en": "Safe counting"},
                    "skill_key": "inventory.count",
                    "target_level": 4,
                },
                {
                    "path_key": "picker-safe-counting",
                    "title_i18n": {"en": "Safe counting"},
                    "skill_key": "safety.haccp",
                    "target_level": 3,
                },
            ],
        }

    session_sentinel = object()
    monkeypatch.setattr(
        skill_gap_service,
        "list_my_badge_credentials",
        fake_learning_context,
    )

    snapshot = await skill_gap_service.get_my_skill_gap_snapshot(
        session_sentinel,  # type: ignore[arg-type]
        principal,
    )

    assert snapshot["subject"] == "academy-learner-31"
    assert snapshot["roles"] == ["inventory_specialist", "picker"]
    assert snapshot["gap_count"] == 2
    assert [item["skill_key"] for item in snapshot["gaps"]] == [
        "inventory.count",
        "safety.haccp",
    ]
    assert snapshot["gaps"][0]["current_level"] == 2
    assert snapshot["gaps"][0]["latest_evidence"]["evidence_ref"] == "assessment:verified-31"
    assert snapshot["gaps"][1]["current_level"] == 0
    assert snapshot["recommended_paths"] == [
        {
            "path_key": "picker-safe-counting",
            "title_i18n": {"en": "Safe counting"},
            "outcomes": [
                {"skill_key": "inventory.count", "target_level": 4},
                {"skill_key": "safety.haccp", "target_level": 3},
            ],
        }
    ]
    assert snapshot["recommendation_policy"] == "deterministic_role_skill_gap_v1"


def test_learning_os_migration_is_tenant_isolated_append_only_and_view_keeps_rls() -> None:
    text = MIGRATION_PATH.read_text()
    for token in (
        "academy_skills",
        "academy_role_skill_requirement",
        "academy_path_skill_outcome",
        "academy_skill_evidence",
        "FORCE ROW LEVEL SECURITY",
        "REVOKE UPDATE, DELETE ON academy_skill_evidence",
        "security_invoker = true",
        'down_revision: str | None = "0040_budget_planning_hardening"',
    ):
        assert token in text
