from datetime import datetime, timedelta, timezone

import pytest

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
from app.timeline_causal_investigation import (
    CausalHypothesisInput,
    HypothesisDisposition,
    investigate_timeline_causes,
)


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _relation(ref: str) -> TimelineObjectRelation:
    return TimelineObjectRelation(
        object_ref=ref,
        object_kind=TimelineObjectKind.WORLD_ENTITY,
        qualifier=TimelineObjectQualifier.AFFECTED,
    )


def _event(
    event_id: str,
    *,
    at: datetime,
    authority: TimelineAuthorityClass,
    kind: TimelineEventKind = TimelineEventKind.COMPANY_ASSERTION,
    refs: tuple[str, ...] = ("store:fulya",),
    confidence: float = 0.9,
):
    return build_timeline_event(
        event_id=event_id,
        event_type="eay.company.assertion" if kind is not TimelineEventKind.OUTCOME else "eay.outcome.observed",
        event_kind=kind,
        source_ref=f"source://{event_id}",
        tenant_id="YS_TR",
        occurred_at=at,
        observed_at=at,
        data_ref=f"data://{event_id}",
        authority_class=authority,
        confidence=confidence,
        object_relations=tuple(_relation(ref) for ref in refs),
        evidence_refs=(f"evidence://{event_id}",),
    )


def _snapshot():
    availability = _event(
        "availability-drop",
        at=NOW - timedelta(minutes=10),
        authority=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        refs=("store:fulya", "metric:availability"),
    )
    rain = _event(
        "heavy-rain",
        at=NOW - timedelta(minutes=30),
        authority=TimelineAuthorityClass.CONTEXT_ONLY,
        kind=TimelineEventKind.EXTERNAL_CONTEXT,
        refs=("location:istanbul",),
    )
    ambient = _event(
        "ambient-rumor",
        at=NOW - timedelta(minutes=4),
        authority=TimelineAuthorityClass.AMBIENT_UNTRUSTED,
        kind=TimelineEventKind.AMBIENT_OBSERVATION,
        refs=("store:fulya",),
        confidence=0.99,
    )
    target = _event(
        "otp-outcome",
        at=NOW,
        authority=TimelineAuthorityClass.VERIFIED_OUTCOME,
        kind=TimelineEventKind.OUTCOME,
        refs=("store:fulya", "metric:otp"),
    )
    future = _event(
        "future-event",
        at=NOW + timedelta(minutes=5),
        authority=TimelineAuthorityClass.VERIFIED_COMPANY,
        refs=("store:fulya",),
    )
    links = (
        TimelineEventLink(
            tenant_id="YS_TR",
            source_event_id=availability.event_id,
            relation=TimelineRelationKind.TEMPORALLY_CORRELATED,
            target_event_id=target.event_id,
            evidence_refs=("analysis://availability-otp-overlap",),
            confidence=0.86,
        ),
        TimelineEventLink(
            tenant_id="YS_TR",
            source_event_id=rain.event_id,
            relation=TimelineRelationKind.TEMPORALLY_CORRELATED,
            target_event_id=target.event_id,
            evidence_refs=("analysis://rain-otp-overlap",),
            confidence=0.75,
        ),
    )
    return build_real_world_timeline(
        tenant_id="YS_TR",
        window_start=NOW - timedelta(hours=1),
        window_end=NOW + timedelta(hours=1),
        events=(availability, rain, ambient, target, future),
        links=links,
    )


def test_investigation_requires_competing_hypotheses() -> None:
    with pytest.raises(ValueError, match="timeline_investigation_requires_competing_hypotheses"):
        investigate_timeline_causes(
            snapshot=_snapshot(),
            target_event_id="otp-outcome",
            hypotheses=(
                CausalHypothesisInput(
                    hypothesis_id="availability",
                    label="Availability deterioration",
                    candidate_event_ids=("availability-drop",),
                ),
            ),
        )


def test_ranked_hypotheses_preserve_correlation_not_causation() -> None:
    view = investigate_timeline_causes(
        snapshot=_snapshot(),
        target_event_id="otp-outcome",
        hypotheses=(
            CausalHypothesisInput(
                hypothesis_id="availability",
                label="Availability deterioration",
                candidate_event_ids=("availability-drop",),
            ),
            CausalHypothesisInput(
                hypothesis_id="rain",
                label="Heavy rain",
                candidate_event_ids=("heavy-rain",),
            ),
            CausalHypothesisInput(
                hypothesis_id="ambient",
                label="Unverified ambient discussion",
                candidate_event_ids=("ambient-rumor",),
            ),
        ),
    )

    assert view.ranked_hypotheses[0].hypothesis_id == "availability"
    assert view.ranked_hypotheses[0].disposition is HypothesisDisposition.PLAUSIBLE
    assert view.causal_claim_proven is False
    assert view.execution_authority_granted is False
    assert all(item.causal_claim_proven is False for item in view.ranked_hypotheses)
    assert next(item for item in view.ranked_hypotheses if item.hypothesis_id == "ambient").score < view.ranked_hypotheses[0].score


def test_counterfactual_evidence_is_surfaced_but_not_promoted_to_causal_authority() -> None:
    view = investigate_timeline_causes(
        snapshot=_snapshot(),
        target_event_id="otp-outcome",
        hypotheses=(
            CausalHypothesisInput(
                hypothesis_id="availability",
                label="Availability deterioration",
                candidate_event_ids=("availability-drop",),
                counterfactual_evidence_ref="counterfactual://matched-store/availability/001",
            ),
            CausalHypothesisInput(
                hypothesis_id="rain",
                label="Heavy rain",
                candidate_event_ids=("heavy-rain",),
            ),
        ),
    )
    availability = next(item for item in view.ranked_hypotheses if item.hypothesis_id == "availability")

    assert availability.counterfactual_support_present is True
    assert availability.counterfactual_evidence_ref == "counterfactual://matched-store/availability/001"
    assert availability.causal_claim_proven is False
    assert view.causal_claim_proven is False


def test_future_event_cannot_be_used_as_explanation_for_prior_target() -> None:
    view = investigate_timeline_causes(
        snapshot=_snapshot(),
        target_event_id="otp-outcome",
        hypotheses=(
            CausalHypothesisInput(
                hypothesis_id="future",
                label="Future company event",
                candidate_event_ids=("future-event",),
            ),
            CausalHypothesisInput(
                hypothesis_id="availability",
                label="Availability deterioration",
                candidate_event_ids=("availability-drop",),
            ),
        ),
    )
    future = next(item for item in view.ranked_hypotheses if item.hypothesis_id == "future")

    assert future.disposition is HypothesisDisposition.INSUFFICIENT
    assert future.score == 0.0
    assert "candidate_occurs_after_target:future-event" in future.blockers


def test_unknown_candidate_event_fails_closed() -> None:
    with pytest.raises(ValueError, match="timeline_hypothesis_references_unknown_event"):
        investigate_timeline_causes(
            snapshot=_snapshot(),
            target_event_id="otp-outcome",
            hypotheses=(
                CausalHypothesisInput(
                    hypothesis_id="missing",
                    label="Missing evidence",
                    candidate_event_ids=("does-not-exist",),
                ),
                CausalHypothesisInput(
                    hypothesis_id="availability",
                    label="Availability deterioration",
                    candidate_event_ids=("availability-drop",),
                ),
            ),
        )


def test_counterfactual_reference_with_secret_material_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="timeline_hypothesis_counterfactual_reference_may_contain_secret",
    ):
        CausalHypothesisInput(
            hypothesis_id="secret",
            label="Secret-bearing hypothesis",
            candidate_event_ids=("availability-drop",),
            counterfactual_evidence_ref="https://example.test/cf?token=do-not-retain",
        )
