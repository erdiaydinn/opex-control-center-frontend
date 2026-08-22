from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.autonomous_investigator import (
    FalsificationResult,
    FalsificationVerdict,
    InvestigatorDisposition,
    InvestigatorHypothesis,
    InvestigatorProblem,
    ProblemNovelty,
    SourceIndependenceBinding,
    evaluate_autonomous_investigation,
)
from app.continuous_world_understanding import (
    SourceFreshnessExpectation,
    SourcePulse,
    WorldWatchDisposition,
    assess_continuous_world,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.research_engine import ResearchEvidence, ResearchRisk, SourceTier
from app.world_model import (
    EntityKind,
    TruthClass,
    WorldAssertion,
    WorldEntity,
    build_world_snapshot,
)

T0 = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)


def entity(tenant_id: str = "tenant-a") -> WorldEntity:
    return WorldEntity(
        entity_id="store:fulya",
        tenant_id=tenant_id,
        kind=EntityKind.STORE,
        display_name="Fulya",
    )


def assertion(
    assertion_id: str,
    *,
    value: float,
    observed_at: datetime,
    tenant_id: str = "tenant-a",
    confidence: float = 0.99,
) -> WorldAssertion:
    return WorldAssertion(
        assertion_id=assertion_id,
        tenant_id=tenant_id,
        entity_id="store:fulya",
        field_name="orders_per_hour",
        value=value,
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=T0 - timedelta(hours=1),
        observed_at=observed_at,
        source_ref=f"source://{assertion_id}",
        evidence_ref=f"evidence://{assertion_id}",
        confidence=confidence,
    )


def world(
    *,
    as_of: datetime,
    value: float = 100.0,
    assertion_id: str = "orders-v1",
    tenant_id: str = "tenant-a",
    confidence: float = 0.99,
):
    return build_world_snapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        entities=[entity(tenant_id)],
        assertions=[
            assertion(
                assertion_id,
                value=value,
                observed_at=as_of,
                tenant_id=tenant_id,
                confidence=confidence,
            )
        ],
    )


def contradicted_world(*, as_of: datetime = T1):
    return build_world_snapshot(
        tenant_id="tenant-a",
        as_of=as_of,
        entities=[entity()],
        assertions=[
            assertion("orders-a", value=100.0, observed_at=as_of),
            assertion("orders-b", value=70.0, observed_at=as_of),
        ],
    )


def hypotheses() -> tuple[InvestigatorHypothesis, ...]:
    return (
        InvestigatorHypothesis(
            hypothesis_id="h-demand",
            label="External demand event changed order intent",
            claim_key="claim:demand",
            required_falsification_test_ids=("f-demand",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-stock",
            label="Availability degradation suppressed conversion",
            claim_key="claim:stock",
            required_falsification_test_ids=("f-stock",),
        ),
        InvestigatorHypothesis(
            hypothesis_id="h-platform",
            label="Platform incident suppressed order intake",
            claim_key="claim:platform",
            required_falsification_test_ids=("f-platform",),
        ),
    )


def research_item(
    evidence_id: str,
    claim_key: str,
    publisher: str,
    *,
    tier: SourceTier,
    supports: bool = False,
    contradicts: bool = False,
) -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id=evidence_id,
        claim_key=claim_key,
        claim_value=f"value:{evidence_id}",
        source_url=f"https://{publisher}.example/{evidence_id}",
        source_domain=f"{publisher}.example",
        source_tier=tier,
        publisher_key=publisher,
        published_at=T0 - timedelta(minutes=10),
        fetched_at=T0,
        supports_claim=supports,
        contradicts_claim=contradicts,
        evidence_ref=f"evidence://{evidence_id}",
    )


def research_evidence() -> tuple[ResearchEvidence, ...]:
    return (
        research_item("d1", "claim:demand", "official", tier=SourceTier.PRIMARY, supports=True),
        research_item(
            "d2",
            "claim:demand",
            "secondary",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            supports=True,
        ),
        research_item(
            "d3",
            "claim:demand",
            "skeptic",
            tier=SourceTier.DISCOVERY_ONLY,
            contradicts=True,
        ),
        research_item("s1", "claim:stock", "catalog", tier=SourceTier.PRIMARY, supports=True),
        research_item(
            "s2",
            "claim:stock",
            "inventory",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        research_item(
            "s3",
            "claim:stock",
            "ops",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
        research_item("p1", "claim:platform", "status", tier=SourceTier.PRIMARY, supports=True),
        research_item(
            "p2",
            "claim:platform",
            "telemetry",
            tier=SourceTier.AUTHORITATIVE_SECONDARY,
            contradicts=True,
        ),
        research_item(
            "p3",
            "claim:platform",
            "review",
            tier=SourceTier.REPUTABLE_SECONDARY,
            contradicts=True,
        ),
    )


def prior_report(bound_world=None):
    bound_world = bound_world or world(as_of=T0)
    evidence = research_evidence()
    return evaluate_autonomous_investigation(
        problem=InvestigatorProblem(
            problem_id="problem:orders-down",
            tenant_id="tenant-a",
            company_id="company-a",
            question="Why did store orders fall despite normal staffing?",
            domains=("operations", "commerce"),
            as_of=T0,
            risk=ResearchRisk.HIGH,
            novelty=ProblemNovelty.NOVEL,
        ),
        world=bound_world,
        hypotheses=hypotheses(),
        evidence=evidence,
        source_bindings=tuple(
            SourceIndependenceBinding(
                evidence_id=item.evidence_id,
                source_family_key=f"family:{item.publisher_key}",
            )
            for item in evidence
        ),
        falsification_results=(
            FalsificationResult(
                test_id="f-demand",
                hypothesis_id="h-demand",
                verdict=FalsificationVerdict.SURVIVED,
                evidence_refs=("evidence://f-demand",),
                completed_at=T0,
            ),
            FalsificationResult(
                test_id="f-stock",
                hypothesis_id="h-stock",
                verdict=FalsificationVerdict.REFUTED,
                evidence_refs=("evidence://f-stock",),
                completed_at=T0,
            ),
            FalsificationResult(
                test_id="f-platform",
                hypothesis_id="h-platform",
                verdict=FalsificationVerdict.REFUTED,
                evidence_refs=("evidence://f-platform",),
                completed_at=T0,
            ),
        ),
    )


def expectation() -> SourceFreshnessExpectation:
    return SourceFreshnessExpectation(
        source_key="orders-live",
        maximum_silence_seconds=120,
        required_for_live_truth=True,
    )


def pulse(
    *,
    observed_at: datetime = T1,
    authority: TimelineAuthorityClass = TimelineAuthorityClass.GOVERNED_OPERATIONAL,
) -> SourcePulse:
    return SourcePulse(
        source_key="orders-live",
        observed_at=observed_at,
        authority_class=authority,
        evidence_ref=f"heartbeat://orders/{observed_at.isoformat()}",
    )


def timeline_event(
    *,
    tenant_id: str = "tenant-a",
    event_id: str = "event:orders",
    observed_at: datetime = T1,
):
    return build_timeline_event(
        event_id=event_id,
        event_type="eay.ops.orders.changed",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="source://orders",
        tenant_id=tenant_id,
        occurred_at=observed_at - timedelta(seconds=1),
        observed_at=observed_at,
        data_ref="data://orders/hourly",
        authority_class=TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        confidence=0.99,
        object_relations=(
            TimelineObjectRelation(
                object_ref="store:fulya",
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.SUBJECT,
            ),
        ),
        evidence_refs=("evidence://orders-event",),
    )


def test_same_semantic_world_at_new_as_of_does_not_thrash_prior_decision() -> None:
    previous = world(as_of=T0, assertion_id="orders-old")
    current = world(as_of=T1, assertion_id="orders-new")
    prior = prior_report(previous)

    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        previous_world=previous,
        source_expectations=(expectation(),),
        source_pulses=(pulse(),),
        prior_investigation=prior,
    )

    assert prior.disposition is InvestigatorDisposition.DECISION_READY
    assert previous.fingerprint != current.fingerprint
    assert assessment.world_change.material_change_count == 0
    assert assessment.prior_belief_invalidated is False
    assert assessment.disposition is WorldWatchDisposition.STABLE
    assert assessment.blockers == ()
    assert assessment.confidence_decay_multiplier == 1.0


def test_semantic_world_change_reopens_a_previous_decision() -> None:
    previous = world(as_of=T0, value=100.0)
    current = world(as_of=T1, value=72.0, assertion_id="orders-drop")

    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        previous_world=previous,
        source_expectations=(expectation(),),
        source_pulses=(pulse(),),
        prior_investigation=prior_report(previous),
    )

    assert assessment.world_change.material_change_count == 1
    assert assessment.prior_belief_invalidated is True
    assert assessment.disposition is WorldWatchDisposition.REINVESTIGATE
    assert "world_watch_prior_investigation_semantic_world_changed" in assessment.blockers
    assert assessment.directive is not None
    assert assessment.directive.read_only is True
    assert assessment.directive.automatic_research_execution_allowed is False
    assert assessment.execution_authority_granted is False


def test_required_source_silence_reopens_decision_and_decays_confidence() -> None:
    previous = world(as_of=T0)
    current = world(as_of=T1, assertion_id="orders-new")

    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        previous_world=previous,
        source_expectations=(expectation(),),
        source_pulses=(pulse(observed_at=T1 - timedelta(minutes=10)),),
        prior_investigation=prior_report(previous),
    )

    assert assessment.prior_belief_invalidated is True
    assert assessment.disposition is WorldWatchDisposition.REINVESTIGATE
    assert "world_watch_source_silent:orders-live" in assessment.blockers
    assert assessment.confidence_decay_multiplier <= 0.60
    assert assessment.directive is not None
    assert assessment.directive.required_source_keys == ("orders-live",)


def test_untrusted_context_pulse_cannot_fake_live_truth_freshness() -> None:
    current = world(as_of=T1)
    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        source_expectations=(expectation(),),
        source_pulses=(
            pulse(authority=TimelineAuthorityClass.CONTEXT_ONLY),
        ),
    )

    assert assessment.disposition is WorldWatchDisposition.REFRESH_REQUIRED
    assert "world_watch_source_authority_insufficient:orders-live" in assessment.blockers
    assert assessment.source_states[0].fresh is False
    assert assessment.source_states[0].authority_accepted is False
    assert assessment.authoritative_truth_surface is False


def test_equal_authority_world_contradiction_forces_read_only_reinvestigation() -> None:
    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=contradicted_world(),
        source_expectations=(expectation(),),
        source_pulses=(pulse(),),
    )

    assert assessment.disposition is WorldWatchDisposition.REINVESTIGATE
    assert "world_watch_company_world_contradicted" in assessment.blockers
    assert assessment.confidence_decay_multiplier <= 0.40
    assert assessment.directive is not None
    assert assessment.directive.previous_investigation_fingerprint is None
    assert assessment.directive.firm_company_claim_authorized is False
    assert assessment.directive.execution_authority_granted is False


def test_unknown_prior_world_lineage_reopens_conservatively() -> None:
    old = world(as_of=T0 - timedelta(minutes=5), assertion_id="orders-oldest")
    previous = world(as_of=T0, assertion_id="orders-middle")
    current = world(as_of=T1, assertion_id="orders-current")
    prior = prior_report(old)

    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        previous_world=previous,
        source_expectations=(expectation(),),
        source_pulses=(pulse(),),
        prior_investigation=prior,
    )

    assert assessment.world_change.material_change_count == 0
    assert assessment.prior_belief_invalidated is True
    assert assessment.disposition is WorldWatchDisposition.REINVESTIGATE
    assert "world_watch_prior_world_lineage_unknown" in assessment.blockers


def test_timeline_replay_is_idempotent_but_cross_tenant_and_future_events_fail_closed() -> None:
    current = world(as_of=T1)
    event = timeline_event()
    assessment = assess_continuous_world(
        tenant_id="tenant-a",
        company_id="company-a",
        now=T1,
        current_world=current,
        timeline_events=(event, event),
        source_expectations=(expectation(),),
        source_pulses=(pulse(),),
    )
    assert assessment.timeline_event_count == 1
    assert assessment.strong_authority_event_count == 1
    assert assessment.distinct_event_domain_count == 1

    with pytest.raises(ValueError, match="cross_tenant_timeline_event"):
        assess_continuous_world(
            tenant_id="tenant-a",
            company_id="company-a",
            now=T1,
            current_world=current,
            timeline_events=(timeline_event(tenant_id="tenant-b"),),
        )

    with pytest.raises(ValueError, match="timeline_event_from_future"):
        assess_continuous_world(
            tenant_id="tenant-a",
            company_id="company-a",
            now=T1,
            current_world=current,
            timeline_events=(
                timeline_event(
                    event_id="event:future",
                    observed_at=T1 + timedelta(seconds=1),
                ),
            ),
        )


def test_future_source_pulse_and_cross_company_prior_are_rejected() -> None:
    previous = world(as_of=T0)
    current = world(as_of=T1)

    with pytest.raises(ValueError, match="source_pulse_from_future"):
        assess_continuous_world(
            tenant_id="tenant-a",
            company_id="company-a",
            now=T1,
            current_world=current,
            source_expectations=(expectation(),),
            source_pulses=(pulse(observed_at=T1 + timedelta(seconds=1)),),
        )

    prior = prior_report(previous).model_copy(update={"company_id": "company-b"})
    with pytest.raises(ValueError, match="prior_investigation_company_mismatch"):
        assess_continuous_world(
            tenant_id="tenant-a",
            company_id="company-a",
            now=T1,
            current_world=current,
            previous_world=previous,
            prior_investigation=prior,
        )
