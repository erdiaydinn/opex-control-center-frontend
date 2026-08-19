"""Evidence-bound causal investigation view over the Jarvis real-world timeline.

This module helps Jarvis compare competing explanations for an observed event.
It ranks evidence bridges using time, shared objects, reviewed timeline links and
source authority. It deliberately cannot prove causality or authorize action.
Counterfactual evidence is surfaced as evidence only; causal attribution remains
owned by the canonical outcome-learning/effect-verification boundaries.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.real_world_timeline import (
    RealWorldTimelineEvent,
    RealWorldTimelineSnapshot,
    TimelineAuthorityClass,
    TimelineEventLink,
)

TIMELINE_CAUSAL_INVESTIGATION_CONTRACT = "eay-timeline-causal-investigation-v1"


class HypothesisDisposition(str, Enum):
    PLAUSIBLE = "plausible"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


_AUTHORITY_WEIGHT = {
    TimelineAuthorityClass.GOVERNED_OPERATIONAL: 1.00,
    TimelineAuthorityClass.VERIFIED_COMPANY: 0.95,
    TimelineAuthorityClass.VERIFIED_LEGAL: 0.90,
    TimelineAuthorityClass.VERIFIED_EXTERNAL: 0.90,
    TimelineAuthorityClass.ANALYTIC_INFERENCE: 0.40,
    TimelineAuthorityClass.CONTEXT_ONLY: 0.60,
    TimelineAuthorityClass.AMBIENT_UNTRUSTED: 0.25,
    TimelineAuthorityClass.DEVICE_OBSERVATION: 0.50,
    TimelineAuthorityClass.DECISION_RECORD: 0.50,
    TimelineAuthorityClass.VERIFIED_ACTION: 1.00,
    TimelineAuthorityClass.VERIFIED_OUTCOME: 1.00,
}

_FORBIDDEN_REFERENCE_MARKERS = (
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


class CausalHypothesisInput(BaseModel):
    hypothesis_id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=500)
    candidate_event_ids: tuple[str, ...] = Field(min_length=1)
    counterfactual_evidence_ref: str | None = None

    @model_validator(mode="after")
    def validate_hypothesis(self) -> "CausalHypothesisInput":
        if len(set(self.candidate_event_ids)) != len(self.candidate_event_ids):
            raise ValueError("timeline_hypothesis_duplicate_candidate_event")
        if self.counterfactual_evidence_ref is not None:
            folded = self.counterfactual_evidence_ref.casefold()
            if any(marker in folded for marker in _FORBIDDEN_REFERENCE_MARKERS):
                raise ValueError("timeline_hypothesis_counterfactual_reference_may_contain_secret")
        return self


class HypothesisEventSupport(BaseModel):
    event_id: str
    support_score: float = Field(ge=0.0, le=1.0)
    temporal_proximity: float = Field(ge=0.0, le=1.0)
    object_overlap: float = Field(ge=0.0, le=1.0)
    direct_relation_support: float = Field(ge=0.0, le=1.0)
    authority_weight: float = Field(ge=0.0, le=1.0)
    evidence_density: float = Field(ge=0.0, le=1.0)
    observed_after_target: bool = False
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class CausalHypothesisAssessment(BaseModel):
    hypothesis_id: str
    label: str
    disposition: HypothesisDisposition
    score: float = Field(ge=0.0, le=1.0)
    event_support: tuple[HypothesisEventSupport, ...]
    counterfactual_support_present: bool = False
    counterfactual_evidence_ref: str | None = None
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ("correlation_is_not_causation",)
    causal_claim_proven: bool = False

    @model_validator(mode="after")
    def assessment_never_proves_causality(self) -> "CausalHypothesisAssessment":
        if self.causal_claim_proven:
            raise ValueError("timeline_investigation_cannot_prove_causality")
        return self


class CausalInvestigationView(BaseModel):
    contract: str = TIMELINE_CAUSAL_INVESTIGATION_CONTRACT
    tenant_id: str
    target_event_id: str
    ranked_hypotheses: tuple[CausalHypothesisAssessment, ...]
    evidence_refs: tuple[str, ...]
    competing_hypotheses_preserved: bool = True
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    warnings: tuple[str, ...] = (
        "correlation_is_not_causation",
        "counterfactual_evidence_requires_separate_causal_attribution_boundary",
        "timeline_investigation_never_authorizes_business_action",
    )

    @model_validator(mode="after")
    def preserve_investigation_boundary(self) -> "CausalInvestigationView":
        if not self.competing_hypotheses_preserved:
            raise ValueError("timeline_investigation_must_preserve_competing_hypotheses")
        if self.causal_claim_proven:
            raise ValueError("timeline_investigation_cannot_prove_causality")
        if self.execution_authority_granted:
            raise ValueError("timeline_investigation_cannot_grant_execution")
        if len(self.ranked_hypotheses) < 2:
            raise ValueError("timeline_investigation_requires_competing_hypotheses")
        return self


def _direct_relation_support(
    *,
    candidate: RealWorldTimelineEvent,
    target: RealWorldTimelineEvent,
    links: tuple[TimelineEventLink, ...],
) -> float:
    return 1.0 if any(
        {link.source_event_id, link.target_event_id} == {candidate.event_id, target.event_id}
        for link in links
    ) else 0.0


def _object_overlap(
    candidate: RealWorldTimelineEvent,
    target: RealWorldTimelineEvent,
) -> float:
    candidate_refs = {item.object_ref for item in candidate.object_relations}
    target_refs = {item.object_ref for item in target.object_relations}
    if not target_refs:
        return 0.0
    return min(len(candidate_refs & target_refs) / len(target_refs), 1.0)


def _temporal_proximity(
    candidate: RealWorldTimelineEvent,
    target: RealWorldTimelineEvent,
) -> float:
    gap_seconds = (target.occurred_at - candidate.occurred_at).total_seconds()
    if gap_seconds < 0:
        return 0.0
    gap_hours = gap_seconds / 3600.0
    return round(max(0.0, 1.0 - (gap_hours / 24.0)), 6)


def _event_support(
    *,
    candidate: RealWorldTimelineEvent,
    target: RealWorldTimelineEvent,
    links: tuple[TimelineEventLink, ...],
) -> HypothesisEventSupport:
    temporal = _temporal_proximity(candidate, target)
    overlap = _object_overlap(candidate, target)
    direct = _direct_relation_support(candidate=candidate, target=target, links=links)
    authority = _AUTHORITY_WEIGHT[candidate.authority_class]
    evidence_density = min(len(candidate.evidence_refs) / 3.0, 1.0)
    score = (
        (0.35 * temporal)
        + (0.25 * overlap)
        + (0.15 * direct)
        + (0.15 * authority)
        + (0.10 * evidence_density)
    )
    return HypothesisEventSupport(
        event_id=candidate.event_id,
        support_score=round(min(max(score, 0.0), 1.0), 6),
        temporal_proximity=temporal,
        object_overlap=round(overlap, 6),
        direct_relation_support=direct,
        authority_weight=authority,
        evidence_density=round(evidence_density, 6),
        observed_after_target=candidate.observed_at > target.observed_at,
        evidence_refs=candidate.evidence_refs,
    )


def _assess_hypothesis(
    *,
    hypothesis: CausalHypothesisInput,
    by_id: dict[str, RealWorldTimelineEvent],
    target: RealWorldTimelineEvent,
    links: tuple[TimelineEventLink, ...],
) -> CausalHypothesisAssessment:
    blockers: list[str] = []
    warnings = ["correlation_is_not_causation"]
    supports: list[HypothesisEventSupport] = []
    evidence_refs: list[str] = []

    for event_id in hypothesis.candidate_event_ids:
        candidate = by_id.get(event_id)
        if candidate is None:
            raise ValueError("timeline_hypothesis_references_unknown_event")
        if candidate.event_id == target.event_id:
            raise ValueError("timeline_hypothesis_cannot_use_target_as_cause_candidate")
        if candidate.occurred_at > target.occurred_at:
            blockers.append(f"candidate_occurs_after_target:{candidate.event_id}")
            continue
        support = _event_support(candidate=candidate, target=target, links=links)
        supports.append(support)
        evidence_refs.extend(candidate.evidence_refs)
        if support.observed_after_target:
            warnings.append(f"candidate_observed_after_target:{candidate.event_id}")

    if hypothesis.counterfactual_evidence_ref is not None:
        evidence_refs.append(hypothesis.counterfactual_evidence_ref)
        warnings.append("counterfactual_support_present_but_not_causal_authority")

    if not supports:
        score = 0.0
        disposition = HypothesisDisposition.INSUFFICIENT
        blockers.append("hypothesis_has_no_temporally_valid_candidate_events")
    else:
        score = sum(item.support_score for item in supports) / len(supports)
        if not any(
            item.object_overlap > 0.0 or item.direct_relation_support > 0.0
            for item in supports
        ):
            blockers.append("hypothesis_missing_object_or_relation_bridge")
            score = min(score, 0.49)
        score = round(score, 6)
        if score >= 0.65:
            disposition = HypothesisDisposition.PLAUSIBLE
        elif score >= 0.40:
            disposition = HypothesisDisposition.WEAK
        else:
            disposition = HypothesisDisposition.INSUFFICIENT

    return CausalHypothesisAssessment(
        hypothesis_id=hypothesis.hypothesis_id,
        label=hypothesis.label,
        disposition=disposition,
        score=score,
        event_support=tuple(supports),
        counterfactual_support_present=hypothesis.counterfactual_evidence_ref is not None,
        counterfactual_evidence_ref=hypothesis.counterfactual_evidence_ref,
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def investigate_timeline_causes(
    *,
    snapshot: RealWorldTimelineSnapshot,
    target_event_id: str,
    hypotheses: tuple[CausalHypothesisInput, ...],
) -> CausalInvestigationView:
    """Rank competing timeline explanations while keeping causal authority separate."""

    snapshot = RealWorldTimelineSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if len(hypotheses) < 2:
        raise ValueError("timeline_investigation_requires_competing_hypotheses")
    hypothesis_ids = [item.hypothesis_id for item in hypotheses]
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        raise ValueError("timeline_investigation_duplicate_hypothesis_id")

    by_id = {item.event_id: item for item in snapshot.events}
    target = by_id.get(target_event_id)
    if target is None:
        raise ValueError("timeline_investigation_target_event_missing")

    assessments = tuple(
        sorted(
            (
                _assess_hypothesis(
                    hypothesis=hypothesis,
                    by_id=by_id,
                    target=target,
                    links=snapshot.links,
                )
                for hypothesis in hypotheses
            ),
            key=lambda item: (-item.score, item.hypothesis_id),
        )
    )
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *target.evidence_refs,
                *(ref for assessment in assessments for ref in assessment.evidence_refs),
            )
        )
    )
    return CausalInvestigationView(
        tenant_id=snapshot.tenant_id,
        target_event_id=target_event_id,
        ranked_hypotheses=assessments,
        evidence_refs=evidence_refs,
    )
