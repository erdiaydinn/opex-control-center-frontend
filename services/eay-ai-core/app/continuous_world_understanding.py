"""Continuous, evidence-bound world understanding for Jarvis.

Jarvis already has a temporal Company World, an object-centric real-world
timeline, situation detection and an autonomous investigator. This module
connects their *freshness* semantics without becoming another truth source or
background executor.

Each invocation answers a narrow but critical question: is the world state that
a prior belief or decision depended on still sufficiently fresh and stable to
reuse? It detects source silence, authority downgrades, material snapshot drift,
new contradictions and rapid change, then invalidates stale beliefs and emits a
read-only reinvestigation directive. It never promotes observations to Company
World truth, never auto-runs research, and never grants business authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .autonomous_investigator import (
    AutonomousInvestigationReport,
    InvestigatorDisposition,
)
from .real_world_timeline import (
    RealWorldTimelineEvent,
    TimelineAuthorityClass,
)
from .world_model import ResolvedField, WorldSnapshot

CONTINUOUS_WORLD_UNDERSTANDING_CONTRACT = "eay-continuous-world-understanding-v1"

_STRONG_LIVE_AUTHORITIES = frozenset(
    {
        TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        TimelineAuthorityClass.VERIFIED_COMPANY,
        TimelineAuthorityClass.VERIFIED_LEGAL,
        TimelineAuthorityClass.VERIFIED_EXTERNAL,
        TimelineAuthorityClass.VERIFIED_ACTION,
        TimelineAuthorityClass.VERIFIED_OUTCOME,
    }
)


class WorldWatchDisposition(str, Enum):
    STABLE = "stable"
    REFRESH_REQUIRED = "refresh_required"
    REINVESTIGATE = "reinvestigate"


class SourceFreshnessExpectation(BaseModel):
    source_key: str = Field(min_length=1)
    maximum_silence_seconds: int = Field(ge=1, le=31_536_000)
    required_for_live_truth: bool = True
    accepted_authority_classes: tuple[TimelineAuthorityClass, ...] = Field(
        default_factory=lambda: tuple(
            sorted(_STRONG_LIVE_AUTHORITIES, key=lambda item: item.value)
        )
    )

    @model_validator(mode="after")
    def accepted_authorities_are_unique(self) -> "SourceFreshnessExpectation":
        if not self.accepted_authority_classes:
            raise ValueError("world_watch_source_authorities_required")
        if len(self.accepted_authority_classes) != len(
            set(self.accepted_authority_classes)
        ):
            raise ValueError("world_watch_source_authorities_must_be_unique")
        return self


class SourcePulse(BaseModel):
    source_key: str = Field(min_length=1)
    observed_at: datetime
    authority_class: TimelineAuthorityClass
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def observed_time_is_aware(self) -> "SourcePulse":
        _require_aware(self.observed_at, "world_watch_source_pulse_requires_timezone")
        return self


class SourceFreshnessState(BaseModel):
    source_key: str
    observed_at: datetime | None = None
    age_seconds: float | None = Field(default=None, ge=0.0)
    required_for_live_truth: bool
    fresh: bool
    authority_accepted: bool
    evidence_ref: str | None = None
    blocker: str | None = None


class WorldFieldDelta(BaseModel):
    field_key: str = Field(min_length=1)
    previous_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    current_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    change_kind: str = Field(pattern=r"^(added|removed|changed)$")


class WorldChangeSet(BaseModel):
    previous_world_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    current_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_deltas: tuple[WorldFieldDelta, ...]
    introduced_contradiction_keys: tuple[str, ...]
    resolved_contradiction_keys: tuple[str, ...]
    material_change_count: int = Field(ge=0)
    change_ratio: float = Field(ge=0.0, le=1.0)
    changes_per_hour: float = Field(ge=0.0)


class ContinuousWorldPolicy(BaseModel):
    maximum_world_snapshot_age_seconds: int = Field(default=900, ge=1, le=86_400)
    material_change_ratio_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    rapid_change_per_hour_threshold: float = Field(
        default=6.0,
        ge=0.0,
        le=10_000.0,
    )
    reopen_when_prior_world_lineage_is_unknown: bool = True


class ReinvestigationDirective(BaseModel):
    contract: str = CONTINUOUS_WORLD_UNDERSTANDING_CONTRACT
    tenant_id: str
    company_id: str
    previous_investigation_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    current_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...] = Field(min_length=1)
    required_source_keys: tuple[str, ...] = ()
    read_only: bool = True
    automatic_research_execution_allowed: bool = False
    firm_company_claim_authorized: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def directive_is_advisory(self) -> "ReinvestigationDirective":
        if not self.read_only:
            raise ValueError("world_watch_reinvestigation_must_be_read_only")
        if (
            self.automatic_research_execution_allowed
            or self.firm_company_claim_authorized
            or self.execution_authority_granted
        ):
            raise ValueError("world_watch_reinvestigation_never_grants_authority")
        return self


class ContinuousWorldAssessment(BaseModel):
    contract: str = CONTINUOUS_WORLD_UNDERSTANDING_CONTRACT
    tenant_id: str
    company_id: str
    as_of: datetime
    current_world_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_change: WorldChangeSet
    source_states: tuple[SourceFreshnessState, ...]
    timeline_event_count: int = Field(ge=0)
    strong_authority_event_count: int = Field(ge=0)
    distinct_event_domain_count: int = Field(ge=0)
    disposition: WorldWatchDisposition
    prior_belief_invalidated: bool
    confidence_decay_multiplier: float = Field(ge=0.25, le=1.0)
    blockers: tuple[str, ...]
    directive: ReinvestigationDirective | None = None
    authoritative_truth_surface: bool = False
    automatic_research_execution_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def assessment_is_integral_and_non_authoritative(
        self,
    ) -> "ContinuousWorldAssessment":
        _require_aware(self.as_of, "world_watch_assessment_requires_timezone")
        if (
            self.authoritative_truth_surface
            or self.automatic_research_execution_allowed
            or self.execution_authority_granted
        ):
            raise ValueError("continuous_world_understanding_never_grants_authority")
        if self.disposition is WorldWatchDisposition.STABLE and (
            self.blockers or self.directive is not None
        ):
            raise ValueError("world_watch_stable_cannot_have_blockers_or_directive")
        if (
            self.disposition is WorldWatchDisposition.REINVESTIGATE
            and self.directive is None
        ):
            raise ValueError("world_watch_reinvestigation_requires_directive")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("continuous_world_understanding_fingerprint_mismatch")
        return self


def assess_continuous_world(
    *,
    tenant_id: str,
    company_id: str,
    now: datetime,
    current_world: WorldSnapshot,
    previous_world: WorldSnapshot | None = None,
    timeline_events: tuple[RealWorldTimelineEvent, ...] = (),
    source_expectations: tuple[SourceFreshnessExpectation, ...] = (),
    source_pulses: tuple[SourcePulse, ...] = (),
    prior_investigation: AutonomousInvestigationReport | None = None,
    policy: ContinuousWorldPolicy | None = None,
) -> ContinuousWorldAssessment:
    """Assess whether live context is fresh enough to reuse prior beliefs."""

    _require_aware(now, "world_watch_now_requires_timezone")
    rules = policy or ContinuousWorldPolicy()
    current = WorldSnapshot.model_validate(current_world.model_dump(mode="json"))
    if current.tenant_id != tenant_id:
        raise ValueError("world_watch_current_world_tenant_mismatch")
    if current.as_of > now:
        raise ValueError("world_watch_current_world_from_future")

    previous: WorldSnapshot | None = None
    if previous_world is not None:
        previous = WorldSnapshot.model_validate(previous_world.model_dump(mode="json"))
        if previous.tenant_id != tenant_id:
            raise ValueError("world_watch_previous_world_tenant_mismatch")
        if previous.as_of > current.as_of:
            raise ValueError("world_watch_world_time_regression")

    prior: AutonomousInvestigationReport | None = None
    if prior_investigation is not None:
        if prior_investigation.tenant_id != tenant_id:
            raise ValueError("world_watch_prior_investigation_tenant_mismatch")
        if prior_investigation.company_id != company_id:
            raise ValueError("world_watch_prior_investigation_company_mismatch")
        prior = AutonomousInvestigationReport.model_validate(
            prior_investigation.model_dump(mode="json")
        )

    expectations = {item.source_key: item for item in source_expectations}
    if len(expectations) != len(source_expectations):
        raise ValueError("world_watch_duplicate_source_expectation")
    pulses = {item.source_key: item for item in source_pulses}
    if len(pulses) != len(source_pulses):
        raise ValueError("world_watch_duplicate_source_pulse")
    if set(pulses) - set(expectations):
        raise ValueError("world_watch_unexpected_source_pulse")

    source_states: list[SourceFreshnessState] = []
    blockers: list[str] = []
    stale_required_sources: list[str] = []
    for source_key, expectation in sorted(expectations.items()):
        pulse = pulses.get(source_key)
        if pulse is None:
            blocker = (
                "world_watch_required_source_missing"
                if expectation.required_for_live_truth
                else "world_watch_optional_source_missing"
            )
            if expectation.required_for_live_truth:
                stale_required_sources.append(source_key)
                blockers.append(f"{blocker}:{source_key}")
            source_states.append(
                SourceFreshnessState(
                    source_key=source_key,
                    required_for_live_truth=expectation.required_for_live_truth,
                    fresh=False,
                    authority_accepted=False,
                    blocker=blocker,
                )
            )
            continue
        if pulse.observed_at > now:
            raise ValueError("world_watch_source_pulse_from_future")
        age_seconds = max(0.0, (now - pulse.observed_at).total_seconds())
        authority_accepted = pulse.authority_class in set(
            expectation.accepted_authority_classes
        )
        fresh_by_time = age_seconds <= expectation.maximum_silence_seconds
        fresh = fresh_by_time and authority_accepted
        blocker: str | None = None
        if not authority_accepted:
            blocker = "world_watch_source_authority_insufficient"
        elif not fresh_by_time:
            blocker = "world_watch_source_silent"
        if blocker and expectation.required_for_live_truth:
            stale_required_sources.append(source_key)
            blockers.append(f"{blocker}:{source_key}")
        source_states.append(
            SourceFreshnessState(
                source_key=source_key,
                observed_at=pulse.observed_at,
                age_seconds=round(age_seconds, 6),
                required_for_live_truth=expectation.required_for_live_truth,
                fresh=fresh,
                authority_accepted=authority_accepted,
                evidence_ref=pulse.evidence_ref,
                blocker=blocker,
            )
        )

    validated_events = _validated_timeline_events(
        events=timeline_events,
        tenant_id=tenant_id,
        now=now,
    )
    strong_count = sum(
        item.authority_class in _STRONG_LIVE_AUTHORITIES
        for item in validated_events
    )
    event_domains = {_event_domain(item.event_type) for item in validated_events}

    world_change = _world_change(previous=previous, current=current)
    world_age_seconds = (now - current.as_of).total_seconds()
    if world_age_seconds > rules.maximum_world_snapshot_age_seconds:
        blockers.append("world_watch_company_world_stale")
    if current.blocked_field_keys:
        blockers.append("world_watch_company_world_contradicted")
    if (
        world_change.material_change_count
        and world_change.change_ratio >= rules.material_change_ratio_threshold
    ):
        blockers.append("world_watch_material_world_change")
    if (
        world_change.material_change_count
        and world_change.changes_per_hour >= rules.rapid_change_per_hour_threshold
    ):
        blockers.append("world_watch_rapid_world_change")

    prior_invalidated = False
    if prior is not None and prior.world_snapshot_fingerprint != current.fingerprint:
        lineage_matches = (
            previous is not None
            and previous.fingerprint == prior.world_snapshot_fingerprint
        )
        semantic_change = world_change.material_change_count > 0
        if lineage_matches and semantic_change:
            prior_invalidated = True
            blockers.append("world_watch_prior_investigation_semantic_world_changed")
        elif not lineage_matches and rules.reopen_when_prior_world_lineage_is_unknown:
            prior_invalidated = True
            blockers.append("world_watch_prior_world_lineage_unknown")
    if prior is not None and current.blocked_field_keys:
        prior_invalidated = True
    if prior is not None and stale_required_sources:
        prior_invalidated = True

    blockers = list(dict.fromkeys(blockers))
    prior_was_decision_ready = (
        prior is not None
        and prior.disposition is InvestigatorDisposition.DECISION_READY
    )
    requires_reinvestigation = (
        prior_invalidated and prior_was_decision_ready
    ) or bool(current.blocked_field_keys)

    if requires_reinvestigation:
        disposition = WorldWatchDisposition.REINVESTIGATE
    elif blockers:
        disposition = WorldWatchDisposition.REFRESH_REQUIRED
    else:
        disposition = WorldWatchDisposition.STABLE

    confidence_multiplier = 1.0
    if world_age_seconds > rules.maximum_world_snapshot_age_seconds:
        confidence_multiplier = min(confidence_multiplier, 0.50)
    if stale_required_sources:
        confidence_multiplier = min(confidence_multiplier, 0.60)
    if current.blocked_field_keys:
        confidence_multiplier = min(confidence_multiplier, 0.40)
    if "world_watch_material_world_change" in blockers:
        confidence_multiplier = min(confidence_multiplier, 0.75)
    if "world_watch_rapid_world_change" in blockers:
        confidence_multiplier = min(confidence_multiplier, 0.65)
    if prior_invalidated:
        confidence_multiplier = min(confidence_multiplier, 0.60)

    directive: ReinvestigationDirective | None = None
    if disposition is WorldWatchDisposition.REINVESTIGATE:
        directive = ReinvestigationDirective(
            tenant_id=tenant_id,
            company_id=company_id,
            previous_investigation_fingerprint=(
                prior.fingerprint if prior is not None else None
            ),
            current_world_fingerprint=current.fingerprint,
            reason_codes=tuple(
                blockers or ("world_watch_company_world_contradicted",)
            ),
            required_source_keys=tuple(sorted(set(stale_required_sources))),
        )

    draft = {
        "contract": CONTINUOUS_WORLD_UNDERSTANDING_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "current_world_fingerprint": current.fingerprint,
        "world_change": world_change.model_dump(mode="json"),
        "source_states": [item.model_dump(mode="json") for item in source_states],
        "timeline_event_count": len(validated_events),
        "strong_authority_event_count": strong_count,
        "distinct_event_domain_count": len(event_domains),
        "disposition": disposition.value,
        "prior_belief_invalidated": prior_invalidated,
        "confidence_decay_multiplier": round(confidence_multiplier, 6),
        "blockers": blockers,
        "directive": (
            directive.model_dump(mode="json") if directive is not None else None
        ),
        "authoritative_truth_surface": False,
        "automatic_research_execution_allowed": False,
        "execution_authority_granted": False,
    }
    return ContinuousWorldAssessment.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _validated_timeline_events(
    *,
    events: tuple[RealWorldTimelineEvent, ...],
    tenant_id: str,
    now: datetime,
) -> tuple[RealWorldTimelineEvent, ...]:
    by_id: dict[str, RealWorldTimelineEvent] = {}
    for raw in events:
        event = RealWorldTimelineEvent.model_validate(raw.model_dump(mode="json"))
        if event.tenant_id != tenant_id:
            raise ValueError("world_watch_cross_tenant_timeline_event")
        if event.observed_at > now:
            raise ValueError("world_watch_timeline_event_from_future")
        existing = by_id.get(event.event_id)
        if existing is not None and existing.fingerprint != event.fingerprint:
            raise ValueError("world_watch_timeline_event_id_conflict")
        by_id[event.event_id] = event
    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (item.observed_at, item.event_id),
        )
    )


def _world_change(
    *,
    previous: WorldSnapshot | None,
    current: WorldSnapshot,
) -> WorldChangeSet:
    if previous is None:
        return WorldChangeSet(
            previous_world_fingerprint=None,
            current_world_fingerprint=current.fingerprint,
            field_deltas=(),
            introduced_contradiction_keys=tuple(sorted(current.blocked_field_keys)),
            resolved_contradiction_keys=(),
            material_change_count=len(current.blocked_field_keys),
            change_ratio=0.0,
            changes_per_hour=0.0,
        )

    previous_fields = {_field_key(item): item for item in previous.fields}
    current_fields = {_field_key(item): item for item in current.fields}
    deltas: list[WorldFieldDelta] = []
    for field_key in sorted(set(previous_fields) | set(current_fields)):
        old = previous_fields.get(field_key)
        new = current_fields.get(field_key)
        if old is None:
            deltas.append(
                WorldFieldDelta(
                    field_key=field_key,
                    current_digest=_field_digest(new),
                    change_kind="added",
                )
            )
        elif new is None:
            deltas.append(
                WorldFieldDelta(
                    field_key=field_key,
                    previous_digest=_field_digest(old),
                    change_kind="removed",
                )
            )
        else:
            old_digest = _field_digest(old)
            new_digest = _field_digest(new)
            if old_digest != new_digest:
                deltas.append(
                    WorldFieldDelta(
                        field_key=field_key,
                        previous_digest=old_digest,
                        current_digest=new_digest,
                        change_kind="changed",
                    )
                )

    previous_blocked = set(previous.blocked_field_keys)
    current_blocked = set(current.blocked_field_keys)
    introduced = tuple(sorted(current_blocked - previous_blocked))
    resolved = tuple(sorted(previous_blocked - current_blocked))
    material_count = len(deltas) + len(introduced) + len(resolved)
    denominator = max(len(previous_fields), len(current_fields), 1)
    ratio = min(material_count / denominator, 1.0)
    elapsed_hours = max(
        (current.as_of - previous.as_of).total_seconds() / 3600.0,
        0.0,
    )
    velocity = material_count / elapsed_hours if elapsed_hours > 0 else 0.0
    return WorldChangeSet(
        previous_world_fingerprint=previous.fingerprint,
        current_world_fingerprint=current.fingerprint,
        field_deltas=tuple(deltas),
        introduced_contradiction_keys=introduced,
        resolved_contradiction_keys=resolved,
        material_change_count=material_count,
        change_ratio=round(ratio, 6),
        changes_per_hour=round(velocity, 6),
    )


def _field_key(field: ResolvedField) -> str:
    return f"{field.entity_id}:{field.field_name}"


def _field_digest(field: ResolvedField) -> str:
    return _fingerprint(
        {
            "entity_id": field.entity_id,
            "field_name": field.field_name,
            "value": field.value,
            "truth_class": field.truth_class.value,
            "confidence": field.confidence,
        }
    )


def _event_domain(event_type: str) -> str:
    parts = event_type.split(".")
    return parts[2] if len(parts) >= 3 else parts[-1]


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
