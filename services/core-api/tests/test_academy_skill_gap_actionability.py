from uuid import UUID

import pytest

from app.core.security import Principal
from app.modules.academy.skill_gap_service import get_my_skill_gap_snapshot


TENANT = UUID("00000000-0000-0000-0000-00000000a551")
PATH_ID = UUID("00000000-0000-0000-0000-00000000a552")
ENROLLMENT_ID = UUID("00000000-0000-0000-0000-00000000a553")


class _Rows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_Rows":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _Session:
    def __init__(self) -> None:
        self.params: dict[str, object] | None = None
        self.execute_calls = 0

    async def execute(self, _statement: object, params: dict[str, object]) -> _Rows:
        self.execute_calls += 1
        self.params = params
        return _Rows(
            [
                {
                    "path_key": "safe-picking-path",
                    "path_id": PATH_ID,
                    "enrollment_id": ENROLLMENT_ID,
                    "enrollment_status": "in_progress",
                    "enrollment_due_at": None,
                }
            ]
        )


def _principal() -> Principal:
    return Principal(
        subject="academy-learner-1",
        tenant_id=TENANT,
        roles=("picker",),
        permissions=("module:academy:view",),
        permission_assignments=(),
        auth_mode="development",
    )


@pytest.mark.asyncio
async def test_skill_gap_recommendation_binds_self_scoped_enrollment_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_learning_context(
        _session: object,
        principal: Principal,
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

    monkeypatch.setattr(
        "app.modules.academy.skill_gap_service.list_my_badge_credentials",
        fake_learning_context,
    )
    session = _Session()
    principal = _principal()

    snapshot = await get_my_skill_gap_snapshot(session, principal)  # type: ignore[arg-type]

    assert snapshot["subject"] == principal.subject
    assert snapshot["gap_count"] == 1
    assert session.execute_calls == 1
    assert session.params is not None
    assert session.params["tenant_id"] == TENANT
    assert session.params["subject"] == principal.subject
    assert "safe-picking-path" in str(session.params["path_keys_json"])
    recommendation = snapshot["recommended_paths"][0]  # type: ignore[index]
    assert recommendation["path_key"] == "safe-picking-path"
    assert recommendation["path_id"] == PATH_ID
    assert recommendation["enrollment_id"] == ENROLLMENT_ID
    assert recommendation["enrollment_status"] == "in_progress"


@pytest.mark.asyncio
async def test_skill_gap_without_recommendations_does_not_query_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_learning_context(
        _session: object,
        _principal: Principal,
        *,
        include_learning_context: bool = False,
    ) -> dict[str, list[dict[str, object]]]:
        assert include_learning_context is True
        return {
            "requirements": [],
            "proficiencies": [],
            "outcomes": [],
        }

    monkeypatch.setattr(
        "app.modules.academy.skill_gap_service.list_my_badge_credentials",
        fake_learning_context,
    )
    session = _Session()

    snapshot = await get_my_skill_gap_snapshot(session, _principal())  # type: ignore[arg-type]

    assert snapshot["gap_count"] == 0
    assert snapshot["recommended_paths"] == []
    assert session.execute_calls == 0
