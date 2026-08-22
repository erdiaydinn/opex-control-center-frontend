from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.cyber_benchmark_evaluation_intelligence import (
    CYBER_BENCHMARK_MIN_CASES_PER_METRIC,
    CyberBenchmarkAdjudicationMethod,
    CyberBenchmarkCaseResult,
    CyberBenchmarkEvaluationReceipt,
    build_cyber_benchmark_case_result,
    compile_cyber_benchmark_evaluation,
    metric_direction,
    verify_cyber_benchmark_evaluation,
)
from app.cyber_benchmark_intelligence import (
    CyberBenchmarkEvidenceClass,
    default_cyber_benchmark_profile,
)
from app.jarvis_benchmark import MetricDirection

NOW = datetime(2026, 8, 19, 20, 30, tzinfo=UTC)
ENVIRONMENT = "e" * 64


def _profile():
    return default_cyber_benchmark_profile(
        profile_id="cyberbench:evaluation:v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )


def _case_fingerprint(metric_name: str, index: int) -> str:
    return hashlib.sha256(f"{metric_name}:{index}".encode()).hexdigest()


def _good_value(metric_name: str) -> float:
    if metric_name in {
        "unsafe_offensive_content_rate",
        "unauthorized_action_rate",
        "false_positive_rate",
    }:
        return 0.0
    return 1.0


def _case_result(
    *,
    profile,
    metric_name: str,
    index: int,
    system_id: str = "jarvis",
    environment_fingerprint: str = ENVIRONMENT,
    case_fingerprint: str | None = None,
):
    return build_cyber_benchmark_case_result(
        profile=profile,
        case_id=f"case:{metric_name}:{index:02d}",
        case_fingerprint=case_fingerprint or _case_fingerprint(metric_name, index),
        metric_name=metric_name,
        system_id=system_id,
        system_version="2026.08.19",
        environment_fingerprint=environment_fingerprint,
        observed_value=_good_value(metric_name),
        adjudication_method=CyberBenchmarkAdjudicationMethod.DETERMINISTIC,
        evidence_ref=f"cyberbench-evidence:{metric_name}:{index:02d}",
        adjudicator_ref="cyberbench-adjudicator:deterministic-v1",
        reviewed_at=NOW,
    )


def _results(*, profile=None, count: int = CYBER_BENCHMARK_MIN_CASES_PER_METRIC):
    profile = profile or _profile()
    return tuple(
        _case_result(profile=profile, metric_name=metric.metric_name, index=index)
        for metric in profile.metrics
        for index in range(count)
    )


def test_case_level_evidence_compiles_all_metrics_only_after_twenty_unique_cases_each():
    profile = _profile()
    receipt = compile_cyber_benchmark_evaluation(
        profile=profile,
        results=_results(profile=profile),
    )

    assert receipt.system_id == "jarvis"
    assert receipt.task_set_id == profile.task_set_id
    assert receipt.profile_fingerprint == profile.fingerprint
    assert receipt.min_cases_per_metric == CYBER_BENCHMARK_MIN_CASES_PER_METRIC
    assert len(receipt.case_result_fingerprints) == 20 * len(profile.metrics)
    assert len(receipt.metric_measurements) == len(profile.metrics) == 12
    assert all(item.sample_count == 20 for item in receipt.metric_measurements)
    assert receipt.all_required_metrics_present is True
    assert receipt.sample_floor_satisfied is True
    assert receipt.superiority_claim_authority_granted is False
    assert receipt.production_security_claim_authority_granted is False
    assert receipt.execution_authority_granted is False

    measurements = {item.metric_name: item.value for item in receipt.metric_measurements}
    assert measurements["tenant_isolation_accuracy"] == pytest.approx(1.0)
    assert measurements["unauthorized_action_rate"] == pytest.approx(0.0)
    assert measurements["unsafe_offensive_content_rate"] == pytest.approx(0.0)


def test_case_level_result_retains_only_refs_and_fingerprints_not_raw_model_material():
    profile = _profile()
    result = _results(profile=profile)[0]
    payload = result.model_dump(mode="json")

    assert "prompt" not in payload
    assert "model_output" not in payload
    assert result.raw_prompt_retained is False
    assert result.raw_model_output_retained is False
    assert result.credential_material_retained is False
    assert result.exploit_content_retained is False
    assert result.execution_authority_granted is False


def test_raw_output_exploit_or_credential_retention_is_forbidden():
    result = _results()[0]
    for field, expected in (
        ("raw_model_output_retained", "cyber_benchmark_case_raw_output_retention_forbidden"),
        ("credential_material_retained", "cyber_benchmark_case_credential_retention_forbidden"),
        ("exploit_content_retained", "cyber_benchmark_case_exploit_content_retention_forbidden"),
    ):
        payload = result.model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError, match=expected):
            CyberBenchmarkCaseResult.model_validate(payload)


def test_secret_bearing_evidence_reference_is_rejected_at_case_boundary():
    profile = _profile()
    with pytest.raises(ValueError, match="cyber_benchmark_case_unsafe_reference_forbidden"):
        build_cyber_benchmark_case_result(
            profile=profile,
            case_id="case:tenant:01",
            case_fingerprint="a" * 64,
            metric_name="tenant_isolation_accuracy",
            system_id="jarvis",
            system_version="2026.08.19",
            environment_fingerprint=ENVIRONMENT,
            observed_value=1.0,
            adjudication_method=CyberBenchmarkAdjudicationMethod.DETERMINISTIC,
            evidence_ref="access_token:must-not-enter-benchmark",
            adjudicator_ref="cyberbench-adjudicator:deterministic-v1",
            reviewed_at=NOW,
        )


def test_missing_metric_cannot_be_hidden_by_aggregate_scores():
    profile = _profile()
    results = tuple(
        item
        for item in _results(profile=profile)
        if item.metric_name != "tenant_isolation_accuracy"
    )
    with pytest.raises(
        ValueError,
        match="cyber_benchmark_evaluation_required_metrics_mismatch",
    ):
        compile_cyber_benchmark_evaluation(profile=profile, results=results)


def test_metric_with_fewer_than_twenty_unique_cases_fails_closed():
    profile = _profile()
    results = [
        item
        for item in _results(profile=profile)
        if not (
            item.metric_name == "company_risk_precision"
            and item.case_id.endswith(":19")
        )
    ]
    with pytest.raises(
        ValueError,
        match="cyber_benchmark_evaluation_sample_floor_not_met:company_risk_precision",
    ):
        compile_cyber_benchmark_evaluation(profile=profile, results=tuple(results))


def test_minimum_case_floor_cannot_be_weakened_below_twenty():
    profile = _profile()
    with pytest.raises(ValueError, match="cyber_benchmark_evaluation_min_cases_too_low"):
        compile_cyber_benchmark_evaluation(
            profile=profile,
            results=_results(profile=profile),
            min_cases_per_metric=19,
        )


def test_duplicate_case_fingerprint_cannot_inflate_sample_count():
    profile = _profile()
    results = list(_results(profile=profile))
    first = results[0]
    second = results[1]
    results[1] = _case_result(
        profile=profile,
        metric_name=second.metric_name,
        index=1,
        case_fingerprint=first.case_fingerprint,
    )
    with pytest.raises(
        ValueError,
        match="cyber_benchmark_evaluation_duplicate_case_fingerprint",
    ):
        compile_cyber_benchmark_evaluation(profile=profile, results=tuple(results))


def test_mixed_system_or_environment_results_cannot_be_combined():
    profile = _profile()
    results = list(_results(profile=profile))
    last = results[-1]
    results[-1] = _case_result(
        profile=profile,
        metric_name=last.metric_name,
        index=19,
        system_id="peer-frontier",
    )
    with pytest.raises(
        ValueError,
        match="cyber_benchmark_evaluation_system_or_environment_mismatch",
    ):
        compile_cyber_benchmark_evaluation(profile=profile, results=tuple(results))


def test_profile_binding_cannot_be_swapped_after_case_adjudication():
    profile = _profile()
    other_profile = default_cyber_benchmark_profile(
        profile_id="cyberbench:evaluation:other-v1",
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    results = list(_results(profile=profile))
    first = results[0]
    results[0] = _case_result(
        profile=other_profile,
        metric_name=first.metric_name,
        index=0,
    )
    with pytest.raises(ValueError, match="cyber_benchmark_evaluation_profile_mismatch"):
        compile_cyber_benchmark_evaluation(profile=profile, results=tuple(results))


def test_metric_direction_is_derived_from_profile_not_model_claim():
    profile = _profile()
    assert metric_direction(
        profile=profile,
        metric_name="tenant_isolation_accuracy",
    ) is MetricDirection.HIGHER_IS_BETTER
    assert metric_direction(
        profile=profile,
        metric_name="unauthorized_action_rate",
    ) is MetricDirection.LOWER_IS_BETTER


def test_evaluation_receipt_never_self_grants_superiority_or_production_claim():
    profile = _profile()
    receipt = compile_cyber_benchmark_evaluation(
        profile=profile,
        results=_results(profile=profile),
    )
    for field, expected in (
        (
            "superiority_claim_authority_granted",
            "cyber_benchmark_evaluation_never_grants_superiority_claim",
        ),
        (
            "production_security_claim_authority_granted",
            "cyber_benchmark_evaluation_never_grants_production_claim",
        ),
    ):
        payload = receipt.model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError, match=expected):
            CyberBenchmarkEvaluationReceipt.model_validate(payload)


def test_tampered_evaluation_fails_fingerprint_verification():
    profile = _profile()
    receipt = compile_cyber_benchmark_evaluation(
        profile=profile,
        results=_results(profile=profile),
    )
    tampered = receipt.model_copy(update={"system_version": "tampered"})
    with pytest.raises(
        ValidationError,
        match="cyber_benchmark_evaluation_fingerprint_mismatch",
    ):
        verify_cyber_benchmark_evaluation(receipt=tampered)
