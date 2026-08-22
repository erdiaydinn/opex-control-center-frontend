"""Object-centric real-world event timeline for EAY Jarvis.

The timeline is an index over canonical evidence; it is never a source of truth,
an execution-authority surface, or a causal proof engine. Event envelopes are
CloudEvents-aligned and event/object relationships are inspired by OCEL-style
object-centric logs so one real-world occurrence can be related to many EAY
objects without forcing a single case identifier.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field, model_validator

REAL_WORLD_TIMELINE_CONTRACT = "eay-real-world-timeline-v1"
CLOUDEVENTS_SPECVERSION = "1.0"

_EVENT_TYPE_PATTERN = re.compile(r"^eay\.[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class TimelineEventKind(str, Enum):
    COMPANY_ASSERTION = "company_assertion"
    EXTERNAL_CONTEXT = "external_context"
    AMBIENT_OBSERVATION = "ambient_observation"
    DEVICE_OBSERVATION = "device_observation"
    DECISION = "decision"
    ACTION = "action"
    OUTCOME = "outcome"
    INCIDENT = "incident"


class TimelineAuthorityClass(str, Enum):
    GOVERNED_OPERATIONAL = "governed_operational"
    VERIFIED_COMPANY = "verified_company"
    VERIFIED_LEGAL = "verified_legal"
    VERIFIED_EXTERNAL = "verified_external"
    ANALYTIC_INFERENCE = "analytic_inference"
    CONTEXT_ONLY = "context_only"
    AMBIENT_UNTRUSTED = "ambient_untrusted"
    DEVICE_OBSERVATION = "device_observation"
    DECISION_RECORD = "decision_record"
    VERIFIED_ACTION = "verified_action"
    VERIFIED_OUTCOME = "verified_outcome"


class TimelineObjectKind(str, Enum):
    WORLD_ENTITY = "world_entity"
    LOCATION = "location"
    DEVICE = "device"
    APPLICATION = "application"
    PERSON = "person"
    MISSION = "mission"
    DECISION = "decision"
    ACTION = "action"
    CONTEXT_SIGNAL = "context_signal"
    SOURCE = "source"


class TimelineObjectQualifier(str, Enum):
    SUBJECT = "subject"
    ACTOR = "actor"
    TARGET = "target"
    AFFECTED = "affected"
    LOCATION = "location"
    SOURCE = "source"
    CONTEXT = "context"
    RESULT = "result"


class TimelineRelationKind(str, Enum):
    TEMPORALLY_CORRELATED = "temporally_correlated"
    DERIVED_FROM = "derived_from"
    OBSERVATION_UPDATES_STATE = "observation_updates_state"
    DECISION_RESPONDS_TO = "decision_responds_to"
    ACTION_EXECUTES_DECISION = "action_executes_decision"
    OUTCOME_FOLLOWS_ACTION = "outcome_follows_action"


class TimelineObjectRelation(BaseModel):
    object_ref: str = Field(min_length=1, max_length=500)
    object_kind: TimelineObjectKind
    qualifier: TimelineObjectQualifier


class RealWorldTimelineEvent(BaseModel):
    contract: str = REAL_WORLD_TIMELINE_CONTRACT
    cloudevents_specversion: str = CLOUDEVENTS_SPECVERSION
    event_id: str = Field(min_length=1, max_length=500)
    event_type: str = Field(min_length=1, max_length=200)
    event_kind: TimelineEventKind
    source_ref: str = Field(min_length=1, max_length=1000)
    tenant_id: str = Field(min_length=1, max_length=200)
    occurred_at: datetime
    observed_at: datetime
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    data_ref: str = Field(min_length=1, max_length=1000)
    authority_class: TimelineAuthorityClass
    confidence: float = Field(ge=0.0, le=1.0)
    object_relations: tuple[TimelineObjectRelation, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    tags: tuple[str, ...] = ()
    raw_content_retained: bool = False
    timeline_grants_truth_authority: bool = False
    execution_authority_granted: bool = False
    causal_claim_proven: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_boundary(self) -> "RealWorldTimelineEvent":
        for value, error in (
            (self.occurred_at, "timeline_event_occurred_at_requires_timezone"),
            (self.observed_at, "timeline_event_observed_at_requires_timezone"),
        ):
            _require_aware(value, error)
        if self.observed_at < self.occurred_at:
            raise ValueError("timeline_event_observed_before_occurrence")
        if self.effective_from is not None:
            _require_aware(self.effective_from, "timeline_event_effective_from_requires_timezone")
        if self.effective_until is not None:
            _require_aware(self.effective_until, "timeline_event_effective_until_requires_timezone")
            if self.effective_from is None:
                raise ValueError("timeline_event_effective_until_requires_effective_from")
            if self.effective_until <= self.effective_from:
                raise ValueError("timeline_event_effective_interval_invalid")
        if self.cloudevents_specversion != CLOUDEVENTS_SPECVERSION:
            raise ValueError("timeline_cloudevents_specversion_must_be_1_0")
        if not _EVENT_TYPE_PATTERN.fullmatch(self.event_type):
            raise ValueError("timeline_event_type_must_be_low_cardinality_eay_name")
        if (
            self.raw_content_retained
            or self.timeline_grants_truth_authority
            or self.execution_authority_granted
            or self.causal_claim_proven
        ):
            raise ValueError("timeline_event_is_index_only_not_authority")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("timeline_event_duplicate_evidence_ref")
        for ref in (self.source_ref, self.data_ref, *self.evidence_refs):
            if not _reference_is_secret_safe(ref):
                raise ValueError("timeline_event_reference_may_contain_secret")
        if len({(item.object_ref, item.object_kind, item.qualifier) for item in self.object_relations}) != len(
            self.object_relations
        ):
            raise ValueError("timeline_event_duplicate_object_relation")
        expected = _event_fingerprint(_event_payload(self))
        if self.fingerprint != expected:
            raise ValueError("timeline_event_fingerprint_mismatch")
        return self


class TimelineEventLink(BaseModel):
    tenant_id: str = Field(min_length=1)
    source_event_id: str = Field(min_length=1)
    relation: TimelineRelationKind
    target_event_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def link_is_non_causal(self) -> "TimelineEventLink":
        if self.source_event_id == self.target_event_id:
            raise ValueError("timeline_self_link_forbidden")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("timeline_link_duplicate_evidence_ref")
        if any(not _reference_is_secret_safe(ref) for ref in self.evidence_refs):
            raise ValueError("timeline_link_reference_may_contain_secret")
        if self.causal_claim_proven:
            raise ValueError("timeline_link_cannot_assert_causality")
        if self.execution_authority_granted:
            raise ValueError("timeline_link_cannot_grant_execution")
        return self


class RealWorldTimelineSnapshot(BaseModel):
    contract: str = REAL_WORLD_TIMELINE_CONTRACT
    tenant_id: str
    window_start: datetime
    window_end: datetime
    events: tuple[RealWorldTimelineEvent, ...]
    links: tuple[TimelineEventLink, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    authoritative_truth_surface: bool = False
    execution_authority_surface: bool = False
    causal_proof_surface: bool = False

    @model_validator(mode="after")
    def snapshot_boundary(self) -> "RealWorldTimelineSnapshot":
        _require_aware(self.window_start, "timeline_window_start_requires_timezone")
        _require_aware(self.window_end, "timeline_window_end_requires_timezone")
        if self.window_end <= self.window_start:
            raise ValueError("timeline_window_invalid")
        if self.authoritative_truth_surface or self.execution_authority_surface or self.causal_proof_surface:
            raise ValueError("timeline_snapshot_is_index_only")
        if any(item.tenant_id != self.tenant_id for item in self.events):
            raise ValueError("timeline_cross_tenant_event_forbidden")
        if any(item.tenant_id != self.tenant_id for item in self.links):
            raise ValueError("timeline_cross_tenant_link_forbidden")
        event_id_list = [item.event_id for item in self.events]
        if len(event_id_list) != len(set(event_id_list)):
            raise ValueError("timeline_snapshot_duplicate_event_id")
        event_ids = set(event_id_list)
        if any(link.source_event_id not in event_ids or link.target_event_id not in event_ids for link in self.links):
            raise ValueError("timeline_link_references_missing_event")
        expected = _snapshot_fingerprint(
            tenant_id=self.tenant_id,
            window_start=self.window_start,
            window_end=self.window_end,
            events=self.events,
            links=self.links,
        )
        if self.fingerprint != expected:
            raise ValueError("timeline_snapshot_fingerprint_mismatch")
        return self


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _reference_is_secret_safe(value: str) -> bool:
    folded = value.casefold()
    forbidden = (
        "authorization=",
        "bearer ",
        "token=",
        "access_token=",
        "refresh_token=",
        "api_key=",
        "apikey=",
        "password=",
        "passwd=",
        "x-amz-signature=",
    )
    return not any(marker in folded for marker in forbidden)


def _canonical_hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_payload(event: RealWorldTimelineEvent) -> dict[str, object]:
    return {
        "contract": event.contract,
        "cloudevents_specversion": event.cloudevents_specversion,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_kind": event.event_kind.value,
        "source_ref": event.source_ref,
        "tenant_id": event.tenant_id,
        "occurred_at": event.occurred_at.isoformat(),
        "observed_at": event.observed_at.isoformat(),
        "effective_from": event.effective_from.isoformat() if event.effective_from else None,
        "effective_until": event.effective_until.isoformat() if event.effective_until else None,
        "data_ref": event.data_ref,
        "authority_class": event.authority_class.value,
        "confidence": event.confidence,
        "object_relations": [
            item.model_dump(mode="json")
            for item in sorted(
                event.object_relations,
                key=lambda item: (item.object_kind.value, item.object_ref, item.qualifier.value),
            )
        ],
        "evidence_refs": sorted(event.evidence_refs),
        "tags": sorted(event.tags),
        "raw_content_retained": False,
        "timeline_grants_truth_authority": False,
        "execution_authority_granted": False,
        "causal_claim_proven": False,
    }


def _event_fingerprint(payload: dict[str, object]) -> str:
    return _canonical_hash(payload)


def build_timeline_event(
    *,
    event_id: str,
    event_type: str,
    event_kind: TimelineEventKind,
    source_ref: str,
    tenant_id: str,
    occurred_at: datetime,
    observed_at: datetime,
    data_ref: str,
    authority_class: TimelineAuthorityClass,
    confidence: float,
    object_relations: Iterable[TimelineObjectRelation],
    evidence_refs: Iterable[str],
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    tags: Iterable[str] = (),
) -> RealWorldTimelineEvent:
    payload = dict(
        event_id=event_id,
        event_type=event_type,
        event_kind=event_kind,
        source_ref=source_ref,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        observed_at=observed_at,
        effective_from=effective_from,
        effective_until=effective_until,
        data_ref=data_ref,
        authority_class=authority_class,
        confidence=confidence,
        object_relations=tuple(object_relations),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        tags=tuple(dict.fromkeys(tags)),
    )
    provisional = RealWorldTimelineEvent.model_construct(
        contract=REAL_WORLD_TIMELINE_CONTRACT,
        cloudevents_specversion=CLOUDEVENTS_SPECVERSION,
        **payload,
        raw_content_retained=False,
        timeline_grants_truth_authority=False,
        execution_authority_granted=False,
        causal_claim_proven=False,
        fingerprint="0" * 64,
    )
    fingerprint = _event_fingerprint(_event_payload(provisional))
    return RealWorldTimelineEvent(**payload, fingerprint=fingerprint)


def _snapshot_fingerprint(
    *,
    tenant_id: str,
    window_start: datetime,
    window_end: datetime,
    events: tuple[RealWorldTimelineEvent, ...],
    links: tuple[TimelineEventLink, ...],
) -> str:
    payload = {
        "tenant_id": tenant_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "events": [
            {"event_id": item.event_id, "fingerprint": item.fingerprint}
            for item in events
        ],
        "links": [
            {
                **item.model_dump(mode="json", exclude={"evidence_refs"}),
                "evidence_refs": sorted(item.evidence_refs),
            }
            for item in links
        ],
    }
    return _canonical_hash(payload)


def build_real_world_timeline(
    *,
    tenant_id: str,
    window_start: datetime,
    window_end: datetime,
    events: Iterable[RealWorldTimelineEvent],
    links: Iterable[TimelineEventLink] = (),
) -> RealWorldTimelineSnapshot:
    _require_aware(window_start, "timeline_window_start_requires_timezone")
    _require_aware(window_end, "timeline_window_end_requires_timezone")
    if window_end <= window_start:
        raise ValueError("timeline_window_invalid")

    by_id: dict[str, RealWorldTimelineEvent] = {}
    for event in events:
        event = validate_timeline_event_integrity(event)
        if event.tenant_id != tenant_id:
            raise ValueError("timeline_cross_tenant_event_forbidden")
        existing = by_id.get(event.event_id)
        if existing is not None and existing.fingerprint != event.fingerprint:
            raise ValueError("timeline_event_id_conflict")
        by_id[event.event_id] = event

    def intersects_window(item: RealWorldTimelineEvent) -> bool:
        occurred_in_window = window_start <= item.occurred_at < window_end
        effective_in_window = (
            item.effective_from is not None
            and item.effective_from < window_end
            and (item.effective_until is None or item.effective_until > window_start)
        )
        # Historical replay must never see evidence that Jarvis had not observed yet.
        observed_by_window_end = item.observed_at < window_end
        return observed_by_window_end and (occurred_in_window or effective_in_window)

    selected = tuple(
        sorted(
            (item for item in by_id.values() if intersects_window(item)),
            key=lambda item: (
                item.effective_from or item.occurred_at,
                item.occurred_at,
                item.observed_at,
                item.event_id,
            ),
        )
    )
    selected_ids = {item.event_id for item in selected}

    validated_links: list[TimelineEventLink] = []
    all_event_ids = set(by_id)
    for link in links:
        link = TimelineEventLink.model_validate(link.model_dump(mode="json"))
        if link.tenant_id != tenant_id:
            raise ValueError("timeline_cross_tenant_link_forbidden")
        if link.source_event_id not in all_event_ids or link.target_event_id not in all_event_ids:
            raise ValueError("timeline_link_references_unknown_event")
        validated_links.append(link)

    selected_links = tuple(
        sorted(
            (
                link
                for link in validated_links
                if link.source_event_id in selected_ids and link.target_event_id in selected_ids
            ),
            key=lambda link: (link.source_event_id, link.relation.value, link.target_event_id),
        )
    )

    fingerprint = _snapshot_fingerprint(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        events=selected,
        links=selected_links,
    )
    return RealWorldTimelineSnapshot(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        events=selected,
        links=selected_links,
        fingerprint=fingerprint,
    )


def validate_timeline_event_integrity(event: RealWorldTimelineEvent) -> RealWorldTimelineEvent:
    return RealWorldTimelineEvent.model_validate(event.model_dump(mode="json"))
