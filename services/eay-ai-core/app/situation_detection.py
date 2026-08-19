"""Evidence-bound real-time situation detection for Jarvis.

A situation is a non-causal attention candidate assembled from already-governed
timeline events plus secret-safe swarm pressure telemetry. It is not Company World
truth, not a root-cause claim and not execution/replanning authority.

Strong authority is required before a situation may be actionable. Ambient/device
or analytic observations can enrich a verified situation but cannot create one by
themselves.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .alert_intelligence import AlertCandidate
from .real_world_timeline import (
    RealWorldTimelineEvent,
    TimelineAuthorityClass,
)
from .swarm_execution_telemetry import SwarmExecutionTelemetrySnapshot

SITUATION_DETECTION_CONTRACT = "eay-situation-detection-v1"

_STRONG_AUTHORITIES = frozenset(
    {
        TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        TimelineAuthorityClass.VERIFIED_COMPANY,
        TimelineAuthorityClass.VERIFIED_EXTERNAL,
        TimelineAuthorityClass.VERIFIED_LEGAL,
        TimelineAuthorityClass.VERIFIED_ACTION,
        TimelineAuthorityClass.VERIFIED_OUTCOME,
    }
)


class SituationAttention(str, Enum):
    WATCH = "watch"
    SURFACE = "surface"
    ESCALATE = "escalate"


class SituationDetectionPolicy(BaseModel):
    window_seconds: int = Field(default=900, ge=30, le=86_400)
    min_shared_object_events: int = Field(default=3, ge=2, le=100)
    min_distinct_event_types: int = Field(default=2, ge=2, le=50)
    min_distinct_domains: int = Field(default=2, ge=1, le=50)
    min_strong_authority_events: int = Field(default=2, ge=1, le=100)
    min_mean_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    pressure_surface_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    escalation_score_threshold: float = Field(default=0.78, ge=0.0, le=1.0)


class SituationCandidate(BaseModel):
    contract: str = SITUATION_DETECTION_CONTRACT
    situation_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    detected_at: datetime
    event_ids: tuple[str, ...] = Field(min_length=1)
    event_types: tuple[str, ...] = Field(min_length=1)
    domains: tuple[str, ...] = Field(min_length=1)
    strong_authority_event_count: int = Field(ge=0)
    mean_confidence: float = Field(ge=0.0, le=1.0)
    swarm_pressure_score: float = Field(ge=0.0, le=1.0)
    situation_score: float = Field(ge=0.0, le=1.0)
    attention: SituationAttention
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    actionable_attention: bool = False
    causal_claim_proven: bool = False
    truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def candidate_is_non_authoritative_and_integral(self) -> "SituationCandidate":
        if self.detected_at.tzinfo is None or self.detected_at.utcoffset() is None:
            raise ValueError("situation_detection_requires_timezone")
        if (
            self.causal_claim_proven
            or self.truth_authority_granted
            or self.replanning_authority_granted
            or self.execution_authority_granted
        ):
            raise ValueError("situation_candidate_never_grants_authority_or_causality")
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("situation_candidate_event_ids_must_be_unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("situation_candidate_evidence_refs_must_be_unique")
        expected = _canonical_hash(
            self.model_dump(mode="json", exclude={"fingerprint"})
        )
        if self.fingerprint != expected:
            raise ValueError("situation_candidate_fingerprint_mismatch")
        return self


def _canonical_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_domain(event_type: str) -> str:
    parts = event_type.split(".")
    if len(parts) >= 3:
        return parts[2]
    return parts[-1]


def _validated_event(event: RealWorldTimelineEvent) -> RealWorldTimelineEvent:
    return RealWorldTimelineEvent.model_validate(event.model_dump(mode="json"))


def _validated_telemetry(
    telemetry: SwarmExecutionTelemetrySnapshot,
) -> SwarmExecutionTelemetrySnapshot:
    return SwarmExecutionTelemetrySnapshot.model_validate(
        telemetry.model_dump(mode="json")
    )


def detect_situations(
    *,
    events: tuple[RealWorldTimelineEvent, ...],
    telemetry: SwarmExecutionTelemetrySnapshot,
    tenant_id: str,
    now: datetime,
    policy: SituationDetectionPolicy | None = None,
) -> tuple[SituationCandidate, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("situation_detection_requires_timezone")
    rules = policy or SituationDetectionPolicy()
    telemetry = _validated_telemetry(telemetry)
    if telemetry.tenant_id != tenant_id:
        raise ValueError("situation_detection_telemetry_tenant_mismatch")
    if telemetry.observed_at > now:
        raise ValueError("situation_detection_telemetry_from_future")

    cutoff = now - timedelta(seconds=rules.window_seconds)
    eligible_events: list[RealWorldTimelineEvent] = []
    for raw in events:
        event = _validated_event(raw)
        if event.tenant_id != tenant_id:
            raise ValueError("situation_detection_cross_tenant_event_forbidden")
        if event.observed_at > now:
            continue
        if event.observed_at < cutoff:
            continue
        eligible_events.append(event)

    by_object: dict[str, list[RealWorldTimelineEvent]] = defaultdict(list)
    for event in eligible_events:
        for relation in event.object_relations:
            by_object[relation.object_ref].append(event)

    candidates: list[SituationCandidate] = []
    for object_ref, object_events in sorted(by_object.items()):
        unique_by_id = {item.event_id: item for item in object_events}
        grouped = tuple(
            sorted(unique_by_id.values(), key=lambda item: (item.observed_at, item.event_id))
        )
        if len(grouped) < rules.min_shared_object_events:
            continue

        event_types = tuple(sorted({item.event_type for item in grouped}))
        domains = tuple(sorted({_event_domain(item.event_type) for item in grouped}))
        strong = sum(item.authority_class in _STRONG_AUTHORITIES for item in grouped)
        mean_confidence = round(
            sum(item.confidence for item in grouped) / len(grouped),
            6,
        )
        if len(event_types) < rules.min_distinct_event_types:
            continue
        if len(domains) < rules.min_distinct_domains:
            continue
        if strong < rules.min_strong_authority_events:
            continue
        if mean_confidence < rules.min_mean_confidence:
            continue

        authority_ratio = strong / len(grouped)
        diversity = min(len(domains) / 4.0, 1.0)
        event_density = min(len(grouped) / 6.0, 1.0)
        pressure = telemetry.operational_pressure_score
        score = round(
            min(
                (0.35 * mean_confidence)
                + (0.25 * authority_ratio)
                + (0.20 * diversity)
                + (0.10 * event_density)
                + (0.10 * pressure),
                1.0,
            ),
            6,
        )
        if score >= rules.escalation_score_threshold:
            attention = SituationAttention.ESCALATE
        elif score >= 0.60 or pressure >= rules.pressure_surface_threshold:
            attention = SituationAttention.SURFACE
        else:
            attention = SituationAttention.WATCH

        event_ids = tuple(item.event_id for item in grouped)
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    *(
                        ref
                        for item in grouped
                        for ref in item.evidence_refs
                    ),
                    f"swarm-telemetry://{telemetry.fingerprint}",
                )
            )
        )
        situation_id = "situation://" + _canonical_hash(
            {
                "tenant_id": tenant_id,
                "object_ref": object_ref,
                "event_ids": event_ids,
                "telemetry_fingerprint": telemetry.fingerprint,
                "detected_at": now.isoformat(),
            }
        )
        payload = dict(
            situation_id=situation_id,
            tenant_id=tenant_id,
            object_ref=object_ref,
            detected_at=now,
            event_ids=event_ids,
            event_types=event_types,
            domains=domains,
            strong_authority_event_count=strong,
            mean_confidence=mean_confidence,
            swarm_pressure_score=pressure,
            situation_score=score,
            attention=attention,
            evidence_refs=evidence_refs,
            actionable_attention=True,
        )
        draft = SituationCandidate.model_construct(
            **payload,
            fingerprint="0" * 64,
        )
        fingerprint = _canonical_hash(
            draft.model_dump(mode="json", exclude={"fingerprint"})
        )
        candidates.append(SituationCandidate(**payload, fingerprint=fingerprint))

    return tuple(
        sorted(
            candidates,
            key=lambda item: (-item.situation_score, item.situation_id),
        )
    )


def situation_to_alert_candidate(candidate: SituationCandidate) -> AlertCandidate:
    """Bridge attention into existing alert-fatigue control without sending anything."""

    candidate = SituationCandidate.model_validate(candidate.model_dump(mode="json"))
    return AlertCandidate(
        fingerprint=f"situation:{candidate.tenant_id}:{candidate.object_ref}",
        observed_at=candidate.detected_at,
        priority_score=candidate.situation_score,
        evidence_refs=tuple(
            dict.fromkeys(
                (
                    *candidate.evidence_refs,
                    f"situation-candidate://{candidate.fingerprint}",
                )
            )
        ),
        resolved=False,
    )
