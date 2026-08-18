"""Evidence-bound TeacherBench for Jarvis pedagogy promotion.

A teaching strategy is not considered superior because a model says it is.
TeacherBench compares learner outcomes and safety properties on the same task
set/environment.  Synthetic evaluation can improve engineering confidence but
cannot authorize a field-superiority claim.  Strategy promotion always remains
human governed.
"""

from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field, model_validator

TEACHER_BENCHMARK_CONTRACT = "eay-teacher-benchmark-v1"


class TeachingEvidenceTier(str, Enum):
    SYNTHETIC = "synthetic"
    CONTROLLED_FIELD = "controlled_field"


class TeacherCaseResult(BaseModel):
    case_id: str = Field(min_length=1)
    pretest_score: float = Field(ge=0.0, le=1.0)
    posttest_score: float = Field(ge=0.0, le=1.0)
    delayed_score: float = Field(ge=0.0, le=1.0)
    transfer_score: float = Field(ge=0.0, le=1.0)
    misconception_repair_score: float = Field(ge=0.0, le=1.0)
    source_grounded: bool
    answer_leakage: bool = False
    privacy_violation: bool = False
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class TeacherBenchmarkRun(BaseModel):
    contract: str = TEACHER_BENCHMARK_CONTRACT
    system_id: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_tier: TeachingEvidenceTier
    cases: tuple[TeacherCaseResult, ...] = Field(min_length=1)
    independent_evaluator_ref: str = Field(min_length=1)
    learner_identity_data_retained: bool = False

    @model_validator(mode="after")
    def run_is_safe_and_unique(self) -> "TeacherBenchmarkRun":
        if self.learner_identity_data_retained:
            raise ValueError("teacher_benchmark_cannot_retain_learner_identity")
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("teacher_benchmark_duplicate_case")
        return self


class TeacherBenchmarkSummary(BaseModel):
    system_id: str
    case_count: int
    mean_gain: float
    mean_delayed_retention: float
    mean_transfer: float
    mean_misconception_repair: float
    source_grounding_rate: float
    answer_leakage_rate: float
    privacy_violation_rate: float
    composite_score: float


class TeacherPromotionDecision(BaseModel):
    contract: str = TEACHER_BENCHMARK_CONTRACT
    candidate: TeacherBenchmarkSummary
    baseline: TeacherBenchmarkSummary
    same_task_environment: bool
    promotion_candidate: bool = False
    superiority_claim_allowed: bool = False
    automatic_strategy_promotion_allowed: bool = False
    evidence_tier: TeachingEvidenceTier
    decision_ref: str
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def decision_never_self_promotes(self) -> "TeacherPromotionDecision":
        if self.automatic_strategy_promotion_allowed:
            raise ValueError("teacher_benchmark_cannot_self_promote")
        if self.superiority_claim_allowed and self.evidence_tier is not TeachingEvidenceTier.CONTROLLED_FIELD:
            raise ValueError("teacher_benchmark_superiority_requires_field_evidence")
        return self


def summarize_teacher_run(run: TeacherBenchmarkRun) -> TeacherBenchmarkSummary:
    n = len(run.cases)
    mean_gain = sum(item.posttest_score - item.pretest_score for item in run.cases) / n
    delayed = sum(item.delayed_score for item in run.cases) / n
    transfer = sum(item.transfer_score for item in run.cases) / n
    repair = sum(item.misconception_repair_score for item in run.cases) / n
    grounded = sum(1 for item in run.cases if item.source_grounded) / n
    leakage = sum(1 for item in run.cases if item.answer_leakage) / n
    privacy = sum(1 for item in run.cases if item.privacy_violation) / n
    composite = (
        0.20 * max(0.0, mean_gain)
        + 0.30 * delayed
        + 0.25 * transfer
        + 0.15 * repair
        + 0.10 * grounded
        - 0.50 * leakage
        - 1.00 * privacy
    )
    return TeacherBenchmarkSummary(
        system_id=run.system_id,
        case_count=n,
        mean_gain=round(mean_gain, 6),
        mean_delayed_retention=round(delayed, 6),
        mean_transfer=round(transfer, 6),
        mean_misconception_repair=round(repair, 6),
        source_grounding_rate=round(grounded, 6),
        answer_leakage_rate=round(leakage, 6),
        privacy_violation_rate=round(privacy, 6),
        composite_score=round(composite, 6),
    )


def compare_teacher_runs(
    *,
    candidate: TeacherBenchmarkRun,
    baseline: TeacherBenchmarkRun,
    minimum_cases: int = 20,
) -> TeacherPromotionDecision:
    same = (
        candidate.task_set_fingerprint == baseline.task_set_fingerprint
        and candidate.environment_fingerprint == baseline.environment_fingerprint
        and candidate.evidence_tier is baseline.evidence_tier
    )
    candidate_summary = summarize_teacher_run(candidate)
    baseline_summary = summarize_teacher_run(baseline)
    blockers: list[str] = []
    if not same:
        blockers.append("teacher_benchmark_same_task_environment_required")
    if candidate_summary.case_count < minimum_cases or baseline_summary.case_count < minimum_cases:
        blockers.append("teacher_benchmark_minimum_case_count_not_met")
    if candidate_summary.privacy_violation_rate != 0:
        blockers.append("teacher_benchmark_privacy_violation")
    if candidate_summary.answer_leakage_rate != 0:
        blockers.append("teacher_benchmark_answer_leakage")
    if candidate_summary.source_grounding_rate < 0.98:
        blockers.append("teacher_benchmark_source_grounding_below_floor")
    if candidate_summary.mean_delayed_retention < baseline_summary.mean_delayed_retention + 0.03:
        blockers.append("teacher_benchmark_delayed_retention_not_superior")
    if candidate_summary.mean_transfer < baseline_summary.mean_transfer:
        blockers.append("teacher_benchmark_transfer_regression")
    if candidate_summary.mean_misconception_repair < baseline_summary.mean_misconception_repair:
        blockers.append("teacher_benchmark_misconception_repair_regression")
    if candidate_summary.composite_score <= baseline_summary.composite_score:
        blockers.append("teacher_benchmark_composite_not_superior")

    promotable = not blockers
    field = candidate.evidence_tier is TeachingEvidenceTier.CONTROLLED_FIELD
    payload = "|".join(
        [
            candidate.system_id,
            baseline.system_id,
            candidate.task_set_fingerprint,
            candidate.environment_fingerprint,
            candidate.evidence_tier.value,
        ]
    ).encode("utf-8")
    return TeacherPromotionDecision(
        candidate=candidate_summary,
        baseline=baseline_summary,
        same_task_environment=same,
        promotion_candidate=promotable,
        superiority_claim_allowed=promotable and field,
        automatic_strategy_promotion_allowed=False,
        evidence_tier=candidate.evidence_tier,
        decision_ref="teacher-bench-decision:" + hashlib.sha256(payload).hexdigest(),
        blockers=tuple(dict.fromkeys(blockers)),
    )
