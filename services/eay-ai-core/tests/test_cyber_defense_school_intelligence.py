from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.cyber_benchmark_intelligence import (
    CyberBenchmarkEvidenceClass,
    build_cyber_benchmark_run,
    compare_cyber_benchmark_runs,
    default_cyber_benchmark_profile,
)
from app.cyber_defense_school import (
    CyberDefenseDomain,
    CyberKnowledgeSource,
    build_domain_receipt,
    build_source_observation,
    default_cyber_defense_curriculum,
    evaluate_cyber_defense_graduation,
)
from app.jarvis_benchmark import MetricDirection, MetricMeasurement

NOW = datetime(2026, 8, 21, 12, 30, tzinfo=UTC)


def _observation(source: CyberKnowledgeSource, *, age: timedelta = timedelta()):
    return build_source_observation(
        source=source,
        source_version_ref=f"version:{source.value}:2026-08-21",
        evidence_ref=f"evidence:{source.value}:2026-08-21",
        observed_at=NOW - age,
        recorded_at=NOW - age,
    )


def _domain_receipt(curriculum, domain: CyberDefenseDomain, *, unresolved=()):
    observations = tuple(
        _observation(source)
        for source in curriculum.required_sources_by_domain[domain]
    )
    return build_domain_receipt(
        curriculum=curriculum,
        domain=domain,
        as_of=NOW,
        source_observations=observations,
        attack_behavior_refs=(f"attack-behavior:{domain.value}",),
        weakness_refs=(f"weakness:{domain.value}",),
        detection_refs=(f"detection:{domain.value}",),
        mitigation_refs=(f"mitigation:{domain.value}",),
        eay_surface_refs=(f"eay-surface:{domain.value}",),
        evidence_refs=(f"eay-evidence:{domain.value}",),
        unresolved_questions=unresolved,
    )


def _passing_benchmark():
    profile = default_cyber_benchmark_profile(
        profile_id="jarvis-cyber-defense-school",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    challenger_measurements = []
    baseline_measurements = []
    for metric in profile.metrics:
        if metric.direction is MetricDirection.HIGHER_IS_BETTER:
            challenger = 1.0
            baseline = 0.80
        else:
            challenger = 0.0
            baseline = 0.10
        challenger_measurements.append(
            MetricMeasurement(
                metric_name=metric.metric_name,
                value=challenger,
                sample_count=40,
                evidence_ref=f"benchmark:jarvis:{metric.metric_name}",
            )
        )
        baseline_measurements.append(
            MetricMeasurement(
                metric_name=metric.metric_name,
                value=baseline,
                sample_count=40,
                evidence_ref=f"benchmark:mentor:{metric.metric_name}",
            )
        )

    environment_fingerprint = "a" * 64
    challenger_run = build_cyber_benchmark_run(
        profile=profile,
        system_id="eay-jarvis-cyber-defense",
        system_version="school-v1",
        environment_fingerprint=environment_fingerprint,
        measured_at=NOW,
        measurements=tuple(challenger_measurements),
    )
    baseline_run = build_cyber_benchmark_run(
        profile=profile,
        system_id="mentor-baseline",
        system_version="baseline-v1",
        environment_fingerprint=environment_fingerprint,
        measured_at=NOW,
        measurements=tuple(baseline_measurements),
    )
    return compare_cyber_benchmark_runs(
        profile=profile,
        challenger=challenger_run,
        baseline=baseline_run,
    )


def test_default_curriculum_covers_every_defensive_domain_and_source():
    curriculum = default_cyber_defense_curriculum()

    assert set(curriculum.domains) == set(CyberDefenseDomain)
    assert {item.source for item in curriculum.source_policies} == set(
        CyberKnowledgeSource
    )
    assert curriculum.architecture_evidence_required is True
    assert curriculum.exploit_generation_permitted is False
    assert curriculum.destructive_execution_permitted is False
    assert curriculum.production_mutation_permitted is False
    assert curriculum.automatic_remediation_permitted is False
    assert curriculum.execution_authority_granted is False

    kev = next(
        item
        for item in curriculum.source_policies
        if item.source is CyberKnowledgeSource.CISA_KEV
    )
    assert kev.can_assert_known_exploitation is True

    for policy in curriculum.source_policies:
        assert policy.server_side_only is True
        assert policy.can_assert_company_exposure is False
        assert policy.can_confirm_company_incident is False
        assert policy.attack_instruction_content_allowed is False
        assert policy.exploit_generation_permitted is False
        assert policy.credential_capture_permitted is False
        assert policy.execution_authority_granted is False


def test_domain_receipt_requires_current_sources_and_eay_architecture_evidence():
    curriculum = default_cyber_defense_curriculum()
    domain = CyberDefenseDomain.WEB_API
    required = curriculum.required_sources_by_domain[domain]

    current = tuple(_observation(source) for source in required)
    ready = build_domain_receipt(
        curriculum=curriculum,
        domain=domain,
        as_of=NOW,
        source_observations=current,
        attack_behavior_refs=("attack-behavior:web-api",),
        weakness_refs=("weakness:CWE-862",),
        detection_refs=("detection:web-api-authz",),
        mitigation_refs=("mitigation:server-side-authz",),
        eay_surface_refs=("eay-surface:candidate-gateway",),
        evidence_refs=("eay-evidence:gateway-authority",),
    )
    assert ready.source_coverage_complete is True
    assert ready.source_freshness_complete is True
    assert ready.architecture_awareness_complete is True
    assert ready.defensive_reasoning_ready is True
    assert ready.company_exposure_granted is False
    assert ready.execution_authority_granted is False

    stale = tuple(
        _observation(
            source,
            age=timedelta(days=2)
            if source is CyberKnowledgeSource.CISA_KEV
            else timedelta(),
        )
        for source in required
    )
    hold = build_domain_receipt(
        curriculum=curriculum,
        domain=domain,
        as_of=NOW,
        source_observations=stale,
        eay_surface_refs=("eay-surface:candidate-gateway",),
        evidence_refs=("eay-evidence:gateway-authority",),
    )
    assert hold.source_coverage_complete is True
    assert hold.source_freshness_complete is False
    assert hold.defensive_reasoning_ready is False


def test_unresolved_questions_force_defensive_abstention():
    curriculum = default_cyber_defense_curriculum()
    receipt = _domain_receipt(
        curriculum,
        CyberDefenseDomain.AI_AGENTIC,
        unresolved=("unknown:model-provider-runtime-version",),
    )

    assert receipt.source_coverage_complete is True
    assert receipt.source_freshness_complete is True
    assert receipt.architecture_awareness_complete is True
    assert receipt.defensive_reasoning_ready is False


def test_offensive_or_secret_bearing_references_are_rejected():
    with pytest.raises(ValueError, match="cyber_school_source_observation_ref_unsafe"):
        build_source_observation(
            source=CyberKnowledgeSource.CISA_KEV,
            source_version_ref="version:cisa-kev",
            evidence_ref="exploit_payload:forbidden",
            observed_at=NOW,
            recorded_at=NOW,
        )


def test_graduation_requires_all_domains_current_architecture_and_measured_win():
    curriculum = default_cyber_defense_curriculum()
    receipts = tuple(
        _domain_receipt(curriculum, domain)
        for domain in curriculum.domains
    )
    benchmark = _passing_benchmark()
    assert benchmark.benchmark_superiority_claim_allowed is True

    decision = evaluate_cyber_defense_graduation(
        curriculum=curriculum,
        domain_receipts=receipts,
        benchmark=benchmark,
    )
    assert decision.domain_coverage_complete is True
    assert decision.current_source_coverage_complete is True
    assert decision.architecture_awareness_complete is True
    assert decision.benchmark_superiority_proven is True
    assert decision.mentor_outperformance_claim_allowed is True
    assert decision.production_security_superiority_claim_allowed is False
    assert decision.exploit_generation_permitted is False
    assert decision.execution_authority_granted is False
    assert decision.blockers == ()


def test_missing_domain_blocks_outperformance_claim():
    curriculum = default_cyber_defense_curriculum()
    receipts = tuple(
        _domain_receipt(curriculum, domain)
        for domain in curriculum.domains
        if domain is not CyberDefenseDomain.IOT_OT
    )

    decision = evaluate_cyber_defense_graduation(
        curriculum=curriculum,
        domain_receipts=receipts,
        benchmark=_passing_benchmark(),
    )

    assert decision.domain_coverage_complete is False
    assert decision.mentor_outperformance_claim_allowed is False
    assert "cyber_school_domain_coverage_incomplete" in decision.blockers
