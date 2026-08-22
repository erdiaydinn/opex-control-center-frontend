from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.specialist_mastery_registry import (
    MasteryTier,
    SpecialistDomain,
    SpecialistScorecard,
    admit_specialist_mastery,
    build_specialist_evidence,
    default_mastery_policy,
)

NOW = datetime(2026, 8, 21, 6, 45, tzinfo=UTC)
SPECIALIST_ID = "jarvis-primary"


def _score(
    value: float = 0.98,
    *,
    authority: float | None = None,
    adversarial: float | None = None,
) -> SpecialistScorecard:
    return SpecialistScorecard(
        factuality=value,
        currentness=value,
        source_quality=value,
        citation_completeness=value,
        falsification_performance=value,
        calibration=value,
        tool_correctness=value,
        domain_benchmark=value,
        authority_adherence=authority if authority is not None else value,
        adversarial_robustness=(
            adversarial if adversarial is not None else value
        ),
    )


def _evidence(
    domain: SpecialistDomain,
    benchmark_id: str,
    *,
    specialist_id: str = SPECIALIST_ID,
    cases: int = 150,
    score: SpecialistScorecard | None = None,
    synthetic: bool = False,
    production_shaped: bool = True,
    independent: bool = True,
    reproducible: bool = True,
    age: timedelta = timedelta(days=1),
):
    return build_specialist_evidence(
        specialist_id=specialist_id,
        domain=domain,
        benchmark_id=benchmark_id,
        benchmark_version="v1",
        evaluated_cases=cases,
        observed_at=NOW - age,
        scorecard=score or _score(),
        evidence_refs=(f"evidence://{benchmark_id}",),
        synthetic=synthetic,
        production_shaped=production_shaped,
        independent_evaluator=independent,
        reproducible=reproducible,
    )


def _admit(domain: SpecialistDomain, evidence):
    return admit_specialist_mastery(
        specialist_id=SPECIALIST_ID,
        domain=domain,
        evidence=evidence,
        now=NOW,
    )


def test_general_reasoning_master_requires_multi_benchmark_evidence() -> None:
    evidence = tuple(
        _evidence(SpecialistDomain.GENERAL_REASONING, f"reasoning-{index}")
        for index in range(3)
    )

    decision = _admit(SpecialistDomain.GENERAL_REASONING, evidence)

    assert decision.specialist_id == SPECIALIST_ID
    assert decision.admitted_tier is MasteryTier.MASTER
    assert decision.production_mastery_claim_allowed is True
    assert decision.universal_superiority_claimed is False
    assert decision.execution_authority_granted is False
    assert decision.distinct_benchmarks == 3
    assert decision.evaluated_cases == 450
    assert decision.blockers == ()


def test_synthetic_only_evidence_cannot_admit_production_mastery() -> None:
    evidence = tuple(
        _evidence(
            SpecialistDomain.DEEP_RESEARCH,
            f"synthetic-research-{index}",
            synthetic=True,
            production_shaped=False,
        )
        for index in range(3)
    )

    decision = _admit(SpecialistDomain.DEEP_RESEARCH, evidence)

    assert decision.admitted_tier is MasteryTier.EXPERT
    assert decision.production_mastery_claim_allowed is False
    assert "specialist_master_non_synthetic_evidence_required" in decision.blockers
    assert "specialist_master_production_shaped_evidence_required" in decision.blockers


def test_sensitive_specialists_use_stricter_master_policy() -> None:
    standard = default_mastery_policy(SpecialistDomain.GENERAL_REASONING)
    sensitive = default_mastery_policy(SpecialistDomain.LEGAL)

    assert sensitive.master_mean > standard.master_mean
    assert sensitive.master_minimum > standard.master_minimum
    assert sensitive.master_cases > standard.master_cases
    assert sensitive.master_authority_minimum > standard.master_authority_minimum
    assert sensitive.maximum_evidence_age_seconds < standard.maximum_evidence_age_seconds


def test_legal_master_requires_strict_authority_and_adversarial_scores() -> None:
    evidence = tuple(
        _evidence(
            SpecialistDomain.LEGAL,
            f"legal-{index}",
            score=_score(0.98, authority=1.0, adversarial=0.98),
        )
        for index in range(3)
    )

    decision = _admit(SpecialistDomain.LEGAL, evidence)

    assert decision.admitted_tier is MasteryTier.MASTER
    assert decision.aggregate_scorecard is not None
    assert decision.aggregate_scorecard.authority_adherence == 1.0
    assert decision.execution_authority_granted is False


def test_sensitive_mastery_is_withheld_when_authority_discipline_is_weak() -> None:
    evidence = tuple(
        _evidence(
            SpecialistDomain.FINANCE,
            f"finance-{index}",
            score=_score(0.98, authority=0.97, adversarial=0.98),
        )
        for index in range(3)
    )

    decision = _admit(SpecialistDomain.FINANCE, evidence)

    assert decision.admitted_tier is MasteryTier.EXPERT
    assert "specialist_master_authority_adherence_insufficient" in decision.blockers
    assert decision.production_mastery_claim_allowed is False


def test_stale_evidence_is_not_counted_as_current_mastery() -> None:
    evidence = (
        _evidence(
            SpecialistDomain.CURRENT_WORLD,
            "current-world-old",
            age=timedelta(days=200),
        ),
    )

    decision = _admit(SpecialistDomain.CURRENT_WORLD, evidence)

    assert decision.admitted_tier is MasteryTier.UNADMITTED
    assert decision.evaluated_cases == 0
    assert "specialist_evidence_stale:current-world-old" in decision.blockers


def test_cross_domain_evidence_is_rejected() -> None:
    legal = _evidence(SpecialistDomain.LEGAL, "legal-scope")

    with pytest.raises(ValueError, match="specialist_evidence_domain_mismatch"):
        _admit(SpecialistDomain.HUMAN_RESOURCES, (legal,))


def test_cross_specialist_evidence_is_rejected() -> None:
    other = _evidence(
        SpecialistDomain.LEGAL,
        "other-specialist",
        specialist_id="legal-agent-b",
    )

    with pytest.raises(ValueError, match="specialist_evidence_identity_mismatch"):
        _admit(SpecialistDomain.LEGAL, (other,))


def test_tampered_benchmark_evidence_is_rejected_before_admission() -> None:
    original = _evidence(SpecialistDomain.CYBER_SECURITY, "cyber-defense")
    tampered = original.model_copy(update={"evaluated_cases": 10_000})

    with pytest.raises(
        ValueError,
        match="specialist_evidence_fingerprint_mismatch",
    ):
        _admit(SpecialistDomain.CYBER_SECURITY, (tampered,))


def test_offensive_cyber_evidence_cannot_enter_mastery_registry() -> None:
    with pytest.raises(ValueError, match="cyber_mastery_evidence_must_be_defensive"):
        build_specialist_evidence(
            specialist_id=SPECIALIST_ID,
            domain=SpecialistDomain.CYBER_SECURITY,
            benchmark_id="offensive-cyber",
            benchmark_version="v1",
            evaluated_cases=500,
            observed_at=NOW,
            scorecard=_score(1.0, authority=1.0, adversarial=1.0),
            evidence_refs=("evidence://cyber",),
            production_shaped=True,
            independent_evaluator=True,
            reproducible=True,
            defensive_only=False,
        )
