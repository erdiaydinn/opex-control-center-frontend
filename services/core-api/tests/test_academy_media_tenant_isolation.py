from uuid import UUID, uuid4

import pytest

from app.core.security import Principal
from app.modules.academy.media import (
    AcademyMediaConfig,
    issue_playback_token,
    verify_playback_token,
)


def _principal(tenant_id: UUID, subject: str) -> Principal:
    return Principal(
        subject=subject,
        tenant_id=tenant_id,
        roles=("employee",),
        auth_mode="test",
    )


def test_playback_token_is_bound_to_tenant_subject_object_and_delivery_key():
    tenant_a = uuid4()
    tenant_b = uuid4()
    media_id = uuid4()
    content_version_id = uuid4()
    config = AcademyMediaConfig("https://media.example.invalid", b"x" * 32, 120)
    token, _ = issue_playback_token(
        config,
        _principal(tenant_a, "employee-a"),
        media_id=media_id,
        content_version_id=content_version_id,
        delivery_key="tenant-a/course-1/video-1",
        now=1_000,
    )

    payload = verify_playback_token(
        config,
        token,
        tenant_id=tenant_a,
        subject="employee-a",
        media_id=media_id,
        content_version_id=content_version_id,
        delivery_key="tenant-a/course-1/video-1",
        now=1_001,
    )
    assert payload["tenant_id"] == str(tenant_a)

    adversarial_scopes = [
        {"tenant_id": tenant_b},
        {"subject": "employee-b"},
        {"media_id": uuid4()},
        {"content_version_id": uuid4()},
        {"delivery_key": "tenant-b/course-1/video-1"},
    ]
    baseline = {
        "tenant_id": tenant_a,
        "subject": "employee-a",
        "media_id": media_id,
        "content_version_id": content_version_id,
        "delivery_key": "tenant-a/course-1/video-1",
        "now": 1_001,
    }
    for override in adversarial_scopes:
        with pytest.raises(ValueError, match="scope mismatch"):
            verify_playback_token(config, token, **(baseline | override))


def test_playback_token_fails_closed_after_expiry():
    tenant_id = uuid4()
    media_id = uuid4()
    content_version_id = uuid4()
    config = AcademyMediaConfig("https://media.example.invalid", b"y" * 32, 30)
    token, _ = issue_playback_token(
        config,
        _principal(tenant_id, "employee-a"),
        media_id=media_id,
        content_version_id=content_version_id,
        delivery_key="tenant-a/course-1/video-1",
        now=2_000,
    )
    with pytest.raises(ValueError, match="expired"):
        verify_playback_token(
            config,
            token,
            tenant_id=tenant_id,
            subject="employee-a",
            media_id=media_id,
            content_version_id=content_version_id,
            delivery_key="tenant-a/course-1/video-1",
            now=2_030,
        )
