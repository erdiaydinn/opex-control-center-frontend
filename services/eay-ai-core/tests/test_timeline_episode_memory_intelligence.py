from datetime import datetime, timedelta, timezone

import pytest

from app.episodic_memory import MemoryQuery, recall_episodes
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineEventLink,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    TimelineRelationKind,
    build_real_world_timeline,
    build_timeline_event,
)
from app.timeline_episode_memory import memory_episode_from_timeline_chain


NOW = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)


def _event(
    event_id: str,
    *,
    at: datetime,
    observed_at: datetime | None = None,
    kind: TimelineEventKind,
    authority: TimelineAuthorityClass,
    entity_ref: str = "store:fulya",
):
    event_type = {
        TimelineEventKind.DECISION: "eay.decision.recorded",
        TimelineEventKind.ACTION: "eay.action.verified",
        TimelineEventKind.OUTCOME: "eay.outcome.observed",
        TimelineEventKind.COMPANY_ASSERTION: "eay.company.assertion",
    }[kind]
    return build_timeline_event(
        event_id=event_id,
        event_type=event_type,
        event_kind=kind,
        source_ref=f"source://{event_id}",
        tenant_id="YS_TR",
        occurred_at=at,
        observed_at=observed_at or at,
        data_ref=f"data://{event_id}",
        authority_class=authority,
        confidence=0.95,
        object_relations=(
            TimelineObjectRelation(
                object_ref=entity_ref,
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=(f"evidence://{event_id}",),
        tags=("store:fulya",),
    )


def _decision_action_outcome_snapshot():
    decision = _event(
        "decision-1",
        at=NOW,
        kind=TimelineEventKind.DECISION,
        authority=TimelineAuthorityClass.DECISION_RECORD,
    )
    action = _event(
        "action-1",
        at=NOW + timedelta(minutes=5),
        observed_at=NOW + timedelta(minutes=6),
        kind=TimelineEventKind.ACTION,
        authority=TimelineAuthorityClass.VERIFIED_ACTION,
    )
    outcome = _event(
        "outcome-1",
        at=NOW + timedelta(hours=1),
        observed_at=NOW + timedelta(hours=2),
        kind=TimelineEventKind.OUTCOME,
        authority=TimelineAuthorityClass.VERIFIED_OUTCOME,
    )
    links = (
        TimelineEventLink(
            tenant_id="YS_TR",
            source_event_id=action.event_id,
            relation=TimelineRelationKind.ACTION_EXECUTES_DECISION,
            target_event_id=decision.event_id,
            evidence_refs=("evidence://decision-action-link",),
            confidence=0.95,
        ),
        TimelineEventLink(
            tenant_id="YS_TR",
            source_event_id=action.event_id,
            relation=TimelineRelationKind.OUTCOME_FOLLOWS_ACTION,
            target_event_id=outcome.event_id,
            evidence_refs=("evidence://action-outcome-link",),
            confidence=0.95,
        ),
    )
    return build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW - timedelta(minutes=1),
        window_end=NOW + timedelta(hours=3),
        events=(decision, action, outcome),
        links=links,
    )


def test_timeline_chain_becomes_reference_only_memory_episode() -> None:
    snapshot = _decision_action_outcome_snapshot()
    episode = memory_episode_from_timeline_chain(
        snapshot=snapshot,
        focal_event_id="outcome-1",
        related_event_ids=("decision-1", "action-1"),
    )
    encoded = episode.model_dump_json()

    assert episode.occurred_at == NOW
    assert episode.recorded_at == NOW + timedelta(hours=2)
    assert snapshot.fingerprint in episode.content_ref
    assert episode.model_summary is None
    assert episode.model_summary_is_truth is False
    assert "before_value" not in encoded
    assert "after_value" not in encoded
    assert "observed_value" not in encoded
    assert set(episode.entity_refs) == {"store:fulya"}


def test_memory_recall_cannot_see_episode_before_it_was_recorded() -> None:
    snapshot = _decision_action_outcome_snapshot()
    episode = memory_episode_from_timeline_chain(
        snapshot=snapshot,
        focal_event_id="outcome-1",
        related_event_ids=("decision-1", "action-1"),
    )

    historical = recall_episodes(
        [episode],
        MemoryQuery(
            tenant_id="YS_TR",
            as_of=NOW + timedelta(hours=1, minutes=30),
            entity_refs=("store:fulya",),
        ),
    )
    current = recall_episodes(
        [episode],
        MemoryQuery(
            tenant_id="YS_TR",
            as_of=NOW + timedelta(hours=2, minutes=1),
            entity_refs=("store:fulya",),
        ),
    )

    assert historical.episodes == ()
    assert historical.omitted_expired_count == 0
    assert tuple(item.episode_id for item in current.episodes) == (episode.episode_id,)
    assert current.memory_is_authoritative_truth is False


def test_disconnected_timeline_events_cannot_be_forced_into_one_memory_episode() -> None:
    snapshot = _decision_action_outcome_snapshot()
    disconnected = _event(
        "unrelated-company-state",
        at=NOW + timedelta(minutes=10),
        kind=TimelineEventKind.COMPANY_ASSERTION,
        authority=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        entity_ref="store:uskudar",
    )
    expanded = build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        events=(*snapshot.events, disconnected),
        links=snapshot.links,
    )

    with pytest.raises(ValueError, match="timeline_memory_chain_must_be_connected"):
        memory_episode_from_timeline_chain(
            snapshot=expanded,
            focal_event_id="outcome-1",
            related_event_ids=("decision-1", "action-1", "unrelated-company-state"),
        )


def test_tampered_timeline_snapshot_is_rejected_before_memory_creation() -> None:
    snapshot = _decision_action_outcome_snapshot()
    tampered = snapshot.model_copy(update={"fingerprint": "f" * 64})

    with pytest.raises(ValueError, match="timeline_snapshot_fingerprint_mismatch"):
        memory_episode_from_timeline_chain(
            snapshot=tampered,
            focal_event_id="outcome-1",
            related_event_ids=("decision-1", "action-1"),
        )
