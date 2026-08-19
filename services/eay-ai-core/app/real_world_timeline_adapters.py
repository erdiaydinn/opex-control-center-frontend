"""Adapters from existing Jarvis perception/truth contracts into the real-world timeline.

Adapters keep canonical payloads in their original modules. The timeline receives
only references, object relationships, authority metadata and evidence refs.
"""

from __future__ import annotations

import unicodedata

from app.ambient_context_intelligence import AmbientSemanticSignal
from app.context_intelligence import ContextSignal
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.world_model import TruthClass, WorldAssertion


_TRUTH_TO_TIMELINE = {
    TruthClass.GOVERNED_OPERATIONAL: TimelineAuthorityClass.GOVERNED_OPERATIONAL,
    TruthClass.VERIFIED_COMPANY: TimelineAuthorityClass.VERIFIED_COMPANY,
    TruthClass.VERIFIED_LEGAL: TimelineAuthorityClass.VERIFIED_LEGAL,
    TruthClass.VERIFIED_EXTERNAL: TimelineAuthorityClass.VERIFIED_EXTERNAL,
    TruthClass.ANALYTIC_INFERENCE: TimelineAuthorityClass.ANALYTIC_INFERENCE,
}


def _location_ref(value: str) -> str:
    folded = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    normalized = "".join(char for char in decomposed if not unicodedata.combining(char))
    return "location:" + "-".join(normalized.split())


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
