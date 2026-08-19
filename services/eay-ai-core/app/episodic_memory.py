"""Provenance-bound episodic memory for Jarvis.

Episodic memory remembers decisions, incidents, actions and outcomes without
turning model-written recollections into truth. Every episode is tenant-bound,
time-bound, retention-bound and backed by evidence references. Recall is a
ranking operation over eligible episodes; it does not alter the Company World
Model or bypass source authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

EPISODIC_MEMORY_CONTRACT = "eay-episodic-memory-v1"


class EpisodeKind(str, Enum):
    DECISION = "decision"
    ACTION = "action"
    OUTCOME = "outcome"
    INCIDENT = "incident"
    OBSERVATION = "observation"
    CONVERSATION = "conversation"
    LESSON = "lesson"


class RetentionClass(str, Enum):
    TRANSIENT = "transient"
    OPERATIONAL = "operational"
    LONG_TERM = "long_term"
    LEGAL_HOLD = "legal_hold"


class Confidentiality(str, Enum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class MemoryEpisode(BaseModel):
    episode_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    kind: EpisodeKind
    occurred_at: datetime
    recorded_at: datetime
    title: str = Field(min_length=1)
    content_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    entity_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    retention_class: RetentionClass = RetentionClass.OPERATIONAL
    retain_until: datetime | None = None
    confidentiality: Confidentiality = Confidentiality.INTERNAL
    model_summary: str | None = None
    model_summary_is_truth: bool = False

    @model_validator(mode="after")
    def temporal_retention_and_truth_contract(self) -> "MemoryEpisode":
        for value, error in (
            (self.occurred_at, "episode_occurred_at_requires_timezone"),
            (self.recorded_at, "episode_recorded_at_requires_timezone"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(error)
        if self.recorded_at < self.occurred_at:
            raise ValueError("episode_recorded_before_occurrence")
        if self.retain_until is not None:
            if self.retain_until.tzinfo is None or self.retain_until.utcoffset() is None:
                raise ValueError("episode_retain_until_requires_timezone")
            if self.retain_until <= self.recorded_at:
                raise ValueError("episode_retention_must_extend_past_recording")
        if self.retention_class is RetentionClass.TRANSIENT and self.retain_until is None:
            raise ValueError("transient_episode_requires_expiry")
        if self.retention_class is RetentionClass.LEGAL_HOLD and self.retain_until is not None:
            raise ValueError("legal_hold_episode_must_not_have_automatic_expiry")
        if self.model_summary_is_truth:
            raise ValueError("model_summary_cannot_be_promoted_to_episode_truth")
        return self

    def eligible_at(self, as_of: datetime) -> bool:
        if self.occurred_at > as_of or self.recorded_at > as_of:
            return False
        if self.retention_class is RetentionClass.LEGAL_HOLD:
            return True
        return self.retain_until is None or as_of < self.retain_until


class MemoryQuery(BaseModel):
    tenant_id: str = Field(min_length=1)
    as_of: datetime
    entity_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    kinds: tuple[EpisodeKind, ...] = ()
    maximum_age: timedelta | None = None
    minimum_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    maximum_results: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def query_time_is_aware(self) -> "MemoryQuery":
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("memory_query_as_of_requires_timezone")
        if self.maximum_age is not None and self.maximum_age <= timedelta(0):
            raise ValueError("memory_query_maximum_age_must_be_positive")
        return self


class RecalledEpisode(BaseModel):
    episode_id: str
    score: float = Field(ge=0.0, le=1.0)
    title: str
    occurred_at: datetime
    kind: EpisodeKind
    content_ref: str
    evidence_refs: tuple[str, ...]
    entity_refs: tuple[str, ...]
    tags: tuple[str, ...]
    model_summary: str | None = None


class MemoryRecall(BaseModel):
    contract: str = EPISODIC_MEMORY_CONTRACT
    tenant_id: str
    as_of: datetime
    episodes: tuple[RecalledEpisode, ...]
    omitted_expired_count: int = Field(ge=0)
    memory_is_authoritative_truth: bool = False

    @model_validator(mode="after")
    def memory_never_becomes_authority(self) -> "MemoryRecall":
        if self.memory_is_authoritative_truth:
            raise ValueError("episodic_memory_cannot_be_authoritative_truth")
        return self


def recall_episodes(episodes: list[MemoryEpisode], query: MemoryQuery) -> MemoryRecall:
    requested_entities = set(query.entity_refs)
    requested_tags = {tag.casefold() for tag in query.tags}
    requested_kinds = set(query.kinds)
    expired = 0
    ranked: list[RecalledEpisode] = []

    for episode in episodes:
        if episode.tenant_id != query.tenant_id:
            continue
        # Historical recall must not reveal an episode before Jarvis actually recorded it.
        if episode.recorded_at > query.as_of:
            continue
        if not episode.eligible_at(query.as_of):
            if episode.occurred_at <= query.as_of:
                expired += 1
            continue
        if query.maximum_age is not None and query.as_of - episode.occurred_at > query.maximum_age:
            continue
        if episode.importance < query.minimum_importance:
            continue
        if requested_kinds and episode.kind not in requested_kinds:
            continue

        episode_entities = set(episode.entity_refs)
        episode_tags = {tag.casefold() for tag in episode.tags}
        entity_overlap = len(requested_entities & episode_entities)
        tag_overlap = len(requested_tags & episode_tags)
        if requested_entities and entity_overlap == 0:
            continue
        if requested_tags and tag_overlap == 0:
            continue

        age_seconds = max(0.0, (query.as_of - episode.occurred_at).total_seconds())
        recency = 1.0 / (1.0 + age_seconds / 86400.0)
        score = 0.35 * episode.importance + 0.25 * recency
        if requested_entities:
            score += 0.25 * min(1.0, entity_overlap / max(1, len(requested_entities)))
        if requested_tags:
            score += 0.15 * min(1.0, tag_overlap / max(1, len(requested_tags)))
        if not requested_entities and not requested_tags:
            score += 0.20
        score = min(score, 1.0)

        ranked.append(
            RecalledEpisode(
                episode_id=episode.episode_id,
                score=round(score, 6),
                title=episode.title,
                occurred_at=episode.occurred_at,
                kind=episode.kind,
                content_ref=episode.content_ref,
                evidence_refs=episode.evidence_refs,
                entity_refs=episode.entity_refs,
                tags=episode.tags,
                model_summary=episode.model_summary,
            )
        )

    ranked.sort(key=lambda item: (-item.score, -item.occurred_at.timestamp(), item.episode_id))
    return MemoryRecall(
        tenant_id=query.tenant_id,
        as_of=query.as_of,
        episodes=tuple(ranked[: query.maximum_results]),
        omitted_expired_count=expired,
    )
