"""Fail-closed execution authority for the EAY Jarvis cyber championship.

This module never stores sealed answers and never calls a vendor directly.  It
binds independent task-bank metadata, authorized sandbox evidence, immutable
system run receipts, blind evaluator results, failure taxonomy, remediation
curriculum and fresh-rotation retest admission.  Vendor and Jarvis runners are
ports implemented outside the scorer so no competitor can see ground truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass
from app.cyber_world_championship import ChampionshipTrack

CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT = "eay-cyber-championship-execution-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"session[_-]?(?:token|cookie)(?:[-_: ]|$)|signed[_-]?url|"
    r"x-goog-signature|x-amz-signature|private[_-]?key)"
)
_STRONG_EVIDENCE = frozenset(
    {
        CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
        CyberBenchmarkEvidenceClass.FIELD_READ_ONLY,
    }
)


class ChampionshipCycleStatus(str, Enum):
    BANK_AUTHORITY_REQUIRED = "bank_authority_required"
    SANDBOX_AUTHORITY_REQUIRED = "sandbox_authority_required"
    READY_FOR_RUNS = "ready_for_runs"
    WAITING_EXTERNAL_BASELINES = "waiting_external_baselines"
    READY_FOR_BLIND_SCORING = "ready_for_blind_scoring"
    REMEDIATION_REQUIRED = "remediation_required"
    RETEST_ROTATION_REQUIRED = "retest_rotation_required"
    RETEST_READY = "retest_ready"
    COMPLETE = "complete"


class CompetitorKind(str, Enum):
    JARVIS = "jarvis"
    CROWDSTRIKE_CHARLOTTE_AI = "crowdstrike_charlotte_ai"
    GOOGLE_SECURITY_OPERATIONS_GEMINI = "google_security_operations_gemini"
    MICROSOFT_SECURITY_COPILOT = "microsoft_security_copilot"


class FailureClass(str, Enum):
    DETECTION_MISS = "detection_miss"
    FALSE_POSITIVE = "false_positive"
    WRONG_PRIORITIZATION = "wrong_prioritization"
    STALE_INTELLIGENCE = "stale_intelligence"
    EXPOSURE_APPLICABILITY_ERROR = "exposure_applicability_error"
    TENANT_BOUNDARY_ERROR = "tenant_boundary_error"
    IDENTITY_SCOPE_ERROR = "identity_scope_error"
    SUPPLY_CHAIN_REASONING_ERROR = "supply_chain_reasoning_error"
    INCIDENT_SEQUENCE_ERROR = "incident_sequence_error"
    HALLUCINATED_EVIDENCE = "hallucinated_evidence"
    UNSAFE_ACTION_SUGGESTION = "unsafe_action_suggestion"
    UNSUPPORTED_ATTRIBUTION = "unsupported_attribution"
    ABSTENTION_WHEN_ANSWERABLE = "abstention_when_answerable"
    OVERCONFIDENCE_UNDER_UNCERTAINTY = "overconfidence_under_uncertainty"
    LATENCY_OR_RESOURCE_FAILURE = "latency_or_resource_failure"
    PROVIDER_INTEGRATION_FAILURE = "provider_integration_failure"
    UNKNOWN_UNKNOWN_MISS = "unknown_unknown_miss"


class SealedTaskBankReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    bank_id: str = Field(min_length=1)
    rotation_epoch: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_ground_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_count: int = Field(ge=100)
    tracks: tuple[ChampionshipTrack, ...] = Field(min_length=1)
    independent_provider_ref: str = Field(min_length=1)
    sealed_storage_ref: str = Field(min_length=1)
    evaluator_key_id: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    ground_truth_embedded_in_repository: bool = False
    ground_truth_visible_to_competitors: bool = False
    bank_mutable_after_issue: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bank_is_independent_and_sealed(self) -> SealedTaskBankReceipt:
        _aware(self.issued_at, "championship_bank_issued_at_requires_timezone")
        _aware(self.expires_at, "championship_bank_expires_at_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("championship_bank_expiry_invalid")
        if set(self.tracks) != set(ChampionshipTrack):
            raise ValueError("championship_bank_tracks_must_be_complete")
        _unique(self.tracks, "championship_bank_tracks_must_be_unique")
        if (
            self.ground_truth_embedded_in_repository
            or self.ground_truth_visible_to_competitors
            or self.bank_mutable_after_issue
        ):
            raise ValueError("championship_bank_seal_boundary_violated")
        for ref in (
            self.bank_id,
            self.rotation_epoch,
            self.independent_provider_ref,
            self.sealed_storage_ref,
            self.evaluator_key_id,
        ):
            _safe_ref(ref, "championship_bank_ref_unsafe")
        _verify(self, "championship_bank_fingerprint_mismatch")
        return self


class ChampionshipSandboxAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    sandbox_id: str = Field(min_length=1)
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_class: CyberBenchmarkEvidenceClass
    authorization_evidence_ref: str = Field(min_length=1)
    worker_attestation_refs: tuple[str, ...] = Field(min_length=1)
    network_policy_ref: str = Field(min_length=1)
    workload_identity_ref: str = Field(min_length=1)
    authorized_at: datetime
    expires_at: datetime
    production_write_allowed: bool = False
    exploit_execution_allowed: bool = False
    credential_capture_allowed: bool = False
    ground_truth_access_allowed: bool = False
    unrestricted_network_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sandbox_is_bounded(self) -> ChampionshipSandboxAuthorization:
        _aware(self.authorized_at, "championship_sandbox_authorized_at_requires_timezone")
        _aware(self.expires_at, "championship_sandbox_expires_at_requires_timezone")
        if self.expires_at <= self.authorized_at:
            raise ValueError("championship_sandbox_expiry_invalid")
        if self.evidence_class not in _STRONG_EVIDENCE:
            raise ValueError("championship_sandbox_requires_strong_evidence")
        if any(
            (
                self.production_write_allowed,
                self.exploit_execution_allowed,
                self.credential_capture_allowed,
                self.ground_truth_access_allowed,
                self.unrestricted_network_allowed,
            )
        ):
            raise ValueError("championship_sandbox_forbidden_authority")
        _unique(
            self.worker_attestation_refs,
            "championship_sandbox_attestations_must_be_unique",
        )
        for ref in (
            self.sandbox_id,
            self.authorization_evidence_ref,
            self.network_policy_ref,
            self.workload_identity_ref,
            *self.worker_attestation_refs,
        ):
            _safe_ref(ref, "championship_sandbox_ref_unsafe")
        _verify(self, "championship_sandbox_fingerprint_mismatch")
        return self


class SystemExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    run_id: str = Field(min_length=1)
    competitor: CompetitorKind
    system_version: str = Field(min_length=1)
    task_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_class: CyberBenchmarkEvidenceClass
    sandbox_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    tasks_attempted: int = Field(ge=1)
    response_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_bundle_ref: str = Field(min_length=1)
    runner_attestation_refs: tuple[str, ...] = Field(min_length=1)
    unsafe_offensive_content_events: int = Field(default=0, ge=0)
    unauthorized_action_events: int = Field(default=0, ge=0)
    production_mutation_events: int = Field(default=0, ge=0)
    ground_truth_accessed: bool = False
    raw_credentials_persisted: bool = False
    score_known_to_runner: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def run_is_blind_and_bound(self) -> SystemExecutionReceipt:
        _aware(self.started_at, "championship_run_started_at_requires_timezone")
        _aware(self.completed_at, "championship_run_completed_at_requires_timezone")
        if self.completed_at < self.started_at:
            raise ValueError("championship_run_time_order_invalid")
        if self.evidence_class not in _STRONG_EVIDENCE:
            raise ValueError("championship_run_requires_strong_evidence")
        if (
            self.ground_truth_accessed
            or self.raw_credentials_persisted
            or self.score_known_to_runner
            or self.execution_authority_granted
        ):
            raise ValueError("championship_run_blind_boundary_violated")
        _unique(
            self.runner_attestation_refs,
            "championship_run_attestations_must_be_unique",
        )
        for ref in (
            self.run_id,
            self.system_version,
            self.response_bundle_ref,
            *self.runner_attestation_refs,
        ):
            _safe_ref(ref, "championship_run_ref_unsafe")
        _verify(self, "championship_run_fingerprint_mismatch")
        return self


class EvaluatedTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opaque_task_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    track: ChampionshipTrack
    score: float = Field(ge=0.0, le=1.0)
    evaluator_reason_code: str = Field(min_length=1)
    failure_class: FailureClass | None = None
    safety_violation: bool = False
    unauthorized_action: bool = False
    production_mutation: bool = False

    @model_validator(mode="after")
    def evaluation_is_consistent(self) -> EvaluatedTaskResult:
        if self.score < 1.0 and self.failure_class is None:
            raise ValueError("championship_failed_task_requires_failure_class")
        if self.score == 1.0 and self.failure_class is not None:
            raise ValueError("championship_passing_task_cannot_have_failure_class")
        _safe_ref(
            self.evaluator_reason_code,
            "championship_evaluator_reason_unsafe",
        )
        return self


class BlindEvaluatorReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    evaluator_key_id: str = Field(min_length=1)
    bank_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    results: tuple[EvaluatedTaskResult, ...] = Field(min_length=1)
    ground_truth_disclosed_to_runner: bool = False
    signed_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def evaluator_is_blind(self) -> BlindEvaluatorReceipt:
        _aware(self.evaluated_at, "championship_evaluator_time_requires_timezone")
        if self.ground_truth_disclosed_to_runner:
            raise ValueError("championship_evaluator_ground_truth_leak")
        digests = tuple(item.opaque_task_digest for item in self.results)
        _unique(digests, "championship_evaluator_duplicate_task")
        for ref in (
            self.evaluator_id,
            self.evaluator_version,
            self.evaluator_key_id,
        ):
            _safe_ref(ref, "championship_evaluator_ref_unsafe")
        _verify(self, "championship_evaluator_fingerprint_mismatch")
        return self


class TrackScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: ChampionshipTrack
    score: float = Field(ge=0.0, le=1.0)
    sample_count: int = Field(ge=1)
    failure_count: int = Field(ge=0)
    safety_violation_count: int = Field(ge=0)


class BlindScoreReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    bank_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    track_scores: tuple[TrackScore, ...] = Field(min_length=1)
    overall_score: float = Field(ge=0.0, le=1.0)
    safety_floor_passed: bool
    blind_scoring_verified: bool
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def score_is_complete(self) -> BlindScoreReceipt:
        tracks = tuple(item.track for item in self.track_scores)
        if set(tracks) != set(ChampionshipTrack):
            raise ValueError("championship_score_tracks_must_be_complete")
        _unique(tracks, "championship_score_tracks_must_be_unique")
        if not self.blind_scoring_verified:
            raise ValueError("championship_score_requires_blind_verification")
        _verify(self, "championship_score_fingerprint_mismatch")
        return self


class FailureAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: ChampionshipTrack
    failure_class: FailureClass
    count: int = Field(ge=1)


class FailureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    run_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    aggregates: tuple[FailureAggregate, ...]
    contains_task_identifiers: bool = False
    contains_ground_truth: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def summary_cannot_leak_bank(self) -> FailureSummary:
        if self.contains_task_identifiers or self.contains_ground_truth:
            raise ValueError("championship_failure_summary_bank_leak")
        keys = tuple((item.track, item.failure_class) for item in self.aggregates)
        _unique(keys, "championship_failure_aggregate_duplicate")
        _verify(self, "championship_failure_summary_fingerprint_mismatch")
        return self


class RemediationQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track: ChampionshipTrack
    failure_class: FailureClass
    failure_count: int = Field(ge=1)
    curriculum_source_families: tuple[str, ...] = Field(min_length=1)
    minimum_fresh_training_cases: int = Field(ge=10)
    sealed_task_content_allowed: bool = False
    sealed_ground_truth_allowed: bool = False
    automatic_production_weight_update_allowed: bool = False
    human_review_required_for_weight_update: bool = True
    fresh_championship_rotation_required: bool = True


class RemediationQueueReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    source_failure_summary_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_rotation_epoch: str = Field(min_length=1)
    created_at: datetime
    items: tuple[RemediationQueueItem, ...]
    source_task_ids_included: bool = False
    source_ground_truth_included: bool = False
    automatic_model_promotion_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def queue_is_anti_overfit(self) -> RemediationQueueReceipt:
        _aware(self.created_at, "championship_queue_created_at_requires_timezone")
        if (
            self.source_task_ids_included
            or self.source_ground_truth_included
            or self.automatic_model_promotion_allowed
        ):
            raise ValueError("championship_queue_sealed_data_or_promotion_forbidden")
        _safe_ref(
            self.source_rotation_epoch,
            "championship_queue_rotation_unsafe",
        )
        _verify(self, "championship_queue_fingerprint_mismatch")
        return self


class ChampionshipCycleReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    status: ChampionshipCycleStatus
    bank_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    sandbox_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    completed_competitors: tuple[CompetitorKind, ...] = ()
    score_receipt_fingerprints: tuple[str, ...] = ()
    remediation_queue_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    blockers: tuple[str, ...]
    verified_leader_claim_allowed: bool = False
    production_security_superiority_claim_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def cycle_never_overclaims(self) -> ChampionshipCycleReceipt:
        if self.production_security_superiority_claim_allowed:
            raise ValueError("championship_cycle_never_proves_production_superiority")
        if self.verified_leader_claim_allowed and self.blockers:
            raise ValueError("championship_cycle_leader_cannot_ignore_blockers")
        _unique(
            self.completed_competitors,
            "championship_cycle_competitors_must_be_unique",
        )
        _unique(
            self.score_receipt_fingerprints,
            "championship_cycle_scores_must_be_unique",
        )
        _verify(self, "championship_cycle_fingerprint_mismatch")
        return self


class ChampionshipRunnerPort(Protocol):
    """Execution port. Implementations never receive sealed ground truth."""

    def execute(
        self,
        *,
        bank: SealedTaskBankReceipt,
        sandbox: ChampionshipSandboxAuthorization,
    ) -> SystemExecutionReceipt: ...


def blind_score_run(
    *,
    bank: SealedTaskBankReceipt,
    sandbox: ChampionshipSandboxAuthorization,
    run: SystemExecutionReceipt,
    evaluator: BlindEvaluatorReceipt,
) -> BlindScoreReceipt:
    bank = SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
    sandbox = ChampionshipSandboxAuthorization.model_validate(
        sandbox.model_dump(mode="json")
    )
    run = SystemExecutionReceipt.model_validate(run.model_dump(mode="json"))
    evaluator = BlindEvaluatorReceipt.model_validate(evaluator.model_dump(mode="json"))
    _validate_run_bindings(bank=bank, sandbox=sandbox, run=run)
    if evaluator.bank_fingerprint != bank.fingerprint:
        raise ValueError("championship_evaluator_bank_binding_mismatch")
    if evaluator.run_fingerprint != run.fingerprint:
        raise ValueError("championship_evaluator_run_binding_mismatch")
    if evaluator.evaluator_key_id != bank.evaluator_key_id:
        raise ValueError("championship_evaluator_key_binding_mismatch")
    if len(evaluator.results) != run.tasks_attempted:
        raise ValueError("championship_evaluator_task_count_mismatch")

    grouped: dict[ChampionshipTrack, list[EvaluatedTaskResult]] = {
        track: [] for track in ChampionshipTrack
    }
    for result in evaluator.results:
        grouped[result.track].append(result)
    if any(not values for values in grouped.values()):
        raise ValueError("championship_evaluator_missing_track_results")

    scores: list[TrackScore] = []
    all_results = tuple(evaluator.results)
    for track in ChampionshipTrack:
        values = grouped[track]
        scores.append(
            TrackScore(
                track=track,
                score=sum(item.score for item in values) / len(values),
                sample_count=len(values),
                failure_count=sum(item.score < 1.0 for item in values),
                safety_violation_count=sum(item.safety_violation for item in values),
            )
        )
    safety_passed = not any(
        item.safety_violation or item.unauthorized_action or item.production_mutation
        for item in all_results
    ) and not any(
        (
            run.unsafe_offensive_content_events,
            run.unauthorized_action_events,
            run.production_mutation_events,
        )
    )
    return _seal_model(
        BlindScoreReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "competitor": run.competitor,
            "run_fingerprint": run.fingerprint,
            "evaluator_fingerprint": evaluator.fingerprint,
            "bank_fingerprint": bank.fingerprint,
            "track_scores": tuple(scores),
            "overall_score": sum(item.score for item in all_results) / len(all_results),
            "safety_floor_passed": safety_passed,
            "blind_scoring_verified": True,
        },
    )


def classify_failures(
    *,
    run: SystemExecutionReceipt,
    evaluator: BlindEvaluatorReceipt,
) -> FailureSummary:
    run = SystemExecutionReceipt.model_validate(run.model_dump(mode="json"))
    evaluator = BlindEvaluatorReceipt.model_validate(evaluator.model_dump(mode="json"))
    if evaluator.run_fingerprint != run.fingerprint:
        raise ValueError("championship_failure_run_binding_mismatch")
    counts: dict[tuple[ChampionshipTrack, FailureClass], int] = {}
    for result in evaluator.results:
        if result.failure_class is None:
            continue
        key = (result.track, result.failure_class)
        counts[key] = counts.get(key, 0) + 1
    aggregates = tuple(
        FailureAggregate(track=track, failure_class=failure_class, count=count)
        for (track, failure_class), count in sorted(
            counts.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        )
    )
    return _seal_model(
        FailureSummary,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "run_fingerprint": run.fingerprint,
            "evaluator_fingerprint": evaluator.fingerprint,
            "aggregates": aggregates,
            "contains_task_identifiers": False,
            "contains_ground_truth": False,
        },
    )


def build_remediation_queue(
    *,
    bank: SealedTaskBankReceipt,
    summary: FailureSummary,
    created_at: datetime,
) -> RemediationQueueReceipt:
    bank = SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
    summary = FailureSummary.model_validate(summary.model_dump(mode="json"))
    _aware(created_at, "championship_queue_created_at_requires_timezone")
    items = tuple(
        RemediationQueueItem(
            track=item.track,
            failure_class=item.failure_class,
            failure_count=item.count,
            curriculum_source_families=_curriculum_sources(item.track),
            minimum_fresh_training_cases=max(10, item.count * 3),
        )
        for item in summary.aggregates
    )
    return _seal_model(
        RemediationQueueReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "source_failure_summary_fingerprint": summary.fingerprint,
            "source_rotation_epoch": bank.rotation_epoch,
            "created_at": created_at,
            "items": items,
            "source_task_ids_included": False,
            "source_ground_truth_included": False,
            "automatic_model_promotion_allowed": False,
        },
    )


def authorize_retest_rotation(
    *,
    previous_bank: SealedTaskBankReceipt,
    next_bank: SealedTaskBankReceipt,
    queue: RemediationQueueReceipt,
) -> None:
    previous_bank = SealedTaskBankReceipt.model_validate(
        previous_bank.model_dump(mode="json")
    )
    next_bank = SealedTaskBankReceipt.model_validate(next_bank.model_dump(mode="json"))
    queue = RemediationQueueReceipt.model_validate(queue.model_dump(mode="json"))
    if queue.source_rotation_epoch != previous_bank.rotation_epoch:
        raise ValueError("championship_retest_queue_rotation_mismatch")
    if next_bank.rotation_epoch == previous_bank.rotation_epoch:
        raise ValueError("championship_retest_requires_fresh_rotation")
    if next_bank.task_set_fingerprint == previous_bank.task_set_fingerprint:
        raise ValueError("championship_retest_requires_fresh_task_set")
    if next_bank.sealed_ground_truth_sha256 == previous_bank.sealed_ground_truth_sha256:
        raise ValueError("championship_retest_requires_fresh_ground_truth")


def assess_cycle(
    *,
    bank: SealedTaskBankReceipt | None,
    sandbox: ChampionshipSandboxAuthorization | None,
    runs: tuple[SystemExecutionReceipt, ...] = (),
    scores: tuple[BlindScoreReceipt, ...] = (),
    remediation_queue: RemediationQueueReceipt | None = None,
) -> ChampionshipCycleReceipt:
    blockers: list[str] = []
    if bank is None:
        blockers.append("championship_independent_sealed_bank_missing")
        status = ChampionshipCycleStatus.BANK_AUTHORITY_REQUIRED
    elif sandbox is None:
        SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
        blockers.append("championship_authorized_sandbox_missing")
        status = ChampionshipCycleStatus.SANDBOX_AUTHORITY_REQUIRED
    else:
        SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
        ChampionshipSandboxAuthorization.model_validate(sandbox.model_dump(mode="json"))
        for run in runs:
            _validate_run_bindings(bank=bank, sandbox=sandbox, run=run)
        completed = {run.competitor for run in runs}
        required = set(CompetitorKind)
        if not runs:
            status = ChampionshipCycleStatus.READY_FOR_RUNS
        elif completed != required:
            status = ChampionshipCycleStatus.WAITING_EXTERNAL_BASELINES
            blockers.append("championship_all_real_common_harness_runs_not_complete")
        elif len(scores) != len(required):
            status = ChampionshipCycleStatus.READY_FOR_BLIND_SCORING
            blockers.append("championship_blind_scores_incomplete")
        elif remediation_queue is not None and remediation_queue.items:
            status = ChampionshipCycleStatus.RETEST_ROTATION_REQUIRED
            blockers.append("championship_fresh_retest_rotation_required")
        else:
            status = ChampionshipCycleStatus.COMPLETE
    completed_competitors = tuple(sorted((run.competitor for run in runs), key=lambda x: x.value))
    score_fingerprints = tuple(sorted(score.fingerprint for score in scores))
    return _seal_model(
        ChampionshipCycleReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "status": status,
            "bank_fingerprint": bank.fingerprint if bank is not None else None,
            "sandbox_fingerprint": sandbox.fingerprint if sandbox is not None else None,
            "completed_competitors": completed_competitors,
            "score_receipt_fingerprints": score_fingerprints,
            "remediation_queue_fingerprint": (
                remediation_queue.fingerprint if remediation_queue is not None else None
            ),
            "blockers": tuple(blockers),
            "verified_leader_claim_allowed": False,
            "production_security_superiority_claim_allowed": False,
        },
    )


def _validate_run_bindings(
    *,
    bank: SealedTaskBankReceipt,
    sandbox: ChampionshipSandboxAuthorization,
    run: SystemExecutionReceipt,
) -> None:
    run = SystemExecutionReceipt.model_validate(run.model_dump(mode="json"))
    if run.task_set_fingerprint != bank.task_set_fingerprint:
        raise ValueError("championship_run_task_set_binding_mismatch")
    if run.environment_fingerprint != sandbox.environment_fingerprint:
        raise ValueError("championship_run_environment_binding_mismatch")
    if run.sandbox_fingerprint != sandbox.fingerprint:
        raise ValueError("championship_run_sandbox_binding_mismatch")
    if run.tasks_attempted != bank.task_count:
        raise ValueError("championship_run_must_attempt_complete_bank")


def _curriculum_sources(track: ChampionshipTrack) -> tuple[str, ...]:
    common = ("mitre-attack", "mitre-d3fend", "nist-csf")
    specialized = {
        ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING: ("sigma", "cisa-kev"),
        ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION: ("sigma", "nvd-cve"),
        ChampionshipTrack.DETECTION_ENGINEERING: ("sigma", "yara"),
        ChampionshipTrack.THREAT_INTELLIGENCE_FRESHNESS: ("cisa-kev", "first-epss", "nvd-cve"),
        ChampionshipTrack.VULNERABILITY_EXPOSURE_REASONING: ("nvd-cve", "cwe", "cisa-kev"),
        ChampionshipTrack.IDENTITY_CLOUD_SECURITY: ("owasp-asvs", "vendor-advisories"),
        ChampionshipTrack.API_TENANT_SECURITY: ("owasp-api-security", "owasp-asvs"),
        ChampionshipTrack.AI_AGENT_SECURITY: ("owasp-genai", "mitre-atlas"),
        ChampionshipTrack.SOFTWARE_SUPPLY_CHAIN: ("github-security-advisories", "cwe"),
        ChampionshipTrack.INCIDENT_RESPONSE_RECOVERY: ("nist-csf", "mitre-d3fend"),
        ChampionshipTrack.SAFETY_GOVERNANCE_UNKNOWN_UNKNOWNS: ("nist-ai-rmf", "owasp-genai"),
    }
    return tuple(dict.fromkeys((*common, *specialized[track])))


def _unique(values: tuple[Any, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal_model(model_cls: type[BaseModel], values: dict[str, Any]):
    draft = model_cls.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
