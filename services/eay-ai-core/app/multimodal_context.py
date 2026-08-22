"""Temporal multimodal context and referent grounding for Jarvis.

Screen pixels, webpages, camera frames, documents, sensors and transcribed
ambient audio are observations, not instructions. Only an explicit user
utterance or a separately verified system event may define intent. This
prevents prompt-injection text or sensor payloads from silently changing a
mission. Raw media is referenced by provenance IDs rather than embedded here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

MULTIMODAL_CONTEXT_CONTRACT = "eay-multimodal-context-v1"


class ObservationModality(str, Enum):
    USER_UTTERANCE = "user_utterance"
    SCREEN = "screen"
    CAMERA = "camera"
    AUDIO = "audio"
    DOCUMENT = "document"
    SENSOR = "sensor"
    SYSTEM_EVENT = "system_event"


class ObservationTrust(str, Enum):
    EXPLICIT_USER_INTENT = "explicit_user_intent"
    VERIFIED_SYSTEM = "verified_system"
    UNTRUSTED_CONTENT = "untrusted_content"
    SENSOR_EVIDENCE = "sensor_evidence"


class FocusCandidate(BaseModel):
    entity_ref: str = Field(min_length=1)
    salience: float = Field(ge=0.0, le=1.0)
    evidence_ref: str = Field(min_length=1)


class MultimodalObservation(BaseModel):
    observation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    modality: ObservationModality
    trust: ObservationTrust
    observed_at: datetime
    duration_ms: int = Field(default=0, ge=0)
    source_ref: str = Field(min_length=1)
    content_ref: str = Field(min_length=1)
    application_id: str | None = None
    window_ref: str | None = None
    location_ref: str | None = None
    semantic_labels: tuple[str, ...] = ()
    focus_candidates: tuple[FocusCandidate, ...] = ()
    contains_instruction_like_content: bool = False

    @model_validator(mode="after")
    def modality_trust_boundary(self) -> "MultimodalObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("multimodal_observation_requires_timezone")
        if self.modality is ObservationModality.USER_UTTERANCE:
            if self.trust is not ObservationTrust.EXPLICIT_USER_INTENT:
                raise ValueError("user_utterance_requires_explicit_user_intent_trust")
        elif self.modality is ObservationModality.SYSTEM_EVENT:
            if self.trust is not ObservationTrust.VERIFIED_SYSTEM:
                raise ValueError("system_event_requires_verified_system_trust")
        elif self.modality is ObservationModality.SENSOR:
            if self.trust not in {ObservationTrust.SENSOR_EVIDENCE, ObservationTrust.VERIFIED_SYSTEM}:
                raise ValueError("sensor_requires_evidence_trust")
        elif self.trust in {ObservationTrust.EXPLICIT_USER_INTENT, ObservationTrust.VERIFIED_SYSTEM}:
            raise ValueError("observed_content_cannot_be_promoted_to_instruction_trust")
        return self

    @property
    def may_define_intent(self) -> bool:
        return (
            self.modality is ObservationModality.USER_UTTERANCE
            and self.trust is ObservationTrust.EXPLICIT_USER_INTENT
        ) or (
            self.modality is ObservationModality.SYSTEM_EVENT
            and self.trust is ObservationTrust.VERIFIED_SYSTEM
        )


class SessionSlice(BaseModel):
    contract: str = MULTIMODAL_CONTEXT_CONTRACT
    session_id: str
    tenant_id: str
    as_of: datetime
    observations: tuple[MultimodalObservation, ...]
    intent_observation_ids: tuple[str, ...]
    untrusted_instruction_observation_ids: tuple[str, ...]


class ReferentResolution(BaseModel):
    contract: str = MULTIMODAL_CONTEXT_CONTRACT
    phrase: str
    resolved_entity_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguous: bool = False
    candidate_entity_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ambiguous_reference_cannot_resolve(self) -> "ReferentResolution":
        if self.ambiguous and self.resolved_entity_ref is not None:
            raise ValueError("ambiguous_referent_cannot_be_resolved")
        return self


def slice_session(
    observations: list[MultimodalObservation],
    *,
    session_id: str,
    tenant_id: str,
    as_of: datetime,
    lookback: timedelta = timedelta(minutes=5),
    maximum_observations: int = 100,
) -> SessionSlice:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("multimodal_session_as_of_requires_timezone")
    if lookback <= timedelta(0):
        raise ValueError("multimodal_session_lookback_must_be_positive")
    if maximum_observations < 1:
        raise ValueError("multimodal_session_maximum_observations_invalid")

    start = as_of - lookback
    selected = [
        item
        for item in observations
        if item.session_id == session_id
        and item.tenant_id == tenant_id
        and start <= item.observed_at <= as_of
    ]
    selected.sort(key=lambda item: (item.observed_at, item.observation_id))
    selected = selected[-maximum_observations:]
    return SessionSlice(
        session_id=session_id,
        tenant_id=tenant_id,
        as_of=as_of,
        observations=tuple(selected),
        intent_observation_ids=tuple(item.observation_id for item in selected if item.may_define_intent),
        untrusted_instruction_observation_ids=tuple(
            item.observation_id
            for item in selected
            if item.contains_instruction_like_content and not item.may_define_intent
        ),
    )


def resolve_recent_referent(
    phrase: str,
    session: SessionSlice,
    *,
    minimum_salience: float = 0.55,
    ambiguity_margin: float = 0.08,
) -> ReferentResolution:
    if not phrase.strip():
        raise ValueError("referent_phrase_required")
    candidates: dict[str, tuple[float, str]] = {}
    for recency_index, observation in enumerate(reversed(session.observations)):
        recency_weight = max(0.70, 1.0 - recency_index * 0.03)
        for candidate in observation.focus_candidates:
            score = candidate.salience * recency_weight
            previous = candidates.get(candidate.entity_ref)
            if previous is None or score > previous[0]:
                candidates[candidate.entity_ref] = (score, candidate.evidence_ref)

    ranked = sorted(
        ((entity_ref, score, evidence_ref) for entity_ref, (score, evidence_ref) in candidates.items()),
        key=lambda item: (-item[1], item[0]),
    )
    if not ranked or ranked[0][1] < minimum_salience:
        return ReferentResolution(
            phrase=phrase,
            confidence=ranked[0][1] if ranked else 0.0,
            candidate_entity_refs=tuple(item[0] for item in ranked[:5]),
            evidence_refs=tuple(item[2] for item in ranked[:5]),
            blockers=("referent_not_grounded_in_recent_context",),
        )

    best = ranked[0]
    if len(ranked) > 1 and best[1] - ranked[1][1] < ambiguity_margin:
        return ReferentResolution(
            phrase=phrase,
            confidence=best[1],
            ambiguous=True,
            candidate_entity_refs=tuple(item[0] for item in ranked[:5]),
            evidence_refs=tuple(item[2] for item in ranked[:5]),
            blockers=("referent_resolution_ambiguous",),
        )

    return ReferentResolution(
        phrase=phrase,
        resolved_entity_ref=best[0],
        confidence=best[1],
        candidate_entity_refs=tuple(item[0] for item in ranked[:5]),
        evidence_refs=(best[2],),
    )
