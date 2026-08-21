from uuid import UUID

TENANT = UUID("00000000-0000-0000-0000-00000000a551")
PATH_ID = UUID("00000000-0000-0000-0000-00000000a552")
ENROLLMENT_ID = UUID("00000000-0000-0000-0000-00000000a553")


def _principal():
    from app.core.security import Principal

    return Principal(
        subject="academy-learner-1",
        tenant_id=TENANT,
        roles=("picker",),
        permissions=("module:academy:view",),
        permission_assignments=(),
        auth_mode="development",
    )


async def test_skill_gap_recommendation_binds_self_scoped_enrollment_navigation(
    monkeypatch,
) -> None:
    from app.modules.academy import skill_gap_service

    async def fake_learning_context(
        _session: object,
        principal,
        *,
        include_learning_context: bool = False,
    ) -> dict[str, list[dict[str, object]]]:
        assert principal.subject == "academy-learner-1"
        assert include_learning_context is True
        return {
            "requirements": [
                {
                    "skill_key": "safe-picking",
                    "title_i18n": {"en": "Safe picking"},
                    "description_i18n": {"en": "Verified safe-picking proficiency"},
                    "required_level": 3,
                    "role_keys": ["picker"],
                }
            ],
            "proficiencies": [
                {
                    "skill_key": "safe-picking",
                    "observed_level": 1,
                    "evidence_type": "assessment",
                    "evidence_ref": "assessment:academy-learner-1",
                    "observed_at": None,
                }
            ],
            "outcomes": [
                {
                    "path_key": "safe-picking-path",
                    "title_i18n": {"en": "Safe Picking Path"},
                    "skill_key": "safe-picking",
                    "target_level": 3,
                }
            ],
        }

    enrollment_calls = 0

    async def fake_enrollments(_session: object, principal) -> list[dict[str, object]]:
        nonlocal enrollment_calls
        enrollment_calls += 1
        assert principal.subject == "academy-learner-1"
        assert principal.tenant_id == TENANT
        return [
            {
                "id": ENROLLMENT_ID,
                "path_id": PATH_ID,
                "key": "safe-picking-path",
                "status": "in_progress",
                "due_at": None,
            }
        ]

    monkeypatch.setattr(
        skill_gap_service,
        "list_my_badge_credentials",
        fake_learning_context,
    )
    monkeypatch.setattr(skill_gap_service, "list_enrollments", fake_enrollments)
    principal = _principal()

    snapshot = await skill_gap_service.get_my_skill_gap_snapshot(object(), principal)

    assert snapshot["subject"] == principal.subject
    assert snapshot["gap_count"] == 1
    assert enrollment_calls == 1
    recommendation = snapshot["recommended_paths"][0]
    assert recommendation["path_key"] == "safe-picking-path"
    assert recommendation["path_id"] == PATH_ID
    assert recommendation["enrollment_id"] == ENROLLMENT_ID
    assert recommendation["enrollment_status"] == "in_progress"


async def test_skill_gap_without_recommendations_skips_enrollment_lookup(
    monkeypatch,
) -> None:
    from app.modules.academy import skill_gap_service

    async def fake_learning_context(
        _session: object,
        _principal_value,
        *,
        include_learning_context: bool = False,
    ) -> dict[str, list[dict[str, object]]]:
        assert include_learning_context is True
        return {
            "requirements": [],
            "proficiencies": [],
            "outcomes": [],
        }

    async def fail_if_called(_session: object, _principal_value):
        raise AssertionError("Enrollment lookup must be skipped without recommendations")

    monkeypatch.setattr(
        skill_gap_service,
        "list_my_badge_credentials",
        fake_learning_context,
    )
    monkeypatch.setattr(skill_gap_service, "list_enrollments", fail_if_called)

    snapshot = await skill_gap_service.get_my_skill_gap_snapshot(object(), _principal())

    assert snapshot["gap_count"] == 0
    assert snapshot["recommended_paths"] == []
