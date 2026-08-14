from uuid import UUID

import httpx
import pytest
from fastapi import Request
from sqlalchemy import text

from app.core.permission_catalog import SYSTEM_ROLE_PERMISSIONS
from app.core.resources import engine
from app.core.security import Principal, get_current_principal
from app.main import app

C = UUID("00000000-0000-0000-0000-00000000c201")
D = UUID("00000000-0000-0000-0000-00000000c202")


async def seed(tenant: UUID, slug: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.tenant_id', :value, true)"),
            {"value": str(tenant)},
        )
        await connection.execute(
            text(
                "INSERT INTO tenants(id,slug,display_name) VALUES(:id,:slug,:name) "
                "ON CONFLICT(id) DO UPDATE SET display_name=EXCLUDED.display_name"
            ),
            {"id": tenant, "slug": slug, "name": slug},
        )
        await connection.execute(
            text(
                "INSERT INTO tenant_entitlements(tenant_id,module_key,enabled) "
                "VALUES(:id,'academy',TRUE) "
                "ON CONFLICT(tenant_id,module_key) DO UPDATE SET enabled=TRUE"
            ),
            {"id": tenant},
        )
        for role_key, role_name in (
            ("picker", "Picker"),
            (f"{slug}_role", f"{slug} role"),
        ):
            await connection.execute(
                text("""
                INSERT INTO roles(tenant_id,key,name,is_system)
                VALUES(:tenant_id,:key,:name,TRUE)
                ON CONFLICT(tenant_id,key)
                DO UPDATE SET name=EXCLUDED.name
                """),
                {"tenant_id": tenant, "key": role_key, "name": role_name},
            )


async def principal(request: Request) -> Principal:
    tenant = D if request.headers.get("X-Test-Tenant") == "d" else C
    return Principal(
        subject="employee-d" if tenant == D else "employee-c",
        tenant_id=tenant,
        roles=("super_admin", "picker"),
        permissions=tuple(sorted(SYSTEM_ROLE_PERMISSIONS["super_admin"])),
        permission_assignments=(),
        auth_mode="development",
    )


@pytest.fixture(autouse=True)
def override():
    app.dependency_overrides[get_current_principal] = principal
    yield
    app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_authoring_options_and_role_targeting_are_tenant_authoritative():
    await seed(C, "academy_c")
    await seed(D, "academy_d")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost",
    ) as client:
        content_response = await client.post(
            "/v1/academy/admin/content",
            json={
                "content_type": "sop",
                "slug": "cold-chain-sop",
                "title_i18n": {"en": "Cold chain SOP"},
                "version_label": "2026.1",
                "locale": "en",
                "source_sha256": "a" * 64,
                "status": "published",
            },
        )
        assert content_response.status_code == 201, content_response.text
        version_id = content_response.json()["version"]["id"]

        workspace = await client.get("/v1/academy/admin/workspace")
        assert workspace.status_code == 200, workspace.text
        authoring = workspace.json()["authoring"]
        role_keys = {item["key"] for item in authoring["roles"]}
        assert "picker" in role_keys
        assert "academy_c_role" in role_keys
        assert "academy_d_role" not in role_keys
        assert [item["content_version_id"] for item in authoring["published_versions"]] == [
            version_id
        ]
        assert authoring["quizzes"] == []

        tenant_d_workspace = await client.get(
            "/v1/academy/admin/workspace",
            headers={"X-Test-Tenant": "d"},
        )
        assert tenant_d_workspace.status_code == 200, tenant_d_workspace.text
        tenant_d_authoring = tenant_d_workspace.json()["authoring"]
        tenant_d_roles = {item["key"] for item in tenant_d_authoring["roles"]}
        assert "academy_d_role" in tenant_d_roles
        assert "academy_c_role" not in tenant_d_roles
        assert tenant_d_authoring["published_versions"] == []
        assert tenant_d_authoring["quizzes"] == []

        invalid_path = await client.post(
            "/v1/academy/admin/paths",
            json={
                "key": "invalid-cross-tenant-role",
                "title_i18n": {"en": "Invalid role path"},
                "items": [{"content_version_id": version_id, "required": True}],
                "role_assignments": [
                    {"role_key": "academy_d_role", "required": True, "due_days": 7}
                ],
                "status": "published",
            },
        )
        assert invalid_path.status_code == 400, invalid_path.text
        assert invalid_path.json()["detail"] == "Learning path contains unknown role assignment"

        duplicate_role_path = await client.post(
            "/v1/academy/admin/paths",
            json={
                "key": "duplicate-role-path",
                "title_i18n": {"en": "Duplicate role path"},
                "items": [{"content_version_id": version_id, "required": True}],
                "role_assignments": [
                    {"role_key": "picker", "required": True},
                    {"role_key": " PICKER ", "required": True},
                ],
                "status": "published",
            },
        )
        assert duplicate_role_path.status_code == 400, duplicate_role_path.text
        assert duplicate_role_path.json()["detail"] == (
            "Learning path contains duplicate role assignment"
        )

        after_rejections = await client.get("/v1/academy/admin/workspace")
        path_keys = {item["key"] for item in after_rejections.json()["paths"]}
        assert "invalid-cross-tenant-role" not in path_keys
        assert "duplicate-role-path" not in path_keys

        valid_path = await client.post(
            "/v1/academy/admin/paths",
            json={
                "key": "picker-cold-chain",
                "title_i18n": {"en": "Picker cold chain"},
                "certificate_enabled": True,
                "items": [{"content_version_id": version_id, "required": True}],
                "role_assignments": [
                    {"role_key": " PICKER ", "required": True, "due_days": 5}
                ],
                "status": "published",
            },
        )
        assert valid_path.status_code == 201, valid_path.text

        single_question = [
            {
                "question_type": "single_choice",
                "prompt_i18n": {"en": "Keep the cold chain?"},
                "points": 1,
                "required": True,
                "options": [
                    {"label_i18n": {"en": "No"}, "is_correct": False},
                    {"label_i18n": {"en": "Yes"}, "is_correct": True},
                ],
            }
        ]
        sop_checkpoint = await client.post(
            "/v1/academy/admin/quizzes",
            json={
                "content_version_id": version_id,
                "kind": "checkpoint",
                "checkpoint_at_ms": 1000,
                "pass_score": 100,
                "required": True,
                "status": "published",
                "questions": single_question,
            },
        )
        assert sop_checkpoint.status_code == 400, sop_checkpoint.text
        assert sop_checkpoint.json()["detail"] == (
            "Checkpoint quizzes require video or live content"
        )

        video_response = await client.post(
            "/v1/academy/admin/content",
            json={
                "content_type": "video",
                "slug": "cold-chain-video",
                "title_i18n": {"en": "Cold chain video"},
                "version_label": "2026.1",
                "locale": "en",
                "source_sha256": "b" * 64,
                "duration_ms": 10000,
                "status": "published",
            },
        )
        assert video_response.status_code == 201, video_response.text
        video_version_id = video_response.json()["version"]["id"]

        late_checkpoint = await client.post(
            "/v1/academy/admin/quizzes",
            json={
                "content_version_id": video_version_id,
                "kind": "checkpoint",
                "checkpoint_at_ms": 11000,
                "pass_score": 100,
                "required": True,
                "status": "published",
                "questions": single_question,
            },
        )
        assert late_checkpoint.status_code == 400, late_checkpoint.text
        assert late_checkpoint.json()["detail"] == "Checkpoint time exceeds content duration"

        checkpoint_response = await client.post(
            "/v1/academy/admin/quizzes",
            json={
                "content_version_id": video_version_id,
                "kind": "checkpoint",
                "checkpoint_at_ms": 5000,
                "pass_score": 100,
                "max_attempts": 3,
                "required": True,
                "status": "published",
                "questions": single_question,
            },
        )
        assert checkpoint_response.status_code == 201, checkpoint_response.text
        checkpoint_id = checkpoint_response.json()["id"]

        quiz_response = await client.post(
            "/v1/academy/admin/quizzes",
            json={
                "content_version_id": version_id,
                "kind": "completion",
                "pass_score": 100,
                "max_attempts": 3,
                "required": True,
                "status": "published",
                "questions": single_question,
            },
        )
        assert quiz_response.status_code == 201, quiz_response.text
        quiz_id = quiz_response.json()["id"]

        workspace_with_quiz = await client.get("/v1/academy/admin/workspace")
        quiz_rows = workspace_with_quiz.json()["authoring"]["quizzes"]
        assert {row["id"] for row in quiz_rows} == {checkpoint_id, quiz_id}
        by_id = {row["id"]: row for row in quiz_rows}
        assert by_id[quiz_id]["content_version_id"] == version_id
        assert by_id[quiz_id]["question_count"] == 1
        assert by_id[quiz_id]["status"] == "published"
        assert by_id[checkpoint_id]["content_version_id"] == video_version_id
        assert by_id[checkpoint_id]["checkpoint_at_ms"] == 5000

        tenant_d_after_quiz = await client.get(
            "/v1/academy/admin/workspace",
            headers={"X-Test-Tenant": "d"},
        )
        assert tenant_d_after_quiz.json()["authoring"]["quizzes"] == []

        home = await client.get("/v1/academy/me")
        assert home.status_code == 200, home.text
        assert any(item["key"] == "picker-cold-chain" for item in home.json()["enrollments"])

        tenant_d_home = await client.get("/v1/academy/me", headers={"X-Test-Tenant": "d"})
        assert tenant_d_home.status_code == 200, tenant_d_home.text
        assert all(
            item["key"] != "picker-cold-chain"
            for item in tenant_d_home.json()["enrollments"]
        )
