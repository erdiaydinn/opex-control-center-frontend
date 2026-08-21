from __future__ import annotations

from types import SimpleNamespace

from app.adaptive_epistemic_control import (
    AdaptiveEpistemicDirective,
    EpistemicMoveKind,
    EpistemicProbe,
    EpistemicStrategy,
)
from app.research_engine import ResearchRole
from app.research_frontier_intelligence import (
    ResearchFrontierDecision,
    ResearchFrontierPolicy,
    plan_research_frontier_wave,
)


def _probe(
    probe_id: str,
    strategy: EpistemicStrategy,
    *,
    hypothesis_id: str = "h-demand",
    gain: float = 0.50,
) -> EpistemicProbe:
    return EpistemicProbe(
        probe_id=probe_id,
        hypothesis_id=hypothesis_id,
        task_ref=f"{hypothesis_id}:{strategy.value}",
        role=(
            ResearchRole.CONTRADICTION
            if strategy in {
                EpistemicStrategy.FALSIFICATION,
                EpistemicStrategy.CONTRADICTION_FIRST,
            }
            else ResearchRole.CORROBORATION
        ),
        strategy=strategy,
        query_intent=f"Investigate {strategy.value} using independent evidence.",
        expected_information_gain=gain,
        reason_codes=("test-probe",),
    )


def _directive(*probes: EpistemicProbe) -> AdaptiveEpistemicDirective:
    draft = {
        "contract": "eay-adaptive-epistemic-control-v1",
        "problem_id": "problem:orders-down",
        "tenant_id": "tenant-a",
        "company_id": "company-a",
        "round_index": 0,
        "move_kind": EpistemicMoveKind.PROBE.value,
        "uncertainty": 0.80,
        "raw_leading_confidence": 0.55,
        "effective_leading_confidence": 0.55,
        "calibration_multiplier": 1.0,
        "stall_count": 0,
        "selected_probe": probes[0].model_dump(mode="json"),
        "candidate_probes": [item.model_dump(mode="json") for item in probes],
        "reason_codes": ["test"],
        "blockers": [],
        "firm_company_claim_authorized": False,
        "production_truth_promoted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "automatic_research_execution_allowed": False,
        "execution_authority_granted": False,
        "direct_provider_call_allowed": False,
    }
    from app.adaptive_epistemic_control import _fingerprint

    return AdaptiveEpistemicDirective.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _report(*, company_id: str = "company-a"):
    return SimpleNamespace(
        problem_id="problem:orders-down",
        tenant_id="tenant-a",
        company_id=company_id,
        fingerprint="a" * 64,
        ranking=SimpleNamespace(leading_hypothesis_id="h-demand"),
    )


def test_parallel_wave_keeps_leader_falsification_and_diverse_lanes() -> None:
    falsification = _probe(
        "probe:falsify",
        EpistemicStrategy.FALSIFICATION,
        gain=0.40,
    )
    contradiction = _probe(
        "probe:contradiction",
        EpistemicStrategy.CONTRADICTION_FIRST,
        hypothesis_id="h-stock",
        gain=0.92,
    )
    corroboration = _probe(
        "probe:corroborate",
        EpistemicStrategy.INDEPENDENT_CORROBORATION,
        gain=0.70,
    )
    primary = _probe(
        "probe:primary",
        EpistemicStrategy.PRIMARY_TRIANGULATION,
        gain=0.65,
    )

    wave = plan_research_frontier_wave(
        directive=_directive(
            contradiction,
            falsification,
            corroboration,
            primary,
        ),
        report=_report(),
        depth=0,
    )

    assert wave.decision is ResearchFrontierDecision.DISPATCH_BOUNDED_WAVE
    assert wave.probes[0].probe_id == "probe:falsify"
    assert {item.strategy for item in wave.probes} >= {
        EpistemicStrategy.FALSIFICATION,
        EpistemicStrategy.CONTRADICTION_FIRST,
        EpistemicStrategy.INDEPENDENT_CORROBORATION,
    }
    assert "research_frontier_leader_falsification_included" in wave.reason_codes
    assert wave.automatic_execution_allowed is False
    assert wave.execution_authority_granted is False
    assert wave.direct_provider_call_allowed is False
    assert wave.production_truth_promoted is False


def test_wave_is_bounded_by_parallel_and_total_budget() -> None:
    probes = tuple(
        _probe(
            f"probe:{index}",
            EpistemicStrategy.CROSS_DOMAIN_EXPANSION,
            hypothesis_id=f"h-{index}",
            gain=0.80 - index * 0.01,
        )
        for index in range(10)
    )
    wave = plan_research_frontier_wave(
        directive=_directive(*probes),
        report=_report(),
        depth=1,
        prior_probe_ids=("old:1", "old:2", "old:3", "old:4"),
        policy=ResearchFrontierPolicy(
            maximum_parallel_probes=3,
            maximum_total_probes=6,
        ),
    )

    assert len(wave.probes) <= 2
    assert wave.scheduled_probe_count_after <= 6


def test_prior_probe_is_not_scheduled_again() -> None:
    first = _probe("probe:first", EpistemicStrategy.FALSIFICATION, gain=0.90)
    second = _probe(
        "probe:second",
        EpistemicStrategy.CONTRADICTION_FIRST,
        gain=0.80,
    )
    wave = plan_research_frontier_wave(
        directive=_directive(first, second),
        report=_report(),
        depth=1,
        prior_probe_ids=("probe:first",),
    )

    assert tuple(item.probe_id for item in wave.probes) == ("probe:second",)


def test_depth_limit_holds_instead_of_recursing_without_bound() -> None:
    probe = _probe("probe:one", EpistemicStrategy.FALSIFICATION)
    wave = plan_research_frontier_wave(
        directive=_directive(probe),
        report=_report(),
        depth=4,
    )

    assert wave.decision is ResearchFrontierDecision.HOLD_BUDGET_EXHAUSTED
    assert wave.probes == ()
    assert "research_frontier_requires_fresh_sequential_assessment" in wave.blockers


def test_cross_company_report_is_rejected_before_frontier_planning() -> None:
    probe = _probe("probe:one", EpistemicStrategy.FALSIFICATION)
    try:
        plan_research_frontier_wave(
            directive=_directive(probe),
            report=_report(company_id="company-b"),
            depth=0,
        )
    except ValueError as exc:
        assert str(exc) == "research_frontier_company_mismatch"
    else:
        raise AssertionError("cross-company frontier planning must fail")
