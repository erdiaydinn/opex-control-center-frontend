# Canonical exact-head proof activation marker: v1

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.modules.academy.learning_os import SkillGap
from app.modules.academy.media_plane import (
    MediaLoadEvidence,
    build_transcode_spec,
    production_media_capacity_accepted,
)
from app.modules.academy.tutor import academy_tutor_answer

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> SimpleNamespace:
    return SimpleNamespace(tenant_id=TENANT, subject="learner")


async def supported(*args: object, **kwargs: object) -> dict[str, object]:
    return {
        "supported": True,
        "answer": "Approved SOP answer",
        "sources": [{"source_sha256": "a" * 64, "content_version_id": "v1"}],
    }


async def unsupported(*args: object, **kwargs: object) -> dict[str, object]:
    return {"supported": False, "answer": None, "sources": []}


async def incomplete_provenance(*args: object, **kwargs: object) -> dict[str, object]:
    return {
        "supported": True,
        "answer": "Untrusted answer",
        "sources": [{"source_sha256": "", "content_version_id": "v1"}],
    }


def test_tutor_is_source_bound_and_can_enrich_with_skill_gap() -> None:
    result = asyncio.run(
        academy_tutor_answer(
            grounded_answer_fn=supported,
            session=object(),
            principal=principal(),
            question="How?",
            locale="en",
            skill_gaps=(SkillGap("safety", 3, 1, 2),),
        )
    )
    assert result["supported"]
    assert result["skill_context"][0]["skill_key"] == "safety"

    denied = asyncio.run(
        academy_tutor_answer(
            grounded_answer_fn=unsupported,
            session=object(),
            principal=principal(),
            question="How?",
            locale="en",
        )
    )
    assert not denied["supported"]
    assert denied["answer"] is None


def test_tutor_fails_closed_when_academy_provenance_is_incomplete() -> None:
    denied = asyncio.run(
        academy_tutor_answer(
            grounded_answer_fn=incomplete_provenance,
            session=object(),
            principal=principal(),
            question="How?",
            locale="en",
        )
    )

    assert not denied["supported"]
    assert denied["answer"] is None
    assert denied["sources"] == []


def test_media_plane_requires_private_source_and_real_1200_session_evidence() -> None:
    spec = build_transcode_spec(
        private_source_key="academy/private/media/source-1.mp4",
        delivery_key="tenant/course/media",
        delivery_mode="hls",
    )
    assert spec.renditions == (360, 720, 1080)

    assert not production_media_capacity_accepted(
        MediaLoadEvidence(1200, "ci", "SYNTHETIC", True, "run:1")
    )
    assert production_media_capacity_accepted(
        MediaLoadEvidence(
            1200,
            "media-prod-shape",
            "REAL_MEDIA_ENVIRONMENT",
            True,
            "load:approved",
        )
    )


def test_media_plane_rejects_public_sources_and_path_traversal() -> None:
    with pytest.raises(ValueError):
        build_transcode_spec(
            private_source_key="https://example.com/video.mp4",
            delivery_key="tenant/video",
            delivery_mode="hls",
        )
    with pytest.raises(ValueError):
        build_transcode_spec(
            private_source_key="academy/private/video.mp4",
            delivery_key="../escape",
            delivery_mode="hls",
        )
