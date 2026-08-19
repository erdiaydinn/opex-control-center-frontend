"""Adapters from existing Jarvis contracts into the real-world timeline.

Adapters keep canonical payloads in their original modules. The timeline receives
only references, object relationships, authority metadata and evidence refs.
Business values, raw media, device transport material and credentials are never
copied into timeline events.
"""

from __future__ import annotations

import hashlib
import unicodedata

from app.ambient_context_intelligence import AmbientSemanticSignal
from app.context_intelligence import ContextSignal
from app.device_world_model import DeviceTrust, DeviceWorldSnapshot
from app.outcome_learning import (
    DecisionLearningRecord,
    GovernedActionReceipt,
    ObservedMetricOutcome,
)
from app.real_world_timeline import (
    RealWorldTimelineEvent,
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineEventLink,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    TimelineRelationKind,
    build_timeline_event,
    validate_timeline_event_integrity,
)
from app.world_model import TruthClass, WorldAssertion


_TRUTH_TO_TIMELINE = {
    TruthClass.GOVERNED_OPERATIONAL: TimelineAuthorityClass.GOVERNED_OPERATIONAL,
    TruthClass.VERIFIED_COMPANY: TimelineAuthorityClass.VERIFIED_COMPANY,
    TruthClass.VERIFIED_LEGAL: TimelineAuthorityClass.VERIFIED_LEGAL,
    TruthClass.VERIFIED_EXTERNAL: TimelineAuthorityClass.VERIFIED_EXTERNAL,
    TruthClass.ANALYTIC_INFERENCE: TimelineAuthorityClass.ANALYTIC_INFERENCE,
}

_DEVICE_TRUST_CONFIDENCE = {
    DeviceTrust.UNTRUSTED: 0.25,
    DeviceTrust.REGISTERED: 0.60,
    DeviceTrust.MANAGED: 0.85,
    DeviceTrust.ATTESTED: 0.98,
}


def _location_ref(value: str) -> str:
    folded = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    normalized = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "location:" + "-".join(normalized.split())


def _stable_token(*values: str) -> str:
    material = "\x1f".join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:24]


def timeline_event_from_world_assertion(assertion: WorldAssertion):
    """Index one canonical WorldAssertion without duplicating its business value."""

    return build_timeline_event(
        event_id=f"timeline:world:{assertion.assertion_id}",
        event_type="eay.company.assertion",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref=assertion.source_ref,
        tenant_id=assertion.tenant_id,
        occurred_at=assertion.observed_at,
        observed_at=assertion.observed_at,
        effective_from=assertion.valid_from,
        effective_until=assertion.valid_to,
        data_ref=f"world-assertion://{assertion.assertion_id}",
        authority_class=_TRUTH_TO_TIMELINE[assertion.truth_class],
        confidence=assertion.confidence,
        object_relations=(
            TimelineObjectRelation(
                object_ref=assertion.entity_id,
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.SUBJECT,
            ),
        ),
        evidence_refs=(assertion.evidence_ref,),
        tags=(f"field:{assertion.field_name}",),
    )


def timeline_event_from_context_signal(*, signal: ContextSignal, tenant_id: str):
    """Index external context as context-only; source quality never becomes company truth."""

    relations = tuple(
        TimelineObjectRelation(
            object_ref=_location_ref(location),
            object_kind=TimelineObjectKind.LOCATION,
            qualifier=TimelineObjectQualifier.AFFECTED,
        )
        for location in signal.locations
        if location.strip()
    )
    return build_timeline_event(
        event_id=f"timeline:context:{signal.signal_id}",
        event_type="eay.external.context",
        event_kind=TimelineEventKind.EXTERNAL_CONTEXT,
        source_ref=signal.source_url,
        tenant_id=tenant_id,
        occurred_at=signal.observed_at,
        observed_at=signal.observed_at,
        effective_from=signal.starts_at,
        effective_until=signal.ends_at,
        data_ref=f"context-signal://{signal.signal_id}",
        authority_class=TimelineAuthorityClass.CONTEXT_ONLY,
        confidence=signal.source_confidence,
        object_relations=relations,
        evidence_refs=(signal.source_url,),
        tags=(
            f"context_kind:{signal.kind.value}",
            *(f"impact:{impact.value}" for impact in signal.expected_impacts),
        ),
    )


def timeline_event_from_ambient_signal(*, signal: AmbientSemanticSignal, tenant_id: str):
    """Index privacy-safe semantic ambient context without retaining transcript/media."""

    relations = []
    if signal.application_ref:
        relations.append(
            TimelineObjectRelation(
                object_ref=signal.application_ref,
                object_kind=TimelineObjectKind.APPLICATION,
                qualifier=TimelineObjectQualifier.CONTEXT,
            )
        )
    else:
        relations.append(
            TimelineObjectRelation(
                object_ref=f"ambient:{signal.modality.value}",
                object_kind=TimelineObjectKind.SOURCE,
                qualifier=TimelineObjectQualifier.SOURCE,
            )
        )

    return build_timeline_event(
        event_id=f"timeline:ambient:{signal.signal_ref}",
        event_type="eay.ambient.observation",
        event_kind=TimelineEventKind.AMBIENT_OBSERVATION,
        source_ref=f"ambient://{signal.modality.value}",
        tenant_id=tenant_id,
        occurred_at=signal.observed_at,
        observed_at=signal.observed_at,
        data_ref=signal.signal_ref,
        authority_class=TimelineAuthorityClass.AMBIENT_UNTRUSTED,
        confidence=signal.confidence,
        object_relations=tuple(relations),
        evidence_refs=(signal.signal_ref,),
        tags=tuple(f"semantic:{tag.casefold()}" for tag in sorted(signal.semantic_tags)),
    )


def timeline_event_from_decision_record(
    decision: DecisionLearningRecord,
) -> RealWorldTimelineEvent:
    """Index a decision record without copying recommendation text or expected values."""

    decision = DecisionLearningRecord.model_validate(decision.model_dump(mode="json"))
    metric_keys = [item.metric_key for item in decision.expected_outcomes]
    if len(metric_keys) != len(set(metric_keys)):
        raise ValueError("timeline_decision_duplicate_expected_metric")

    evidence_refs = list(decision.decision_evidence_refs)
    for expected in decision.expected_outcomes:
        evidence_refs.extend(expected.evidence_refs)

    relations = [
        TimelineObjectRelation(
            object_ref=f"decision:{decision.decision_id}",
            object_kind=TimelineObjectKind.DECISION,
            qualifier=TimelineObjectQualifier.SUBJECT,
        )
    ]
    relations.extend(
        TimelineObjectRelation(
            object_ref=f"metric:{metric_key}",
            object_kind=TimelineObjectKind.WORLD_ENTITY,
            qualifier=TimelineObjectQualifier.AFFECTED,
        )
        for metric_key in metric_keys
    )
    confidence = sum(item.confidence for item in decision.expected_outcomes) / len(
        decision.expected_outcomes
    )

    return build_timeline_event(
        event_id=f"timeline:decision:{decision.decision_id}",
        event_type="eay.decision.recorded",
        event_kind=TimelineEventKind.DECISION,
        source_ref=decision.recommendation_ref,
        tenant_id=decision.tenant_id,
        occurred_at=decision.decided_at,
        observed_at=decision.decided_at,
        data_ref=f"decision-learning://{decision.decision_id}",
        authority_class=TimelineAuthorityClass.DECISION_RECORD,
        confidence=confidence,
        object_relations=tuple(relations),
        evidence_refs=tuple(evidence_refs),
        tags=(f"decision_type:{decision.decision_type.casefold()}",),
    )


def timeline_event_from_verified_action_receipt(
    *,
    action: GovernedActionReceipt,
    decision: DecisionLearningRecord,
) -> RealWorldTimelineEvent:
    """Index only an action whose canonical effect verifier already passed."""

    action = GovernedActionReceipt.model_validate(action.model_dump(mode="json"))
    decision = DecisionLearningRecord.model_validate(decision.model_dump(mode="json"))
    if action.decision_id != decision.decision_id or action.tenant_id != decision.tenant_id:
        raise ValueError("timeline_action_decision_identity_mismatch")
    if action.executed_at < decision.decided_at:
        raise ValueError("timeline_action_precedes_decision")
    if not action.effect_verified:
        raise ValueError("timeline_action_requires_verified_effect")

    evidence_refs = [*action.evidence_refs]
    if action.approval_ref is not None:
        evidence_refs.append(action.approval_ref)

    return build_timeline_event(
        event_id=f"timeline:action:{action.action_id}",
        event_type="eay.action.verified",
        event_kind=TimelineEventKind.ACTION,
        source_ref=action.capability_ref,
        tenant_id=action.tenant_id,
        occurred_at=action.executed_at,
        observed_at=action.executed_at,
        data_ref=f"governed-action://{action.action_id}",
        authority_class=TimelineAuthorityClass.VERIFIED_ACTION,
        confidence=1.0,
        object_relations=(
            TimelineObjectRelation(
                object_ref=f"action:{action.action_id}",
                object_kind=TimelineObjectKind.ACTION,
                qualifier=TimelineObjectQualifier.SUBJECT,
            ),
            TimelineObjectRelation(
                object_ref=f"decision:{decision.decision_id}",
                object_kind=TimelineObjectKind.DECISION,
                qualifier=TimelineObjectQualifier.CONTEXT,
            ),
        ),
        evidence_refs=tuple(evidence_refs),
        tags=("effect:verified",),
    )


def timeline_event_from_observed_outcome(
    *,
    decision: DecisionLearningRecord,
    outcome: ObservedMetricOutcome,
    action: GovernedActionReceipt | None = None,
) -> RealWorldTimelineEvent:
    """Index a governed metric observation without copying its numeric value."""

    decision = DecisionLearningRecord.model_validate(decision.model_dump(mode="json"))
    outcome = ObservedMetricOutcome.model_validate(outcome.model_dump(mode="json"))
    expected = {item.metric_key: item for item in decision.expected_outcomes}
    if len(expected) != len(decision.expected_outcomes):
        raise ValueError("timeline_decision_duplicate_expected_metric")
    expected_metric = expected.get(outcome.metric_key)
    if expected_metric is None:
        raise ValueError("timeline_outcome_metric_not_declared_by_decision")
    if outcome.unit != expected_metric.unit:
        raise ValueError("timeline_outcome_metric_unit_mismatch")
    if outcome.observed_at < decision.decided_at:
        raise ValueError("timeline_outcome_precedes_decision")

    relations = [
        TimelineObjectRelation(
            object_ref=f"metric:{outcome.metric_key}",
            object_kind=TimelineObjectKind.WORLD_ENTITY,
            qualifier=TimelineObjectQualifier.SUBJECT,
        ),
        TimelineObjectRelation(
            object_ref=f"decision:{decision.decision_id}",
            object_kind=TimelineObjectKind.DECISION,
            qualifier=TimelineObjectQualifier.CONTEXT,
        ),
    ]
    if action is not None:
        action = GovernedActionReceipt.model_validate(action.model_dump(mode="json"))
        if action.decision_id != decision.decision_id or action.tenant_id != decision.tenant_id:
            raise ValueError("timeline_outcome_action_identity_mismatch")
        if not action.effect_verified:
            raise ValueError("timeline_outcome_requires_verified_action_when_action_is_bound")
        if outcome.observed_at < action.executed_at:
            raise ValueError("timeline_outcome_precedes_verified_action")
        relations.append(
            TimelineObjectRelation(
                object_ref=f"action:{action.action_id}",
                object_kind=TimelineObjectKind.ACTION,
                qualifier=TimelineObjectQualifier.CONTEXT,
            )
        )

    token = _stable_token(
        decision.decision_id,
        outcome.metric_key,
        outcome.observed_at.isoformat(),
        outcome.governed_truth_ref,
    )
    return build_timeline_event(
        event_id=f"timeline:outcome:{token}",
        event_type="eay.outcome.observed",
        event_kind=TimelineEventKind.OUTCOME,
        source_ref=outcome.governed_truth_ref,
        tenant_id=decision.tenant_id,
        occurred_at=outcome.observed_at,
        observed_at=outcome.observed_at,
        data_ref=f"outcome-learning://{decision.decision_id}/{token}",
        authority_class=TimelineAuthorityClass.VERIFIED_OUTCOME,
        confidence=1.0,
        object_relations=tuple(relations),
        evidence_refs=(*outcome.evidence_refs, outcome.governed_truth_ref),
        tags=(f"metric:{outcome.metric_key}", f"unit:{outcome.unit}"),
    )


def timeline_links_for_decision_action_outcomes(
    *,
    decision_event: RealWorldTimelineEvent,
    action_event: RealWorldTimelineEvent,
    outcome_events: tuple[RealWorldTimelineEvent, ...],
) -> tuple[TimelineEventLink, ...]:
    """Build non-causal graph links across an already verified execution chain."""

    decision_event = validate_timeline_event_integrity(decision_event)
    action_event = validate_timeline_event_integrity(action_event)
    outcome_events = tuple(validate_timeline_event_integrity(item) for item in outcome_events)
    tenant_id = decision_event.tenant_id
    if action_event.tenant_id != tenant_id or any(item.tenant_id != tenant_id for item in outcome_events):
        raise ValueError("timeline_execution_chain_cross_tenant_forbidden")
    if decision_event.event_kind is not TimelineEventKind.DECISION:
        raise ValueError("timeline_execution_chain_requires_decision_event")
    if action_event.event_kind is not TimelineEventKind.ACTION:
        raise ValueError("timeline_execution_chain_requires_action_event")
    if any(item.event_kind is not TimelineEventKind.OUTCOME for item in outcome_events):
        raise ValueError("timeline_execution_chain_requires_outcome_events")
    if action_event.occurred_at < decision_event.occurred_at:
        raise ValueError("timeline_execution_chain_action_precedes_decision")
    if any(item.occurred_at < action_event.occurred_at for item in outcome_events):
        raise ValueError("timeline_execution_chain_outcome_precedes_action")

    links = [
        TimelineEventLink(
            tenant_id=tenant_id,
            source_event_id=action_event.event_id,
            relation=TimelineRelationKind.ACTION_EXECUTES_DECISION,
            target_event_id=decision_event.event_id,
            evidence_refs=tuple(
                dict.fromkeys((*decision_event.evidence_refs, *action_event.evidence_refs))
            ),
            confidence=min(decision_event.confidence, action_event.confidence),
        )
    ]
    links.extend(
        TimelineEventLink(
            tenant_id=tenant_id,
            source_event_id=action_event.event_id,
            relation=TimelineRelationKind.OUTCOME_FOLLOWS_ACTION,
            target_event_id=outcome.event_id,
            evidence_refs=tuple(
                dict.fromkeys((*action_event.evidence_refs, *outcome.evidence_refs))
            ),
            confidence=min(action_event.confidence, outcome.confidence),
        )
        for outcome in outcome_events
    )
    return tuple(links)


def timeline_events_from_device_world_snapshot(
    snapshot: DeviceWorldSnapshot,
) -> tuple[RealWorldTimelineEvent, ...]:
    """Index privacy-safe device observations without transport or credential material."""

    snapshot = DeviceWorldSnapshot.model_validate(snapshot.model_dump(mode="json"))
    events: list[RealWorldTimelineEvent] = []
    for device in sorted(snapshot.devices, key=lambda item: item.device_ref):
        if device.observed_at > snapshot.observed_at:
            raise ValueError("timeline_device_snapshot_precedes_device_observation")

        evidence_refs = list(snapshot.source_evidence_refs)
        if device.identity_evidence_ref is not None:
            evidence_refs.append(device.identity_evidence_ref)
        source_ref = device.identity_evidence_ref or snapshot.source_evidence_refs[0]
        relations = [
            TimelineObjectRelation(
                object_ref=device.device_ref,
                object_kind=TimelineObjectKind.DEVICE,
                qualifier=TimelineObjectQualifier.SUBJECT,
            )
        ]
        if device.room_ref is not None:
            relations.append(
                TimelineObjectRelation(
                    object_ref=device.room_ref,
                    object_kind=TimelineObjectKind.LOCATION,
                    qualifier=TimelineObjectQualifier.LOCATION,
                )
            )

        token = _stable_token(snapshot.tenant_ref, device.device_ref, snapshot.observed_at.isoformat())
        events.append(
            build_timeline_event(
                event_id=f"timeline:device:{token}",
                event_type="eay.device.observation",
                event_kind=TimelineEventKind.DEVICE_OBSERVATION,
                source_ref=source_ref,
                tenant_id=snapshot.tenant_ref,
                occurred_at=device.observed_at,
                observed_at=snapshot.observed_at,
                data_ref=f"device-world://{device.device_ref}/{token}",
                authority_class=TimelineAuthorityClass.DEVICE_OBSERVATION,
                confidence=_DEVICE_TRUST_CONFIDENCE[device.trust],
                object_relations=tuple(relations),
                evidence_refs=tuple(evidence_refs),
                tags=(
                    f"device_class:{device.device_class.value}",
                    f"trust:{device.trust.value}",
                    f"online:{str(device.online).lower()}",
                    *(f"capability:{item.value}" for item in sorted(device.capabilities, key=lambda item: item.value)),
                ),
            )
        )
    return tuple(events)
