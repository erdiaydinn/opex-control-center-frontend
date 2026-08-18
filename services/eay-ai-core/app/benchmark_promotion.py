"""Evidence-bound benchmark promotion artifacts for Jarvis engine activation.

A deployment benchmark is not a manually typed score. Promotion artifacts are
built from comparable BenchmarkRun objects on the same task set/environment.
Registry admission uses a replay-verifiable bundle containing the source runs
and metric definitions, so a shape-valid hand-authored attestation is never
sufficient to activate a frontier engine.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from .jarvis_benchmark import (
    BenchmarkComparison,
    BenchmarkMetric,
    BenchmarkRun,
    MIN_CLAIM_SAMPLE_COUNT,
    compare_benchmark_runs,
)

BENCHMARK_PROMOTION_CONTRACT = "eay-engine-benchmark-promotion-v1"
VERIFIED_BENCHMARK_PROMOTION_CONTRACT = "eay-verified-engine-benchmark-promotion-v1"


class EngineBenchmarkAttestation(BaseModel):
    contract: str = BENCHMARK_PROMOTION_CONTRACT
    engine_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    task_set_id: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_score: float = Field(ge=0.0, le=1.0)
    evidence_ref: str = Field(pattern=r"^benchmark://[0-9a-f]{64}$")
    artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    baseline_system_ids: tuple[str, ...] = Field(min_length=1)
    measurement_evidence_refs: tuple[str, ...] = Field(min_length=1)
    minimum_sample_count: int = Field(ge=MIN_CLAIM_SAMPLE_COUNT)
    critical_safety_regression: bool = False
    promotion_allowed: bool
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def attestation_is_internally_consistent(self) -> "EngineBenchmarkAttestation":
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("benchmark_attestation_requires_timezone")
        if self.evidence_ref != f"benchmark://{self.artifact_fingerprint}":
            raise ValueError("benchmark_attestation_evidence_ref_fingerprint_mismatch")
        if self.promotion_allowed and (self.blockers or self.critical_safety_regression):
            raise ValueError("benchmark_attestation_cannot_promote_with_blockers")
        return self


def _measurement_refs(run: BenchmarkRun) -> tuple[str, ...]:
    return tuple(sorted({item.evidence_ref for item in run.measurements}))


def _canonical_fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_engine_benchmark_attestation(
    *,
    engine_id: str,
    challenger: BenchmarkRun,
    baselines: tuple[BenchmarkRun, ...],
    metrics: tuple[BenchmarkMetric, ...],
    required_weighted_win_rate: float = 0.80,
    generated_at: datetime | None = None,
) -> EngineBenchmarkAttestation:
    if not engine_id.strip():
        raise ValueError("benchmark_attestation_engine_id_required")
    if challenger.system_id != engine_id:
        raise ValueError("benchmark_attestation_challenger_engine_mismatch")
    if not baselines:
        raise ValueError("benchmark_attestation_requires_baseline")
    if not metrics:
        raise ValueError("benchmark_attestation_requires_metrics")

    comparisons: list[BenchmarkComparison] = []
    blockers: list[str] = []
    minimum_sample_count = min(
        item.sample_count
        for run in (challenger, *baselines)
        for item in run.measurements
    )

    if minimum_sample_count < MIN_CLAIM_SAMPLE_COUNT:
        blockers.append("benchmark_attestation_sample_floor_below_minimum")

    for baseline in baselines:
        comparison = compare_benchmark_runs(
            challenger=challenger,
            baseline=baseline,
            metrics=metrics,
            required_weighted_win_rate=required_weighted_win_rate,
        )
        comparisons.append(comparison)
        blockers.extend(comparison.blockers)
        if not comparison.comparable:
            blockers.append(f"benchmark_attestation_not_comparable:{baseline.system_id}")
        if not comparison.superiority_claim_allowed:
            blockers.append(f"benchmark_attestation_baseline_not_beaten:{baseline.system_id}")

    critical_safety_regression = any(item.critical_safety_regression for item in comparisons)
    if critical_safety_regression:
        blockers.append("benchmark_attestation_critical_safety_regression")

    benchmark_score = min(item.weighted_win_rate for item in comparisons)
    measurement_evidence_refs = tuple(
        sorted(
            {
                ref
                for run in (challenger, *baselines)
                for ref in _measurement_refs(run)
            }
        )
    )
    if not measurement_evidence_refs:
        blockers.append("benchmark_attestation_measurement_evidence_missing")

    blockers = list(dict.fromkeys(blockers))
    generated = generated_at or datetime.now(timezone.utc)
    if generated.tzinfo is None or generated.utcoffset() is None:
        raise ValueError("benchmark_attestation_requires_timezone")

    fingerprint_payload = {
        "contract": BENCHMARK_PROMOTION_CONTRACT,
        "engine_id": engine_id,
        "challenger": challenger.model_dump(mode="json"),
        "baselines": [item.model_dump(mode="json") for item in baselines],
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "required_weighted_win_rate": required_weighted_win_rate,
        "measurement_evidence_refs": measurement_evidence_refs,
    }
    artifact_fingerprint = _canonical_fingerprint(fingerprint_payload)

    return EngineBenchmarkAttestation(
        engine_id=engine_id,
        system_version=challenger.system_version,
        task_set_id=challenger.task_set_id,
        task_set_fingerprint=challenger.task_set_fingerprint,
        environment_fingerprint=challenger.environment_fingerprint,
        benchmark_score=benchmark_score,
        evidence_ref=f"benchmark://{artifact_fingerprint}",
        artifact_fingerprint=artifact_fingerprint,
        generated_at=generated,
        baseline_system_ids=tuple(item.system_id for item in baselines),
        measurement_evidence_refs=measurement_evidence_refs,
        minimum_sample_count=minimum_sample_count,
        critical_safety_regression=critical_safety_regression,
        promotion_allowed=not blockers,
        blockers=tuple(blockers),
    )


class VerifiedEngineBenchmarkPromotion(BaseModel):
    """Source-replayable promotion bundle accepted by the engine registry."""

    contract: str = VERIFIED_BENCHMARK_PROMOTION_CONTRACT
    attestation: EngineBenchmarkAttestation
    challenger: BenchmarkRun
    baselines: tuple[BenchmarkRun, ...] = Field(min_length=1)
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1)
    required_weighted_win_rate: float = Field(default=0.80, ge=0.5, le=1.0)
    verification_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def source_runs_must_reproduce_attestation(self) -> "VerifiedEngineBenchmarkPromotion":
        rebuilt = build_engine_benchmark_attestation(
            engine_id=self.attestation.engine_id,
            challenger=self.challenger,
            baselines=self.baselines,
            metrics=self.metrics,
            required_weighted_win_rate=self.required_weighted_win_rate,
            generated_at=self.attestation.generated_at,
        )
        if rebuilt != self.attestation:
            raise ValueError("verified_benchmark_promotion_attestation_not_reproducible")
        expected = _canonical_fingerprint(
            {
                "contract": VERIFIED_BENCHMARK_PROMOTION_CONTRACT,
                "attestation": rebuilt.model_dump(mode="json"),
                "challenger": self.challenger.model_dump(mode="json"),
                "baselines": [item.model_dump(mode="json") for item in self.baselines],
                "metrics": [item.model_dump(mode="json") for item in self.metrics],
                "required_weighted_win_rate": self.required_weighted_win_rate,
            }
        )
        if self.verification_fingerprint != expected:
            raise ValueError("verified_benchmark_promotion_fingerprint_mismatch")
        return self


def build_verified_engine_benchmark_promotion(
    *,
    engine_id: str,
    challenger: BenchmarkRun,
    baselines: tuple[BenchmarkRun, ...],
    metrics: tuple[BenchmarkMetric, ...],
    required_weighted_win_rate: float = 0.80,
    generated_at: datetime | None = None,
) -> VerifiedEngineBenchmarkPromotion:
    attestation = build_engine_benchmark_attestation(
        engine_id=engine_id,
        challenger=challenger,
        baselines=baselines,
        metrics=metrics,
        required_weighted_win_rate=required_weighted_win_rate,
        generated_at=generated_at,
    )
    verification_fingerprint = _canonical_fingerprint(
        {
            "contract": VERIFIED_BENCHMARK_PROMOTION_CONTRACT,
            "attestation": attestation.model_dump(mode="json"),
            "challenger": challenger.model_dump(mode="json"),
            "baselines": [item.model_dump(mode="json") for item in baselines],
            "metrics": [item.model_dump(mode="json") for item in metrics],
            "required_weighted_win_rate": required_weighted_win_rate,
        }
    )
    return VerifiedEngineBenchmarkPromotion(
        attestation=attestation,
        challenger=challenger,
        baselines=baselines,
        metrics=metrics,
        required_weighted_win_rate=required_weighted_win_rate,
        verification_fingerprint=verification_fingerprint,
    )
