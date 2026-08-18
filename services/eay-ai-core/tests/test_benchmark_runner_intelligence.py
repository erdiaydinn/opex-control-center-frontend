import asyncio
import json
from datetime import datetime, timezone

import pytest

from app.benchmark_runner import (
    CANONICAL_AGENT_METRICS,
    BenchmarkCaseOutcome,
    BenchmarkEnvironmentManifest,
    BenchmarkEvidenceArtifact,
    BenchmarkSystemAdapter,
    BenchmarkTaskCase,
    BenchmarkTaskSuite,
    MeasuredBenchmarkResult,
    build_verified_promotion_from_measured_results,
    run_same_task_benchmark,
    run_system_benchmark,
    write_benchmark_evidence_artifact,
)


def _suite(count=20):
    return BenchmarkTaskSuite(
        task_set_id="eay-enterprise-agent-bench-v1",
        cases=tuple(
            BenchmarkTaskCase(
                case_id=f"inventory-{index:02d}",
                prompt=f"SENSITIVE BENCHMARK PROMPT {index}: adjust verified synthetic inventory",
                category="inventory-write",
                side_effect=True,
                expected_evaluator_ref="evaluator://inventory-authoritative-readback-v1",
            )
            for index in range(count)
        ),
    )


def _environment():
    return BenchmarkEnvironmentManifest(
        environment_id="synthetic-enterprise-vm-v1",
        components={
            "browser": "chromium-managed",
            "portal_fixture": "inventory-v1",
            "network_profile": "stable-50ms",
        },
    )


def _good_adapter(system_id="jarvis"):
    async def invoke(case):
        return BenchmarkCaseOutcome(
            task_success=True,
            effect_verified=True,
            silent_wrong_action=False,
            duplicate_action=False,
            evidence_refs=(f"evidence://{system_id}/{case.case_id}/verified",),
        )

    return BenchmarkSystemAdapter(
        system_id=system_id,
        system_version="v1",
        invoke=invoke,
    )


def _weak_adapter(system_id="peer"):
    async def invoke(case):
        index = int(case.case_id.rsplit("-", 1)[1])
        return BenchmarkCaseOutcome(
            task_success=(index % 2 == 0),
            effect_verified=(index % 4 == 0),
            silent_wrong_action=(index % 5 == 0),
            duplicate_action=(index % 7 == 0),
            evidence_refs=(f"evidence://{system_id}/{case.case_id}/observed",),
        )

    return BenchmarkSystemAdapter(
        system_id=system_id,
        system_version="v1",
        invoke=invoke,
    )


def _measurement(run, name):
    return next(item for item in run.measurements if item.metric_name == name)


def _measured_pair():
    return asyncio.run(
        run_same_task_benchmark(
            adapters=(_good_adapter("jarvis"), _weak_adapter("peer")),
            suite=_suite(),
            environment=_environment(),
            measured_at=datetime(2026, 8, 18, 6, 30, tzinfo=timezone.utc),
        )
    )


def test_same_task_runner_produces_comparable_fingerprints_and_evidence_bound_runs():
    jarvis, peer = _measured_pair()
    assert jarvis.run.task_set_fingerprint == peer.run.task_set_fingerprint
    assert jarvis.run.environment_fingerprint == peer.run.environment_fingerprint
    assert len(jarvis.evidence.records) == 20
    assert _measurement(jarvis.run, "task_success").value == 1.0
    assert _measurement(jarvis.run, "effect_verification_coverage").value == 1.0
    assert _measurement(jarvis.run, "silent_wrong_action_rate").value == 0.0
    assert _measurement(jarvis.run, "duplicate_action_rate").value == 0.0
    assert _measurement(peer.run, "task_success").value < 0.5
    assert _measurement(peer.run, "effect_verification_coverage").value < 1.0
    assert jarvis.run.measurements[0].evidence_ref == jarvis.evidence.evidence_ref


def test_side_effect_claimed_success_without_effect_verification_is_counted_as_failure():
    async def invoke(case):
        return BenchmarkCaseOutcome(
            task_success=True,
            effect_verified=False,
            evidence_refs=("evidence://toast-said-success",),
        )

    clock_values = iter((10.0, 10.4))
    result = asyncio.run(
        run_system_benchmark(
            adapter=BenchmarkSystemAdapter("unsafe-peer", "v1", invoke),
            suite=BenchmarkTaskSuite(task_set_id="single", cases=(_suite(1).cases[0],)),
            environment=_environment(),
            measured_at=datetime(2026, 8, 18, 6, 31, tzinfo=timezone.utc),
            clock=lambda: next(clock_values),
        )
    )

    record = result.evidence.records[0]
    assert record.task_success is False
    assert record.effect_verified is False
    assert record.error_code == "side_effect_success_without_effect_verification"
    assert _measurement(result.run, "task_success").value == 0.0
    assert _measurement(result.run, "effect_verification_coverage").value == 0.0


def test_measured_runs_feed_replay_verified_promotion_without_manual_scores():
    jarvis, peer = _measured_pair()
    promotion = build_verified_promotion_from_measured_results(
        engine_id="jarvis",
        challenger=jarvis,
        baselines=(peer,),
        metrics=CANONICAL_AGENT_METRICS,
        generated_at=datetime(2026, 8, 18, 6, 33, tzinfo=timezone.utc),
    )

    attestation = promotion.attestation
    assert attestation.promotion_allowed is True
    assert attestation.minimum_sample_count == 20
    assert attestation.critical_safety_regression is False
    assert jarvis.evidence.evidence_ref in attestation.measurement_evidence_refs
    assert attestation.evidence_ref.startswith("benchmark://")
    assert promotion.challenger == jarvis.run


def test_evidence_record_tamper_with_old_fingerprint_is_rejected():
    jarvis, _ = _measured_pair()
    payload = jarvis.evidence.model_dump(mode="json")
    payload["records"][0]["task_success"] = False

    with pytest.raises(ValueError, match="benchmark_evidence_artifact_fingerprint_mismatch"):
        BenchmarkEvidenceArtifact.model_validate(payload)


def test_aggregate_score_tamper_against_real_case_evidence_is_rejected():
    jarvis, _ = _measured_pair()
    measurements = list(jarvis.run.measurements)
    measurements[0] = measurements[0].model_copy(update={"value": 0.25})
    forged_run = jarvis.run.model_copy(update={"measurements": tuple(measurements)})

    with pytest.raises(ValueError, match="benchmark_result_measurements_not_reproducible_from_case_evidence"):
        MeasuredBenchmarkResult(run=forged_run, evidence=jarvis.evidence)


def test_persisted_evidence_artifact_contains_no_prompts(tmp_path):
    suite = _suite(1)
    result = asyncio.run(
        run_system_benchmark(
            adapter=_good_adapter("jarvis"),
            suite=suite,
            environment=_environment(),
            measured_at=datetime(2026, 8, 18, 6, 34, tzinfo=timezone.utc),
        )
    )
    path = tmp_path / "jarvis-benchmark.json"
    write_benchmark_evidence_artifact(path, result.evidence)
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert "SENSITIVE BENCHMARK PROMPT" not in raw
    assert payload["prompts_retained"] is False
    assert payload["artifact_fingerprint"] == result.evidence.artifact_fingerprint
    assert payload["records"][0]["case_id"] == suite.cases[0].case_id


def test_environment_manifest_rejects_secret_like_fields():
    with pytest.raises(ValueError, match="benchmark_environment_secret_like_key_forbidden"):
        BenchmarkEnvironmentManifest(
            environment_id="bad",
            components={"OPENAI_API_KEY": "must-never-be-fingerprinted"},
        )


def test_system_adapter_exception_is_sanitized_to_type_only_evidence():
    async def invoke(case):
        raise RuntimeError("raw-sensitive-error-detail")

    result = asyncio.run(
        run_system_benchmark(
            adapter=BenchmarkSystemAdapter("broken", "v1", invoke),
            suite=_suite(1),
            environment=_environment(),
            measured_at=datetime(2026, 8, 18, 6, 35, tzinfo=timezone.utc),
        )
    )
    serialized = result.model_dump_json()

    assert result.evidence.records[0].error_code == "system_adapter_error:RuntimeError"
    assert "raw-sensitive-error-detail" not in serialized
    assert "benchmark-error://broken/inventory-00/RuntimeError" in serialized
