"""Evidence-bound benchmark comparison for Jarvis versus peer systems.

There is no self-assigned 10/10 or 11/10 score in this contract.  A superiority
claim is allowed only from comparable measured runs on the same task set and
environment, with sufficient samples, evidence references, and no regression
on critical safety metrics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

JARVIS_BENCHMARK_CONTRACT = "eay-jarvis-benchmark-v1"
MIN_CLAIM_SAMPLE_COUNT = 20


class MetricDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class BenchmarkMetric(BaseModel):
    metric_name: str = Field(min_length=1)
    direction: MetricDirection
    weight: float = Field(gt=0.0, le=10.0)
    critical_safety: bool = False


class MetricMeasurement(BaseModel):
    metric_name: str = Field(min_length=1)
    value: float
    sample_count: int = Field(ge=1)
    evidence_ref: str = Field(min_length=1)


class BenchmarkRun(BaseModel):
    contract: str = JARVIS_BENCHMARK_CONTRACT
    system_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    task_set_id: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    measured_at: datetime
    measurements: tuple[MetricMeasurement, ...]

    @model_validator(mode="after")
    def measured_run_is_valid(self) -> "BenchmarkRun":
        if self.measured_at.tzinfo is None or self.measured_at.utcoffset() is None:
            raise ValueError("benchmark_run_requires_timezone")
        names = [item.metric_name for item in self.measurements]
        if len(names) != len(set(names)):
            raise ValueError("benchmark_metric_measurements_must_be_unique")
        return self


class MetricOutcome(str, Enum):
    WIN = "win"
    TIE = "tie"
    LOSS = "loss"


class MetricComparison(BaseModel):
    metric_name: str
    outcome: MetricOutcome
    challenger_value: float
    baseline_value: float
    weight: float
    critical_safety: bool


class BenchmarkComparison(BaseModel):
    contract: str = JARVIS_BENCHMARK_CONTRACT
    challenger_system_id: str
    baseline_system_id: str
    metric_results: tuple[MetricComparison, ...]
    weighted_win_rate: float = Field(ge=0.0, le=1.0)
    critical_safety_regression: bool
    comparable: bool
    superiority_claim_allowed: bool
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def claim_cannot_ignore_blockers(self) -> "BenchmarkComparison":
        if self.superiority_claim_allowed and self.blockers:
            raise ValueError("benchmark_superiority_claim_cannot_ignore_blockers")
        return self


def _outcome(direction: MetricDirection, challenger: float, baseline: float) -> MetricOutcome:
    if challenger == baseline:
        return MetricOutcome.TIE
    if direction is MetricDirection.HIGHER_IS_BETTER:
        return MetricOutcome.WIN if challenger > baseline else MetricOutcome.LOSS
    return MetricOutcome.WIN if challenger < baseline else MetricOutcome.LOSS


def compare_benchmark_runs(
    *,
    challenger: BenchmarkRun,
    baseline: BenchmarkRun,
    metrics: tuple[BenchmarkMetric, ...],
    required_weighted_win_rate: float = 0.80,
) -> BenchmarkComparison:
    if not 0.5 <= required_weighted_win_rate <= 1.0:
        raise ValueError("benchmark_required_win_rate_out_of_range")

    blockers: list[str] = []
    if challenger.task_set_id != baseline.task_set_id or challenger.task_set_fingerprint != baseline.task_set_fingerprint:
        blockers.append("benchmark_task_set_not_comparable")
    if challenger.environment_fingerprint != baseline.environment_fingerprint:
        blockers.append("benchmark_environment_not_comparable")

    metric_defs = {metric.metric_name: metric for metric in metrics}
    challenger_values = {item.metric_name: item for item in challenger.measurements}
    baseline_values = {item.metric_name: item for item in baseline.measurements}

    missing = sorted(set(metric_defs) - set(challenger_values) | set(metric_defs) - set(baseline_values))
    if missing:
        blockers.append("benchmark_required_metrics_missing:" + ",".join(missing))

    comparisons: list[MetricComparison] = []
    total_weight = 0.0
    win_weight = 0.0
    critical_regression = False

    for name, metric in metric_defs.items():
        challenger_measurement = challenger_values.get(name)
        baseline_measurement = baseline_values.get(name)
        if challenger_measurement is None or baseline_measurement is None:
            continue
        if (
            challenger_measurement.sample_count < MIN_CLAIM_SAMPLE_COUNT
            or baseline_measurement.sample_count < MIN_CLAIM_SAMPLE_COUNT
        ):
            blockers.append(f"benchmark_sample_count_insufficient:{name}")
        outcome = _outcome(metric.direction, challenger_measurement.value, baseline_measurement.value)
        total_weight += metric.weight
        if outcome is MetricOutcome.WIN:
            win_weight += metric.weight
        if metric.critical_safety and outcome is MetricOutcome.LOSS:
            critical_regression = True
        comparisons.append(
            MetricComparison(
                metric_name=name,
                outcome=outcome,
                challenger_value=challenger_measurement.value,
                baseline_value=baseline_measurement.value,
                weight=metric.weight,
                critical_safety=metric.critical_safety,
            )
        )

    if critical_regression:
        blockers.append("benchmark_critical_safety_regression")

    weighted_win_rate = win_weight / total_weight if total_weight else 0.0
    if weighted_win_rate < required_weighted_win_rate:
        blockers.append("benchmark_weighted_win_rate_below_target")

    blockers = list(dict.fromkeys(blockers))
    return BenchmarkComparison(
        challenger_system_id=challenger.system_id,
        baseline_system_id=baseline.system_id,
        metric_results=tuple(comparisons),
        weighted_win_rate=weighted_win_rate,
        critical_safety_regression=critical_regression,
        comparable=not any(
            blocker.startswith("benchmark_task_set_not_comparable")
            or blocker.startswith("benchmark_environment_not_comparable")
            or blocker.startswith("benchmark_required_metrics_missing")
            for blocker in blockers
        ),
        superiority_claim_allowed=not blockers,
        blockers=tuple(blockers),
    )
