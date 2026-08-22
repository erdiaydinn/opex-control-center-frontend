"""Measured same-task benchmark runner for Jarvis and peer intelligence systems.

Every system is run against the same immutable task corpus and environment.
Case-level evidence is deterministically fingerprinted, aggregate measurements
are replayed from those records, and only a source-consistent measured result
can feed a verified engine-promotion bundle. Prompts and secrets are never
retained in benchmark artifacts.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from pydantic import BaseModel, Field, model_validator

from .jarvis_benchmark import (
    BenchmarkMetric,
    BenchmarkRun,
    MetricDirection,
    MetricMeasurement,
)

BENCHMARK_RUNNER_CONTRACT = "eay-benchmark-runner-v1"


CANONICAL_AGENT_METRICS = (
    BenchmarkMetric(
        metric_name="task_success",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=4.0,
    ),
    BenchmarkMetric(
        metric_name="silent_wrong_action_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=10.0,
        critical_safety=True,
    ),
    BenchmarkMetric(
        metric_name="effect_verification_coverage",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=8.0,
        critical_safety=True,
    ),
    BenchmarkMetric(
        metric_name="duplicate_action_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=8.0,
        critical_safety=True,
    ),
    BenchmarkMetric(
        metric_name="mean_latency_seconds",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=1.0,
    ),
)

_SECRET_MARKERS = ("secret", "token", "password", "credential", "api_key", "apikey", "private_key")


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class BenchmarkTaskCase(BaseModel):
    case_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=30000)
    category: str = Field(min_length=1)
    side_effect: bool = False
    expected_evaluator_ref: str = Field(min_length=1)


class BenchmarkTaskSuite(BaseModel):
    contract: str = BENCHMARK_RUNNER_CONTRACT
    task_set_id: str = Field(min_length=1)
    cases: tuple[BenchmarkTaskCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> "BenchmarkTaskSuite":
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark_runner_case_ids_must_be_unique")
        return self

    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class BenchmarkEnvironmentManifest(BaseModel):
    contract: str = BENCHMARK_RUNNER_CONTRACT
    environment_id: str = Field(min_length=1)
    components: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def environment_contains_no_secret_material(self) -> "BenchmarkEnvironmentManifest":
        for key, value in self.components.items():
            normalized_key = key.casefold().replace("-", "_")
            if any(marker in normalized_key for marker in _SECRET_MARKERS):
                raise ValueError("benchmark_environment_secret_like_key_forbidden")
            if not str(value).strip():
                raise ValueError("benchmark_environment_component_value_required")
        return self

    def fingerprint(self) -> str:
        return _fingerprint(self.model_dump(mode="json"))


class BenchmarkCaseOutcome(BaseModel):
    task_success: bool
    silent_wrong_action: bool = False
    effect_verified: bool = False
    duplicate_action: bool = False
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    error_code: str | None = None

    @model_validator(mode="after")
    def evidence_is_unique(self) -> "BenchmarkCaseOutcome":
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("benchmark_case_evidence_refs_must_be_unique")
        return self


class BenchmarkCaseRecord(BaseModel):
    case_id: str
    category: str
    side_effect: bool
    task_success: bool
    silent_wrong_action: bool
    effect_verified: bool
    duplicate_action: bool
    latency_seconds: float = Field(ge=0.0)
    evidence_refs: tuple[str, ...]
    error_code: str | None = None
    prompt_retained: bool = False

    @model_validator(mode="after")
    def no_prompt_retention(self) -> "BenchmarkCaseRecord":
        if self.prompt_retained:
            raise ValueError("benchmark_case_record_cannot_retain_prompt")
        return self


class BenchmarkEvidenceArtifact(BaseModel):
    contract: str = BENCHMARK_RUNNER_CONTRACT
    system_id: str
    system_version: str
    task_set_id: str
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[BenchmarkCaseRecord, ...] = Field(min_length=1)
    artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_ref: str
    prompts_retained: bool = False

    @model_validator(mode="after")
    def artifact_is_payload_bound(self) -> "BenchmarkEvidenceArtifact":
        if self.prompts_retained:
            raise ValueError("benchmark_artifact_cannot_retain_prompts")
        payload = {
            "contract": BENCHMARK_RUNNER_CONTRACT,
            "system_id": self.system_id,
            "system_version": self.system_version,
            "task_set_id": self.task_set_id,
            "task_set_fingerprint": self.task_set_fingerprint,
            "environment_fingerprint": self.environment_fingerprint,
            "records": [item.model_dump(mode="json") for item in self.records],
        }
        expected = _fingerprint(payload)
        if self.artifact_fingerprint != expected:
            raise ValueError("benchmark_evidence_artifact_fingerprint_mismatch")
        if self.evidence_ref != f"benchmark-evidence://{expected}":
            raise ValueError("benchmark_evidence_ref_fingerprint_mismatch")
        return self


def _aggregate_measurements(
    records: tuple[BenchmarkCaseRecord, ...],
    *,
    evidence_ref: str,
) -> tuple[MetricMeasurement, ...]:
    sample_count = len(records)
    if sample_count < 1:
        raise ValueError("benchmark_measurement_requires_records")
    successes = sum(item.task_success for item in records)
    silent_wrong = sum(item.silent_wrong_action for item in records)
    duplicates = sum(item.duplicate_action for item in records)
    side_effect_records = tuple(item for item in records if item.side_effect)
    verified_side_effects = sum(item.effect_verified for item in side_effect_records)
    effect_denominator = len(side_effect_records)
    mean_latency = sum(item.latency_seconds for item in records) / sample_count

    return (
        MetricMeasurement(
            metric_name="task_success",
            value=successes / sample_count,
            sample_count=sample_count,
            evidence_ref=evidence_ref,
        ),
        MetricMeasurement(
            metric_name="silent_wrong_action_rate",
            value=silent_wrong / sample_count,
            sample_count=sample_count,
            evidence_ref=evidence_ref,
        ),
        MetricMeasurement(
            metric_name="effect_verification_coverage",
            value=(verified_side_effects / effect_denominator if effect_denominator else 1.0),
            sample_count=sample_count,
            evidence_ref=evidence_ref,
        ),
        MetricMeasurement(
            metric_name="duplicate_action_rate",
            value=duplicates / sample_count,
            sample_count=sample_count,
            evidence_ref=evidence_ref,
        ),
        MetricMeasurement(
            metric_name="mean_latency_seconds",
            value=mean_latency,
            sample_count=sample_count,
            evidence_ref=evidence_ref,
        ),
    )


class MeasuredBenchmarkResult(BaseModel):
    contract: str = BENCHMARK_RUNNER_CONTRACT
    run: BenchmarkRun
    evidence: BenchmarkEvidenceArtifact

    @model_validator(mode="after")
    def run_and_evidence_match(self) -> "MeasuredBenchmarkResult":
        if self.run.system_id != self.evidence.system_id:
            raise ValueError("benchmark_result_system_identity_mismatch")
        if self.run.system_version != self.evidence.system_version:
            raise ValueError("benchmark_result_system_version_mismatch")
        if self.run.task_set_id != self.evidence.task_set_id:
            raise ValueError("benchmark_result_task_set_identity_mismatch")
        if self.run.task_set_fingerprint != self.evidence.task_set_fingerprint:
            raise ValueError("benchmark_result_task_set_fingerprint_mismatch")
        if self.run.environment_fingerprint != self.evidence.environment_fingerprint:
            raise ValueError("benchmark_result_environment_fingerprint_mismatch")
        replayed = _aggregate_measurements(
            self.evidence.records,
            evidence_ref=self.evidence.evidence_ref,
        )
        if self.run.measurements != replayed:
            raise ValueError("benchmark_result_measurements_not_reproducible_from_case_evidence")
        return self


SystemInvoke = Callable[[BenchmarkTaskCase], Awaitable[BenchmarkCaseOutcome]]
Clock = Callable[[], float]


@dataclass(frozen=True)
class BenchmarkSystemAdapter:
    system_id: str
    system_version: str
    invoke: SystemInvoke

    def __post_init__(self) -> None:
        if not self.system_id.strip() or not self.system_version.strip():
            raise ValueError("benchmark_system_identity_required")


async def run_system_benchmark(
    *,
    adapter: BenchmarkSystemAdapter,
    suite: BenchmarkTaskSuite,
    environment: BenchmarkEnvironmentManifest,
    measured_at,
    clock: Clock = time.perf_counter,
) -> MeasuredBenchmarkResult:
    records: list[BenchmarkCaseRecord] = []
    for case in suite.cases:
        start = clock()
        try:
            outcome = await adapter.invoke(case)
        except Exception as exc:
            end = clock()
            records.append(
                BenchmarkCaseRecord(
                    case_id=case.case_id,
                    category=case.category,
                    side_effect=case.side_effect,
                    task_success=False,
                    silent_wrong_action=False,
                    effect_verified=False,
                    duplicate_action=False,
                    latency_seconds=max(0.0, end - start),
                    evidence_refs=(f"benchmark-error://{adapter.system_id}/{case.case_id}/{type(exc).__name__}",),
                    error_code=f"system_adapter_error:{type(exc).__name__}",
                )
            )
            continue
        end = clock()
        effective_success = outcome.task_success and (
            not case.side_effect or outcome.effect_verified
        )
        records.append(
            BenchmarkCaseRecord(
                case_id=case.case_id,
                category=case.category,
                side_effect=case.side_effect,
                task_success=effective_success,
                silent_wrong_action=outcome.silent_wrong_action,
                effect_verified=outcome.effect_verified if case.side_effect else False,
                duplicate_action=outcome.duplicate_action,
                latency_seconds=max(0.0, end - start),
                evidence_refs=outcome.evidence_refs,
                error_code=(
                    outcome.error_code
                    if effective_success == outcome.task_success
                    else "side_effect_success_without_effect_verification"
                ),
            )
        )

    record_tuple = tuple(records)
    evidence_payload = {
        "contract": BENCHMARK_RUNNER_CONTRACT,
        "system_id": adapter.system_id,
        "system_version": adapter.system_version,
        "task_set_id": suite.task_set_id,
        "task_set_fingerprint": suite.fingerprint(),
        "environment_fingerprint": environment.fingerprint(),
        "records": [item.model_dump(mode="json") for item in record_tuple],
    }
    artifact_fingerprint = _fingerprint(evidence_payload)
    evidence_ref = f"benchmark-evidence://{artifact_fingerprint}"
    evidence = BenchmarkEvidenceArtifact(
        system_id=adapter.system_id,
        system_version=adapter.system_version,
        task_set_id=suite.task_set_id,
        task_set_fingerprint=suite.fingerprint(),
        environment_fingerprint=environment.fingerprint(),
        records=record_tuple,
        artifact_fingerprint=artifact_fingerprint,
        evidence_ref=evidence_ref,
    )
    run = BenchmarkRun(
        system_id=adapter.system_id,
        system_version=adapter.system_version,
        task_set_id=suite.task_set_id,
        task_set_fingerprint=suite.fingerprint(),
        environment_fingerprint=environment.fingerprint(),
        measured_at=measured_at,
        measurements=_aggregate_measurements(record_tuple, evidence_ref=evidence_ref),
    )
    return MeasuredBenchmarkResult(run=run, evidence=evidence)


async def run_same_task_benchmark(
    *,
    adapters: tuple[BenchmarkSystemAdapter, ...],
    suite: BenchmarkTaskSuite,
    environment: BenchmarkEnvironmentManifest,
    measured_at,
) -> tuple[MeasuredBenchmarkResult, ...]:
    if len(adapters) < 2:
        raise ValueError("same_task_benchmark_requires_multiple_systems")
    identities = [(item.system_id, item.system_version) for item in adapters]
    if len(identities) != len(set(identities)):
        raise ValueError("same_task_benchmark_system_identities_must_be_unique")
    results: list[MeasuredBenchmarkResult] = []
    for adapter in adapters:
        results.append(
            await run_system_benchmark(
                adapter=adapter,
                suite=suite,
                environment=environment,
                measured_at=measured_at,
            )
        )
    return tuple(results)


def build_verified_promotion_from_measured_results(
    *,
    engine_id: str,
    challenger: MeasuredBenchmarkResult,
    baselines: tuple[MeasuredBenchmarkResult, ...],
    metrics: tuple[BenchmarkMetric, ...] = CANONICAL_AGENT_METRICS,
    required_weighted_win_rate: float = 0.80,
    generated_at=None,
):
    """Convert case-evidence-bound measured results into registry promotion."""
    if challenger.run.system_id != engine_id:
        raise ValueError("measured_promotion_engine_id_mismatch")
    if not baselines:
        raise ValueError("measured_promotion_requires_baseline")
    task_fp = challenger.run.task_set_fingerprint
    env_fp = challenger.run.environment_fingerprint
    for baseline in baselines:
        if baseline.run.task_set_fingerprint != task_fp:
            raise ValueError("measured_promotion_task_set_not_comparable")
        if baseline.run.environment_fingerprint != env_fp:
            raise ValueError("measured_promotion_environment_not_comparable")
    from .benchmark_promotion import build_verified_engine_benchmark_promotion

    return build_verified_engine_benchmark_promotion(
        engine_id=engine_id,
        challenger=challenger.run,
        baselines=tuple(item.run for item in baselines),
        metrics=metrics,
        required_weighted_win_rate=required_weighted_win_rate,
        generated_at=generated_at,
    )


def write_benchmark_evidence_artifact(
    path: Path,
    artifact: BenchmarkEvidenceArtifact,
) -> None:
    """Atomically persist a secret/prompt-free benchmark evidence artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        artifact.model_dump_json(indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
