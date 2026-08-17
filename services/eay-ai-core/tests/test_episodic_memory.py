from datetime import datetime, timedelta, timezone

import pytest

from app.episodic_memory import (
    Confidentiality,
    EpisodeKind,
    MemoryEpisode,
    MemoryQuery,
    RetentionClass,
    recall_episodes,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 5, 0, tzinfo=UTC)


def _episode(episode_id, **overrides):
    payload = dict(
        episode_id=episode_id,
        tenant_id="warehouse:fulya",
        kind=EpisodeKind.DECISION,
        occurred_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=2) + timedelta(minutes=5),
        title="Prepared capacity for rain",
        content_ref=f"memory://{episode_id}",
        evidence_refs=(f"evidence://{episode_id}",),
        entity_refs=("warehouse:fulya",),
        tags=("weather", "capacity"),
        importance=0.9,
        retention_class=RetentionClass.OPERATIONAL,
        retain_until=NOW + timedelta(days=30),
        confidentiality=Confidentiality.INTERNAL,
        model_summary="Rain capacity preparation decision.",
    )
    payload.update(overrides)
    return MemoryEpisode(**payload)


def test_recall_is_tenant_entity_and_tag_scoped():
    episodes = [
        _episode("fulya"),
        _episode("other", tenant_id="warehouse:besiktas", entity_refs=("warehouse:besiktas",)),
    ]
    recall = recall_episodes(
        episodes,
        MemoryQuery(
            tenant_id="warehouse:fulya",
            as_of=NOW,
            entity_refs=("warehouse:fulya",),
            tags=("weather",),
        ),
    )

    assert [item.episode_id for item in recall.episodes] == ["fulya"]
    assert recall.memory_is_authoritative_truth is False


def test_expired_episode_is_omitted_and_counted():
    expired = _episode(
        "expired",
        occurred_at=NOW - timedelta(days=10),
        recorded_at=NOW - timedelta(days=10) + timedelta(minutes=1),
        retain_until=NOW - timedelta(days=1),
    )
    recall = recall_episodes(
        [expired],
        MemoryQuery(tenant_id="warehouse:fulya", as_of=NOW),
    )

    assert recall.episodes == ()
    assert recall.omitted_expired_count == 1


def test_transient_episode_requires_explicit_expiry():
    with pytest.raises(ValueError, match="transient_episode_requires_expiry"):
        _episode(
            "transient-no-expiry",
            retention_class=RetentionClass.TRANSIENT,
            retain_until=None,
        )


def test_legal_hold_has_no_automatic_expiry():
    with pytest.raises(ValueError, match="legal_hold_episode_must_not_have_automatic_expiry"):
        _episode("legal", retention_class=RetentionClass.LEGAL_HOLD)


def test_model_summary_cannot_be_declared_truth():
    with pytest.raises(ValueError, match="model_summary_cannot_be_promoted_to_episode_truth"):
        _episode("bad-summary", model_summary_is_truth=True)


def test_recent_high_importance_episode_ranks_above_old_lower_importance():
    recent = _episode(
        "recent",
        occurred_at=NOW - timedelta(hours=2),
        recorded_at=NOW - timedelta(hours=1, minutes=59),
        importance=0.95,
    )
    old = _episode(
        "old",
        occurred_at=NOW - timedelta(days=20),
        recorded_at=NOW - timedelta(days=20) + timedelta(minutes=1),
        importance=0.5,
    )
    recall = recall_episodes(
        [old, recent],
        MemoryQuery(tenant_id="warehouse:fulya", as_of=NOW, tags=("capacity",)),
    )

    assert [item.episode_id for item in recall.episodes] == ["recent", "old"]
