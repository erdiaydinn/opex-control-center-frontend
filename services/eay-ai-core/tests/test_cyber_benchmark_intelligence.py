from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.cyber_benchmark_intelligence import (
    CYBER_BENCHMARK_REQUIRED_WIN_RATE,
    CyberBenchmarkEvidenceClass,
    CyberBenchmarkProfile,
    CyberBenchmarkTaskFamily,
    build_cyber_benchmark_run,
    compare_cyber_benchmark_runs,
    default_cyber_benchmark_profile,
)
from app.jarvis_benchmark import MetricMeasurement

NOW = datetime(2026, 8, 19, 19, 10, tzinfo=UTC)
ENV_A = "a" * 64
ENV_B = "b" * 64


def _values(*, winner: bool) -> dict[str, float]:
    if winner:
        return {
            "evidence_grounding_accuracy": 0.995,
            "company_risk_precision": 0.995,
            "unknown_exposure_abstention_rate": 0.995,
            "tenant_isolation_accuracy": 1.0,
            "known_exploitation_source_precision": 0.995,
            "temporal_freshness_accuracy": 0.995,
            "defensive_detection_coverage": 0.97,
            "incident_need_to_know_accuracy": 1.0,
            "unsafe_offensive_content_rate": 0.0,
            "unauthorized_action_rate": 0.0,
            "false_positive_rate": 0.03,
            "remediation_quality": 0.96,
        }
    return {
        "evidence_grounding_accuracy": 0.90,
        "company_risk_precision": 0.92,
        "unknown_exposure_abstention_rate": 0.91,
        "tenant_isolation_accuracy": 0.98,
        "known_exploitation_source_precision": 0.93,
        "temporal_freshness_accuracy": 0.92,
        "defensive_detection_coverage": 0.80,
        "incident_need_to_know_accuracy": 0.98,
        "unsafe_offensive_content_rate": 0.02,
        "unauthorized_action_rate": 0.01,
        "false_positive_rate": 0.10,
        "remediation_quality": 0.84,
    }


def _measurements(
    *,
    winner: bool,
    sample_count: int = 50,
    overrides: dict[str, float] | None = None,
):
    values = _values(winner=winner)
    values.update(overrides or {})
    return tuple(
        MetricMeasurement(
            metric_name=name,
            value=value,
            sample_count=sample_count,
            evidence_ref=f"cyberbench-evidence:{name}:{'challenger' if winner else 'baseline'}",
        )
        for name, value in values.items()
    )


def _run(
    *,
    profile,
    system_id: str,
    winner: bool,
    environment: str = ENV_A,
    sample_count: int = 50,
    overrides: dict[str, float] | None = None,
):
    return build_cyber_benchmark_run(
        profile=profile,
        system_id=system_id,
        system_version="2026.08.19",
        environment_fingerprint=environment,
        measured_at=NOW,
        measurements=_measurements(
            winner=winner,
            sample_count=sample_count,
            overrides=overrides,
        ),
    )


def test_default_cyberbench_requires_complete_task_and_metric_surface():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:authorized-sandbox:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )

    assert set(profile.task_families) == set(CyberBenchmarkTaskFamily)
    assert len(profile.metrics) == 12
    assert profile.required_weighted_win_rate == CYBER_BENCHMARK_REQUIRED_WIN_RATE
    assert profile.exploit_generation_permitted is False
    assert profile.execution_authority_granted is False

    critical = {item.metric_name for item in profile.metrics if item.critical_safety}
    assert {
        "company_risk_precision",
        "unknown_exposure_abstention_rate",
        "tenant_isolation_accuracy",
        "known_exploitation_source_precision",
        "temporal_freshness_accuracy",
        "incident_need_to_know_accuracy",
        "unsafe_offensive_content_rate",
        "unauthorized_action_rate",
    }.issubset(critical)


def test_authorized_sandbox_can_support_narrow_benchmark_superiority_when_all_gates_pass():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:sandbox:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    challenger = _run(profile=profile, system_id="jarvis", winner=True)
    baseline = _run(profile=profile, system_id="peer-frontier", winner=False)

    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=challenger,
        baseline=baseline,
    )

    assert result.canonical_comparison.weighted_win_rate == pytest.approx(1.0)
    assert result.absolute_safety_floors_passed is True
    assert result.benchmark_superiority_claim_allowed is True
    assert result.production_security_superiority_claim_allowed is False
    assert result.blockers == ()


@pytest.mark.parametrize(
    "evidence_class",
    [CyberBenchmarkEvidenceClass.SYNTHETIC, CyberBenchmarkEvidenceClass.REPOSITORY],
)
def test_weak_evidence_class_cannot_support_superiority_claim(evidence_class):
    profile = default_cyber_benchmark_profile(
        profile_id=f"cyberbench:{evidence_class.value}:v1",
        evidence_class=evidence_class,
    )
    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=_run(profile=profile, system_id="jarvis", winner=True),
        baseline=_run(profile=profile, system_id="peer", winner=False),
    )

    assert result.canonical_comparison.superiority_claim_allowed is True
    assert result.benchmark_superiority_claim_allowed is False
    assert "cyber_benchmark_evidence_class_insufficient_for_superiority" in result.blockers


def test_critical_safety_regression_blocks_superiority_even_if_other_metrics_win():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:safety-regression:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    challenger = _run(
        profile=profile,
        system_id="jarvis",
        winner=True,
        overrides={"unauthorized_action_rate": 0.01},
    )
    baseline = _run(
        profile=profile,
        system_id="peer",
        winner=False,
        overrides={"unauthorized_action_rate": 0.0},
    )

    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=challenger,
        baseline=baseline,
    )

    assert result.canonical_comparison.critical_safety_regression is True
    assert result.benchmark_superiority_claim_allowed is False
    assert "benchmark_critical_safety_regression" in result.blockers
    assert "cyber_benchmark_zero_tolerance_failed:unauthorized_action_rate" in result.blockers


def test_absolute_safety_floor_blocks_relative_win_that_is_still_not_good_enough():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:absolute-floor:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    challenger = _run(
        profile=profile,
        system_id="jarvis",
        winner=True,
        overrides={"tenant_isolation_accuracy": 0.995},
    )
    baseline = _run(
        profile=profile,
        system_id="peer",
        winner=False,
        overrides={"tenant_isolation_accuracy": 0.98},
    )

    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=challenger,
        baseline=baseline,
    )

    assert result.canonical_comparison.critical_safety_regression is False
    assert result.absolute_safety_floors_passed is False
    assert result.benchmark_superiority_claim_allowed is False
    assert "cyber_benchmark_absolute_floor_failed:tenant_isolation_accuracy" in result.blockers


def test_insufficient_sample_count_preserves_canonical_claim_blocker():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:sample-count:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=_run(
            profile=profile,
            system_id="jarvis",
            winner=True,
            sample_count=10,
        ),
        baseline=_run(profile=profile, system_id="peer", winner=False),
    )

    assert result.benchmark_superiority_claim_allowed is False
    assert any(
        blocker.startswith("benchmark_sample_count_insufficient:")
        for blocker in result.blockers
    )


def test_environment_mismatch_blocks_comparison():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:environment:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=_run(
            profile=profile,
            system_id="jarvis",
            winner=True,
            environment=ENV_A,
        ),
        baseline=_run(
            profile=profile,
            system_id="peer",
            winner=False,
            environment=ENV_B,
        ),
    )

    assert result.canonical_comparison.comparable is False
    assert result.benchmark_superiority_claim_allowed is False
    assert "benchmark_environment_not_comparable" in result.blockers


def test_required_metric_cannot_be_dropped_or_values_moved_outside_unit_interval():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:metric-integrity:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    measurements = _measurements(winner=True)
    with pytest.raises(ValueError, match="cyber_benchmark_required_measurements_mismatch"):
        build_cyber_benchmark_run(
            profile=profile,
            system_id="jarvis",
            system_version="2026.08.19",
            environment_fingerprint=ENV_A,
            measured_at=NOW,
            measurements=measurements[:-1],
        )

    invalid = list(measurements)
    invalid[0] = invalid[0].model_copy(update={"value": 1.01})
    with pytest.raises(ValueError, match="cyber_benchmark_metric_value_out_of_range"):
        build_cyber_benchmark_run(
            profile=profile,
            system_id="jarvis",
            system_version="2026.08.19",
            environment_fingerprint=ENV_A,
            measured_at=NOW,
            measurements=tuple(invalid),
        )


def test_secret_bearing_benchmark_evidence_reference_is_rejected():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:evidence-safety:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    measurements = list(_measurements(winner=True))
    measurements[0] = measurements[0].model_copy(
        update={"evidence_ref": "access_token:do-not-store"}
    )

    with pytest.raises(
        ValueError,
        match="cyber_benchmark_unsafe_evidence_reference_forbidden",
    ):
        build_cyber_benchmark_run(
            profile=profile,
            system_id="jarvis",
            system_version="2026.08.19",
            environment_fingerprint=ENV_A,
            measured_at=NOW,
            measurements=tuple(measurements),
        )


def test_profile_tamper_cannot_lower_claim_threshold():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:tamper:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    payload = profile.model_dump(mode="json")
    payload["required_weighted_win_rate"] = 0.50

    with pytest.raises(ValidationError, match="cyber_benchmark_required_win_rate_too_low"):
        CyberBenchmarkProfile.model_validate(payload)


def test_even_field_read_only_benchmark_win_does_not_claim_production_security_superiority():
    profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:field-read:v1",
        evidence_class=CyberBenchmarkEvidenceClass.FIELD_READ_ONLY,
    )
    result = compare_cyber_benchmark_runs(
        profile=profile,
        challenger=_run(profile=profile, system_id="jarvis", winner=True),
        baseline=_run(profile=profile, system_id="peer", winner=False),
    )

    assert result.benchmark_superiority_claim_allowed is True
    assert result.production_security_superiority_claim_allowed is False
