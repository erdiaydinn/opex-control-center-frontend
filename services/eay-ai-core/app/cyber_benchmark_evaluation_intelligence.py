"""Evidence-bound CyberBench adjudication and metric compilation for EAY Jarvis.

CyberBench superiority cannot be manufactured from hand-entered aggregate scores.
This module requires case-level adjudications, exact task/environment bindings and
unique case fingerprints before the canonical cyber benchmark may consume metrics.

The evaluator deliberately stores references and fingerprints rather than raw model
outputs. That keeps secrets, exploit-like text and company payloads out of benchmark
receipts while preserving auditable case-level evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_benchmark_intelligence import CyberBenchmarkProfile
from app.jarvis_benchmark import MetricDirection, MetricMeasurement

CYBER_BENCHMARK_EVALUATION_CONTRACT = "eay-cyber-benchmark-evaluation-v1"
CYBER_BENCHMARK_MIN_CASES_PER_METRIC = 20

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CyberBenchmarkAdjudicationMethod(str, Enum):
    DETERMINISTIC = "deterministic"
    BLIND_HUMAN = "blind_human"
    DUAL_REVIEW = "dual_review"


class CyberBenchmarkCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_BENCHMARK_EVALUATION_CONTRACT
    case_id: str = Field(min_length=1)
    case_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_set_id: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_value: float = Field(ge=0.0, le=1.0)
    adjudication_method: CyberBenchmarkAdjudicationMethod
    evidence_ref: str = Field(min_length=1)
    adjudicator_ref: str = Field(min_length=1)
    reviewed_at: datetime
    raw_prompt_retained: bool = False
    raw_model_output_retained: bool = False
    credential_material_retained: bool = False
    exploit_content_retained: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def result_is_safe_case_level_evidence(self) -> CyberBenchmarkCaseResult:
        _aware(self.reviewed_at, "cyber_benchmark_case_reviewed_at_requires_timezone")
        if self.raw_prompt_retained:
            raise ValueError("cyber_benchmark_case_raw_prompt_retention_forbidden")
        if self.raw_model_output_retained:
            raise ValueError("cyber_benchmark_case_raw_output_retention_forbidden")
        if self.credential_material_retained:
            raise ValueError("cyber_benchmark_case_credential_retention_forbidden")
        if self.exploit_content_retained:
            raise ValueError("cyber_benchmark_case_exploit_content_retention_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_benchmark_case_never_grants_execution_authority")
        for ref in (
            self.case_id,
            self.task_set_id,
            self.metric_name,
            self.system_id,
            self.system_version,
            self.evidence_ref,
            self.adjudicator_ref,
        ):
            _safe_ref(ref, "cyber_benchmark_case_unsafe_reference_forbidden")
        _verify(self, "cyber_benchmark_case_fingerprint_mismatch")
        return self


class CyberBenchmarkEvaluationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_BENCHMARK_EVALUATION_CONTRACT
    evaluation_id: str = Field(min_length=1)
    profile_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_set_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    min_cases_per_metric: int = Field(ge=CYBER_BENCHMARK_MIN_CASES_PER_METRIC)
    case_result_fingerprints: tuple[str, ...] = Field(min_length=1)
    metric_measurements: tuple[MetricMeasurement, ...] = Field(min_length=1)
    all_required_metrics_present: bool
    sample_floor_satisfied: bool
    raw_prompt_retained: bool = False
    raw_model_output_retained: bool = False
    superiority_claim_authority_granted: bool = False
    production_security_claim_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_complete_and_non_authoritative(self) -> CyberBenchmarkEvaluationReceipt:
        _unique(
            self.case_result_fingerprints,
            "cyber_benchmark_evaluation_case_fingerprints_must_be_unique",
        )
        metric_names = tuple(item.metric_name for item in self.metric_measurements)
        _unique(metric_names, "cyber_benchmark_evaluation_metrics_must_be_unique")
        expected_sample_floor = all(
            item.sample_count >= self.min_cases_per_metric
            for item in self.metric_measurements
        )
        if self.sample_floor_satisfied != expected_sample_floor:
            raise ValueError("cyber_benchmark_evaluation_sample_floor_flag_mismatch")
        if not self.all_required_metrics_present:
            raise ValueError("cyber_benchmark_evaluation_requires_complete_metrics")
        if not self.sample_floor_satisfied:
            raise ValueError("cyber_benchmark_evaluation_requires_sample_floor")
        if self.raw_prompt_retained:
            raise ValueError("cyber_benchmark_evaluation_raw_prompt_retention_forbidden")
        if self.raw_model_output_retained:
            raise ValueError("cyber_benchmark_evaluation_raw_output_retention_forbidden")
        if self.superiority_claim_authority_granted:
            raise ValueError("cyber_benchmark_evaluation_never_grants_superiority_claim")
        if self.production_security_claim_authority_granted:
            raise ValueError("cyber_benchmark_evaluation_never_grants_production_claim")
        if self.execution_authority_granted:
            raise ValueError("cyber_benchmark_evaluation_never_grants_execution_authority")
        for ref in (self.evaluation_id, self.task_set_id, self.system_id, self.system_version):
            _safe_ref(ref, "cyber_benchmark_evaluation_unsafe_reference_forbidden")
        _verify(self, "cyber_benchmark_evaluation_fingerprint_mismatch")
        return self


def build_cyber_benchmark_case_result(
    *,
    profile: CyberBenchmarkProfile,
    case_id: str,
    case_fingerprint: str,
    metric_name: str,
    system_id: str,
    system_version: str,
    environment_fingerprint: str,
    observed_value: float,
    adjudication_method: CyberBenchmarkAdjudicationMethod,
    evidence_ref: str,
    adjudicator_ref: str,
    reviewed_at: datetime,
) -> CyberBenchmarkCaseResult:
    profile = CyberBenchmarkProfile.model_validate(profile.model_dump(mode="json"))
    metric_names = {item.metric_name for item in profile.metrics}
    if metric_name not in metric_names:
        raise ValueError("cyber_benchmark_case_metric_not_in_profile")
    if not re.fullmatch(r"[0-9a-f]{64}", case_fingerprint):
        raise ValueError("cyber_benchmark_case_fingerprint_invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", environment_fingerprint):
        raise ValueError("cyber_benchmark_case_environment_fingerprint_invalid")
    _aware(reviewed_at, "cyber_benchmark_case_reviewed_at_requires_timezone")
    draft = {
        "contract": CYBER_BENCHMARK_EVALUATION_CONTRACT,
        "case_id": case_id,
        "case_fingerprint": case_fingerprint,
        "profile_fingerprint": profile.fingerprint,
        "task_set_id": profile.task_set_id,
        "metric_name": metric_name,
        "system_id": system_id,
        "system_version": system_version,
        "environment_fingerprint": environment_fingerprint,
        "observed_value": observed_value,
        "adjudication_method": adjudication_method.value,
        "evidence_ref": evidence_ref,
        "adjudicator_ref": adjudicator_ref,
        "reviewed_at": _iso(reviewed_at),
        "raw_prompt_retained": False,
        "raw_model_output_retained": False,
        "credential_material_retained": False,
        "exploit_content_retained": False,
        "execution_authority_granted": False,
    }
    return CyberBenchmarkCaseResult.model_validate(_sealed(draft))


def compile_cyber_benchmark_evaluation(
    *,
    profile: CyberBenchmarkProfile,
    results: tuple[CyberBenchmarkCaseResult, ...],
    min_cases_per_metric: int = CYBER_BENCHMARK_MIN_CASES_PER_METRIC,
) -> CyberBenchmarkEvaluationReceipt:
    profile = CyberBenchmarkProfile.model_validate(profile.model_dump(mode="json"))
    if min_cases_per_metric < CYBER_BENCHMARK_MIN_CASES_PER_METRIC:
        raise ValueError("cyber_benchmark_evaluation_min_cases_too_low")
    if not results:
        raise ValueError("cyber_benchmark_evaluation_requires_case_results")

    normalized = tuple(
        CyberBenchmarkCaseResult.model_validate(item.model_dump(mode="json"))
        for item in results
    )
    first = normalized[0]
    expected_identity = (
        first.system_id,
        first.system_version,
        first.environment_fingerprint,
    )
    seen_case_fingerprints: set[str] = set()
    by_metric: dict[str, list[CyberBenchmarkCaseResult]] = {}
    for result in normalized:
        if result.profile_fingerprint != profile.fingerprint:
            raise ValueError("cyber_benchmark_evaluation_profile_mismatch")
        if result.task_set_id != profile.task_set_id:
            raise ValueError("cyber_benchmark_evaluation_task_set_mismatch")
        identity = (
            result.system_id,
            result.system_version,
            result.environment_fingerprint,
        )
        if identity != expected_identity:
            raise ValueError("cyber_benchmark_evaluation_system_or_environment_mismatch")
        if result.case_fingerprint in seen_case_fingerprints:
            raise ValueError("cyber_benchmark_evaluation_duplicate_case_fingerprint")
        seen_case_fingerprints.add(result.case_fingerprint)
        by_metric.setdefault(result.metric_name, []).append(result)

    expected_metrics = {item.metric_name: item for item in profile.metrics}
    if set(by_metric) != set(expected_metrics):
        raise ValueError("cyber_benchmark_evaluation_required_metrics_mismatch")

    measurements: list[MetricMeasurement] = []
    for metric_name in sorted(expected_metrics):
        metric = expected_metrics[metric_name]
        cases = by_metric[metric_name]
        if len(cases) < min_cases_per_metric:
            raise ValueError(
                f"cyber_benchmark_evaluation_sample_floor_not_met:{metric_name}"
            )
        value = sum(item.observed_value for item in cases) / len(cases)
        evidence_seed = {
            "profile": profile.fingerprint,
            "metric": metric_name,
            "system": first.system_id,
            "version": first.system_version,
            "environment": first.environment_fingerprint,
            "case_fingerprints": sorted(item.fingerprint for item in cases),
            "direction": metric.direction.value,
        }
        evidence_ref = (
            f"cyberbench-metric:{metric_name}:{_fingerprint(evidence_seed)[:24]}"
        )
        measurements.append(
            MetricMeasurement(
                metric_name=metric_name,
                value=value,
                sample_count=len(cases),
                evidence_ref=evidence_ref,
            )
        )

    evaluation_seed = {
        "profile": profile.fingerprint,
        "system": first.system_id,
        "version": first.system_version,
        "environment": first.environment_fingerprint,
        "case_result_fingerprints": sorted(item.fingerprint for item in normalized),
        "min_cases_per_metric": min_cases_per_metric,
    }
    evaluation_id = f"cyberbench-evaluation:{_fingerprint(evaluation_seed)[:24]}"
    draft = {
        "contract": CYBER_BENCHMARK_EVALUATION_CONTRACT,
        "evaluation_id": evaluation_id,
        "profile_fingerprint": profile.fingerprint,
        "task_set_id": profile.task_set_id,
        "system_id": first.system_id,
        "system_version": first.system_version,
        "environment_fingerprint": first.environment_fingerprint,
        "min_cases_per_metric": min_cases_per_metric,
        "case_result_fingerprints": sorted(item.fingerprint for item in normalized),
        "metric_measurements": [item.model_dump(mode="json") for item in measurements],
        "all_required_metrics_present": True,
        "sample_floor_satisfied": True,
        "raw_prompt_retained": False,
        "raw_model_output_retained": False,
        "superiority_claim_authority_granted": False,
        "production_security_claim_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CyberBenchmarkEvaluationReceipt.model_validate(_sealed(draft))


def verify_cyber_benchmark_evaluation(
    *,
    receipt: CyberBenchmarkEvaluationReceipt,
) -> None:
    CyberBenchmarkEvaluationReceipt.model_validate(receipt.model_dump(mode="json"))


def metric_direction(
    *,
    profile: CyberBenchmarkProfile,
    metric_name: str,
) -> MetricDirection:
    profile = CyberBenchmarkProfile.model_validate(profile.model_dump(mode="json"))
    for metric in profile.metrics:
        if metric.metric_name == metric_name:
            return metric.direction
    raise ValueError("cyber_benchmark_metric_not_in_profile")


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_benchmark_evaluation_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
