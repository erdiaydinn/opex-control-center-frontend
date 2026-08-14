from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import Request
from sqlalchemy import text

from app.core.permission_catalog import SYSTEM_ROLE_PERMISSIONS
from app.core.resources import engine
from app.core.security import Principal, get_current_principal
from app.main import app

A = UUID("00000000-0000-0000-0000-00000000a101")
B = UUID("00000000-0000-0000-0000-00000000a102")


async def seed(tenant: UUID, slug: str) -> None:
    async with engine.begin() as c:
        await c.execute(text("SELECT set_config('app.tenant_id', :v, true)"), {"v": str(tenant)})
        await c.execute(
            text(
                "INSERT INTO tenants(id,slug,display_name) VALUES(:id,:slug,:name) ON CONFLICT(id) DO UPDATE SET display_name=EXCLUDED.display_name"
            ),
            {"id": tenant, "slug": slug, "name": slug},
        )
        await c.execute(
            text(
                "INSERT INTO tenant_entitlements(tenant_id,module_key,enabled) VALUES(:id,'academy',TRUE) ON CONFLICT(tenant_id,module_key) DO UPDATE SET enabled=TRUE"
            ),
            {"id": tenant},
        )


async def principal(request: Request) -> Principal:
    tenant = B if request.headers.get("X-Test-Tenant") == "b" else A
    return Principal(
        subject="employee-b" if tenant == B else "employee-a",
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
async def test_academy_lifecycle_rls_media_concurrency_and_grounded_qa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    await seed(A, "academy-a")
    await seed(B, "academy-b")
    key = tmp_path / "media.key"
    key.write_bytes(b"x" * 48)
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_CDN_BASE_URL", "https://academy-cdn.example.test")
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_SIGNING_SECRET_FILE", str(key))
    monkeypatch.setenv("OPEX_ACADEMY_MEDIA_TOKEN_TTL_SECONDS", "90")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as c:
        video = (
            await c.post(
                "/v1/academy/admin/content",
                json={
                    "content_type": "video",
                    "slug": "safety-video",
                    "title_i18n": {"tr": "Güvenlik", "en": "Safety", "ar": "سلامة"},
                    "version_label": "2026.1",
                    "locale": "tr",
                    "source_sha256": "1" * 64,
                    "duration_ms": 10000,
                    "accessibility_metadata": {"captions": ["tr", "en", "ar"], "transcript": True},
                    "status": "published",
                },
            )
        ).json()
        version = video["version"]["id"]
        media = await c.post(
            "/v1/academy/admin/media",
            json={
                "content_version_id": version,
                "asset_kind": "video_hls",
                "storage_provider": "s3",
                "storage_bucket": "private-origin",
                "storage_key": "tenant-a/source.mp4",
                "delivery_key": "tenant-a/video-v1",
                "manifest_path": "hls/master.m3u8",
                "checksum_sha256": "2" * 64,
                "size_bytes": 1000,
                "duration_ms": 10000,
                "delivery_mode": "hls",
                "segment_duration_seconds": 6,
            },
        )
        assert media.status_code == 201, media.text
        path = await c.post(
            "/v1/academy/admin/paths",
            json={
                "key": "picker-safety",
                "title_i18n": {"tr": "Picker Güvenlik"},
                "certificate_enabled": True,
                "items": [{"content_version_id": version, "required": True}],
                "role_assignments": [{"role_key": "picker", "required": True}],
                "status": "published",
            },
        )
        assert path.status_code == 201, path.text
        quiz = await c.post(
            "/v1/academy/admin/quizzes",
            json={
                "content_version_id": version,
                "kind": "checkpoint",
                "checkpoint_at_ms": 5000,
                "pass_score": 100,
                "required": True,
                "status": "published",
                "questions": [
                    {
                        "question_type": "single_choice",
                        "prompt_i18n": {"tr": "Dur?", "en": "Stop?"},
                        "options": [
                            {"label_i18n": {"en": "No"}, "is_correct": False},
                            {"label_i18n": {"en": "Yes"}, "is_correct": True},
                        ],
                    }
                ],
            },
        )
        assert quiz.status_code == 201, quiz.text
        quiz_id = quiz.json()["id"]
        home = await c.get("/v1/academy/me")
        assert home.status_code == 200
        assert home.json()["direction_by_locale"]["ar"] == "rtl"
        assert set(home.json()["locales"]) == {
            "tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"
        }
        enrollment = home.json()["enrollments"][0]["id"]
        workspace = await c.get(f"/v1/academy/enrollments/{enrollment}")
        assert workspace.status_code == 200, workspace.text
        assert workspace.json()["items"][0]["content_version_id"] == version
        play = await c.post(f"/v1/academy/media/{media.json()['id']}/playback-authorization")
        assert play.status_code == 200 and play.json()["expires_in_seconds"] == 90
        assert (
            "private-origin" not in play.json()["playback_url"]
            and "source.mp4" not in play.json()["playback_url"]
        )

        p1 = {
            "content_version_id": version,
            "last_position_ms": 4000,
            "watched_delta_ms": 4000,
            "expected_revision": 0,
        }
        r1 = await c.patch(
            f"/v1/academy/enrollments/{enrollment}/progress",
            headers={"Idempotency-Key": "p1"},
            json=p1,
        )
        assert r1.status_code == 200 and r1.json()["revision"] == 1
        replay = await c.patch(
            f"/v1/academy/enrollments/{enrollment}/progress",
            headers={"Idempotency-Key": "p1"},
            json=p1,
        )
        assert replay.json()["idempotent_replay"] is True
        stale_payload = {**p1, "last_position_ms": 4100}
        assert (
            await c.patch(
                f"/v1/academy/enrollments/{enrollment}/progress",
                headers={"Idempotency-Key": "p1"},
                json=stale_payload,
            )
        ).status_code == 409
        blocked = await c.patch(
            f"/v1/academy/enrollments/{enrollment}/progress",
            headers={"Idempotency-Key": "p2"},
            json={
                "content_version_id": version,
                "last_position_ms": 6000,
                "watched_delta_ms": 1000,
                "expected_revision": 1,
            },
        )
        assert blocked.status_code == 409 and blocked.json()["detail"]["quiz_id"] == quiz_id

        public = await c.get(f"/v1/academy/enrollments/{enrollment}/quizzes/{quiz_id}")
        assert public.status_code == 200 and "is_correct" not in public.text
        q = public.json()["questions"][0]
        correct = next(o for o in q["options"] if o["label_i18n"]["en"] == "Yes")
        attempt_payload = {
            "enrollment_id": enrollment,
            "answers": [{"question_id": q["id"], "selected_option_ids": [correct["id"]]}],
        }
        attempt = await c.post(
            f"/v1/academy/quizzes/{quiz_id}/attempts",
            headers={"Idempotency-Key": "q1"},
            json=attempt_payload,
        )
        assert attempt.status_code == 201 and attempt.json()["passed"] is True
        assert (
            await c.post(
                f"/v1/academy/quizzes/{quiz_id}/attempts",
                headers={"Idempotency-Key": "q1"},
                json=attempt_payload,
            )
        ).json()["idempotent_replay"] is True

        seek_only = await c.patch(
            f"/v1/academy/enrollments/{enrollment}/progress",
            headers={"Idempotency-Key": "p3"},
            json={
                "content_version_id": version,
                "last_position_ms": 10000,
                "watched_delta_ms": 1000,
                "complete_requested": True,
                "expected_revision": 1,
            },
        )
        assert seek_only.status_code == 200, seek_only.text
        assert seek_only.json()["progress_percent"] == 100
        assert seek_only.json()["watched_percent"] == 50
        assert seek_only.json()["required_watch_percent"] == 90
        assert seek_only.json()["status"] == "in_progress"

        watched_completion = await c.patch(
            f"/v1/academy/enrollments/{enrollment}/progress",
            headers={"Idempotency-Key": "p4"},
            json={
                "content_version_id": version,
                "last_position_ms": 10000,
                "watched_delta_ms": 5000,
                "complete_requested": True,
                "expected_revision": 2,
            },
        )
        assert watched_completion.status_code == 200, watched_completion.text
        assert watched_completion.json()["watched_percent"] == 100
        assert watched_completion.json()["status"] == "completed"
        done = await c.post(f"/v1/academy/enrollments/{enrollment}/complete")
        assert done.status_code == 200, done.text
        assert done.json()["certificate_code"]
        final_home = await c.get("/v1/academy/me")
        assert final_home.status_code == 200
        assert final_home.json()["certificates"]

        # Tenant B must not read or operate on A's content/enrollment/media.
        headers_b = {"X-Test-Tenant": "b"}
        assert (await c.get(f"/v1/academy/enrollments/{enrollment}", headers=headers_b)).status_code == 404
        assert (await c.post(f"/v1/academy/media/{media.json()['id']}/playback-authorization", headers=headers_b)).status_code == 404
        answer = await c.post(
            "/v1/academy/knowledge/answer",
            headers=headers_b,
            json={"question": "Safety?", "locale": "en", "top_k": 5},
        )
        assert answer.status_code == 200
        assert answer.json()["supported"] is False
