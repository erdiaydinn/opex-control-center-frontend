"""Derive provenance-bound episodic memory views from the real-world timeline.

The timeline remains the canonical event index. Episodic memory stores only a
stable reference to a connected timeline chain plus evidence/entity/tag indexes;
it never copies canonical business payload values into memory.
"""

from __future__ import annotations

import hashlib

from app.episodic_memory import (
    Confidentiality,
    EpisodeKind,
    MemoryEpisode,
    RetentionClass,
)
from app.real_world_timeline import (
    RealWorldTimelineEvent,
    RealWorldTimelineSnapshot,
    TimelineEventKind,
)


_EVENT_KIND_TO_EPISODE_KIND = {
    TimelineEventKind.DECISION: EpisodeKind.DECISION,
    TimelineEventKind.ACTION: EpisodeKind.ACTION,
    TimelineEventKind.OUTCOME: EpisodeKind.OUTCOME,
    TimelineEventKind.INCIDENT: EpisodeKind.INCIDENT,
}


def _stable_token(*values: str) -> str:
    material = "\x1f".join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def _selected_chain_is_connected(
    *,
    snapshot: RealWorldTimelineSnapshot,
    selected_ids: set[str],
    focal_event_id: str,
) -> bool:
    adjacency = {event_id: set() for event_id in selected_ids}
    for link in snapshot.links:
        if link.source_event_id in selected_ids and link.target_event_id in selected_ids:
            adjacency[link.source_event_id].add(link.target_event_id)
            adjacency[link.target_event_id].add(link.source_event_id)

    visited = {focal_event_id}
    pending = [focal_event_id]
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current] - visited:
            visited.add(neighbor)
            pending.append(neighbor)
    return visited == selected_ids


def memory_episode_from_timeline_chain(
    *,
    snapshot: RealWorldTimelineSnapshot,
    focal_event_id: str,
    related_event_ids: tuple[str, ...] = (),
    importance: float = 0.7,
    retention_class: RetentionClass = RetentionClass.OPERATIONAL,
    retain_until=None,
    confidentiality: Confidentiality = Confidentiality.INTERNAL,
) -> MemoryEpisode:
    """Create a memory index for one connected timeline chain without payload copying."""

    snapshot = RealWorldTimelineSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if len(set(related_event_ids)) != len(related_event_ids):
        raise ValueError("timeline_memory_duplicate_related_event")

    by_id = {item.event_id: item for item in snapshot.events}
    focal = by_id.get(focal_event_id)
    if focal is None:
        raise ValueError("timeline_memory_focal_event_missing")

    selected_ids = {focal_event_id, *related_event_ids}
    unknown = selected_ids - set(by_id)
    if unknown:
        raise ValueError("timeline_memory_related_event_missing")
    if len(selected_ids) > 1 and not _selected_chain_is_connected(
        snapshot=snapshot,
        selected_ids=selected_ids,
        focal_event_id=focal_event_id,
    ):
        raise ValueError("timeline_memory_chain_must_be_connected")

    selected: tuple[RealWorldTimelineEvent, ...] = tuple(
        sorted(
            (by_id[event_id] for event_id in selected_ids),
            key=lambda item: (item.occurred_at, item.observed_at, item.event_id),
        )
    )
    selected_links = tuple(
        link
        for link in snapshot.links
        if link.source_event_id in selected_ids and link.target_event_id in selected_ids
    )
    occurred_at = min(item.occurred_at for item in selected)
    recorded_at = max(item.observed_at for item in selected)
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *(ref for event in selected for ref in event.evidence_refs),
                *(ref for link in selected_links for ref in link.evidence_refs),
            )
        )
    )
    entity_refs = tuple(
        dict.fromkeys(
            relation.object_ref
            for event in selected
            for relation in event.object_relations
        )
    )
    tags = tuple(
        dict.fromkeys(
            (
                *(tag for event in selected for tag in event.tags),
                *(f"timeline_kind:{event.event_kind.value}" for event in selected),
            )
        )
    )
    ordered_ids = tuple(sorted(selected_ids))
    chain_token = _stable_token(snapshot.fingerprint, focal_event_id, *ordered_ids)
    episode_kind = _EVENT_KIND_TO_EPISODE_KIND.get(
        focal.event_kind,
        EpisodeKind.OBSERVATION,
    )

    return MemoryEpisode(
        episode_id=f"timeline-episode:{chain_token}",
        tenant_id=snapshot.tenant_id,
        kind=episode_kind,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
        title=f"Timeline chain: {focal.event_kind.value}",
        content_ref=f"timeline://{snapshot.fingerprint}/chain/{chain_token}",
        evidence_refs=evidence_refs,
        entity_refs=entity_refs,
        tags=tags,
        importance=importance,
        retention_class=retention_class,
        retain_until=retain_until,
        confidentiality=confidentiality,
        model_summary=None,
        model_summary_is_truth=False,
    )
