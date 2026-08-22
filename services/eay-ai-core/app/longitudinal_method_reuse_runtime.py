"""Fail-closed runtime gate for reusing a previously verified Jarvis method.

Novel-solution, transfer/OOD and longitudinal evidence answer different questions.
This module composes those existing authorities before a *reused* method may enter
the existing frontier deliberation runtime. It deliberately does not create a new
router, provider gateway, scheduler or side-effect authority.

The original ``execute_verified_novel_frontier`` path remains the first-use novel
solution deliberation path. Reuse of an already selected method is expected to use
``execute_verified_method_reuse_frontier`` so historical success cannot silently
outlive current-regime degradation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frontier3_certification_intelligence import FrontierCertificationDomain
from .intelligence_router import TaskRisk
from .longitudinal_method_reliability_intelligence import (
    LongitudinalMethodReliabilityArtifact,
    MethodReliabilityState,
)
from .novel_problem_solver_intelligence import (
    NovelFrontierGateway,
    NovelProblemDisposition,
    VerifiedNovelFrontierRequest,
    VerifiedNovelFrontierResult,
    execute_verified_novel_frontier,
)
from .transfer_generalization_intelligence import (
    TransferDisposition,
    TransferGeneralizationArtifact,
)

METHOD_REUSE_RUNTIME_CONTRACT = "eay-longitudinal-method-reuse-runtime-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _seal(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


_SealedT = TypeVar("_SealedT", bound=BaseModel)


def _fingerprint_for(model_type: type[_SealedT], values: dict[str, object]) -> str:
    probe = model_type.model_construct(**values, fingerprint="0" * 64)
    return _seal(_payload(probe))


class MethodReuseAdmissionStatus(str, Enum):
    ADMITTED = "admitted"
    HOLD = "hold"


class MethodReusePolicy(SealedModel):
    maximum_reliability_age_hours: int = Field(default=24, ge=1, le=168)
    require_fresh_frontier_certification: bool = True
    require_ready_transfer: bool = True
    require_trusted_current_regime: bool = True

    @model_validator(mode="after")
    def safety_requirements_cannot_be_disabled(self) -> "MethodReusePolicy":
        if not all(
            (
                self.require_fresh_frontier_certification,
                self.require_ready_transfer,
                self.require_trusted_current_regime,
            )
        ):
            raise ValueError("method_reuse_safety_requirements_cannot_be_disabled")
        return self


class VerifiedMethodReuseRequest(SealedModel):
    contract: str = METHOD_REUSE_RUNTIME_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    problem_id: str = Field(pattern=_SCOPE)
    current_regime_id: str = Field(pattern=_SCOPE)
    checked_at: datetime
    frontier_request: VerifiedNovelFrontierRequest
    transfer_artifact: TransferGeneralizationArtifact
    reliability_artifact: LongitudinalMethodReliabilityArtifact
    policy: MethodReusePolicy = Field(default_factory=MethodReusePolicy)

    @model_validator(mode="after")
    def exact_evidence_chain(self) -> "VerifiedMethodReuseRequest":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("method_reuse_checked_at_requires_timezone")

        solution = self.frontier_request.solution_artifact
        transfer = self.transfer_artifact
        reliability = self.reliability_artifact
        selected = solution.selected_solution_id

        if self.frontier_request.tenant_id != self.tenant_id:
            raise ValueError("method_reuse_frontier_tenant_mismatch")
        if self.frontier_request.company_id != self.company_id:
            raise ValueError("method_reuse_frontier_company_mismatch")
        if solution.tenant_id != self.tenant_id:
            raise ValueError("method_reuse_solution_tenant_mismatch")
        if solution.company_id != self.company_id:
            raise ValueError("method_reuse_solution_company_mismatch")
        if solution.problem_id != self.problem_id:
            raise ValueError("method_reuse_solution_problem_mismatch")
        if solution.disposition is not NovelProblemDisposition.READY or not selected:
            raise ValueError("method_reuse_requires_ready_selected_solution")

        if transfer.tenant_id != self.tenant_id:
            raise ValueError("method_reuse_transfer_tenant_mismatch")
        if transfer.company_id != self.company_id:
            raise ValueError("method_reuse_transfer_company_mismatch")
        if transfer.problem_id != self.problem_id:
            raise ValueError("method_reuse_transfer_problem_mismatch")
        if transfer.source_solution_artifact_fingerprint != solution.fingerprint:
            raise ValueError("method_reuse_transfer_solution_fingerprint_mismatch")
        if transfer.selected_solution_id != selected:
            raise ValueError("method_reuse_transfer_method_mismatch")

        if reliability.tenant_id != self.tenant_id:
            raise ValueError("method_reuse_reliability_tenant_mismatch")
        if reliability.company_id != self.company_id:
            raise ValueError("method_reuse_reliability_company_mismatch")
        if reliability.problem_id != self.problem_id:
            raise ValueError("method_reuse_reliability_problem_mismatch")
        if reliability.method_id != selected:
            raise ValueError("method_reuse_reliability_method_mismatch")
        if reliability.source_transfer_artifact_fingerprint != transfer.fingerprint:
            raise ValueError("method_reuse_reliability_transfer_fingerprint_mismatch")
        if reliability.current_regime_id != self.current_regime_id:
            raise ValueError("method_reuse_current_regime_mismatch")
        if reliability.assessment_as_of > self.checked_at:
            raise ValueError("method_reuse_future_reliability_assessment_forbidden")
        return self


class MethodReuseAdmission(SealedModel):
    contract: str = METHOD_REUSE_RUNTIME_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    problem_id: str = Field(pattern=_SCOPE)
    method_id: str = Field(pattern=_SCOPE)
    current_regime_id: str = Field(pattern=_SCOPE)
    checked_at: datetime
    valid_until: datetime
    source_solution_fingerprint: str = Field(pattern=_DIGEST)
    source_transfer_fingerprint: str = Field(pattern=_DIGEST)
    source_reliability_fingerprint: str = Field(pattern=_DIGEST)
    status: MethodReuseAdmissionStatus
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    provider_authority_granted: bool = False
    company_truth_promoted: bool = False
    automatic_training_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral_and_non_authoritative(self) -> "MethodReuseAdmission":
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("method_reuse_admission_checked_at_requires_timezone")
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("method_reuse_admission_valid_until_requires_timezone")
        if self.status is MethodReuseAdmissionStatus.ADMITTED:
            if self.blockers or self.valid_until < self.checked_at:
                raise ValueError("method_reuse_admitted_requires_fresh_blocker_free_evidence")
        elif not self.blockers:
            raise ValueError("method_reuse_hold_requires_blocker")
        if any(
            (
                self.provider_authority_granted,
                self.company_truth_promoted,
                self.automatic_training_allowed,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("method_reuse_admission_never_mints_authority")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("method_reuse_admission_fingerprint_mismatch")
        return self


class VerifiedMethodReuseResult(SealedModel):
    contract: str = METHOD_REUSE_RUNTIME_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    problem_id: str = Field(pattern=_SCOPE)
    method_id: str = Field(pattern=_SCOPE)
    admission: MethodReuseAdmission
    frontier_deliberation_invoked: bool
    frontier_result: VerifiedNovelFrontierResult | None = None
    execution_authority_granted: bool = False
    company_truth_promoted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral_and_non_authoritative(self) -> "VerifiedMethodReuseResult":
        admitted = self.admission.status is MethodReuseAdmissionStatus.ADMITTED
        if admitted != self.frontier_deliberation_invoked:
            raise ValueError("method_reuse_frontier_invocation_must_match_admission")
        if admitted != (self.frontier_result is not None):
            raise ValueError("method_reuse_frontier_result_must_match_admission")
        if self.execution_authority_granted or self.company_truth_promoted or self.side_effect_authority_granted:
            raise ValueError("method_reuse_result_never_mints_authority")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("method_reuse_result_fingerprint_mismatch")
        return self


def build_method_reuse_admission(request: VerifiedMethodReuseRequest) -> MethodReuseAdmission:
    request = VerifiedMethodReuseRequest.model_validate(request.model_dump(mode="json"))
    solution = request.frontier_request.solution_artifact
    transfer = request.transfer_artifact
    reliability = request.reliability_artifact
    selected = solution.selected_solution_id or ""
    blockers: list[str] = []

    if request.policy.require_ready_transfer and transfer.disposition is not TransferDisposition.READY:
        blockers.append("method_reuse_transfer_not_ready")
    if not transfer.bounded_transfer_claim_allowed:
        blockers.append("method_reuse_bounded_transfer_claim_missing")

    if (
        request.policy.require_trusted_current_regime
        and reliability.state is not MethodReliabilityState.TRUSTED
    ):
        blockers.append(f"method_reuse_current_regime_not_trusted:{reliability.state.value}")
    if not reliability.bounded_current_regime_reliability_claim_allowed:
        blockers.append("method_reuse_bounded_current_regime_claim_missing")

    valid_until = reliability.assessment_as_of + timedelta(
        hours=request.policy.maximum_reliability_age_hours
    )
    if request.checked_at > valid_until:
        blockers.append("method_reuse_reliability_assessment_stale")

    task = request.frontier_request.task
    if request.policy.require_fresh_frontier_certification:
        if not task.requires_fresh_certification:
            blockers.append("method_reuse_fresh_frontier_certification_required")
        if task.certification_domain is not FrontierCertificationDomain.NOVEL_PROBLEM_SOLVING:
            blockers.append("method_reuse_novel_problem_certification_domain_required")

    if task.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL} and reliability.state is not MethodReliabilityState.TRUSTED:
        blockers.append("method_reuse_high_risk_requires_trusted_method")

    status = (
        MethodReuseAdmissionStatus.ADMITTED
        if not blockers
        else MethodReuseAdmissionStatus.HOLD
    )
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *solution.evidence_refs,
                *transfer.evidence_refs,
                *reliability.evidence_refs,
                f"novel-solution://{solution.fingerprint}",
                f"transfer-generalization://{transfer.fingerprint}",
                f"longitudinal-reliability://{reliability.fingerprint}",
            )
        )
    )
    values: dict[str, object] = dict(
        tenant_id=request.tenant_id,
        company_id=request.company_id,
        problem_id=request.problem_id,
        method_id=selected,
        current_regime_id=request.current_regime_id,
        checked_at=request.checked_at,
        valid_until=valid_until,
        source_solution_fingerprint=solution.fingerprint,
        source_transfer_fingerprint=transfer.fingerprint,
        source_reliability_fingerprint=reliability.fingerprint,
        status=status,
        blockers=tuple(dict.fromkeys(blockers)),
        evidence_refs=evidence_refs,
    )
    values["fingerprint"] = _fingerprint_for(MethodReuseAdmission, values)
    return MethodReuseAdmission.model_validate(values)


def _result(
    *,
    request: VerifiedMethodReuseRequest,
    admission: MethodReuseAdmission,
    frontier_result: VerifiedNovelFrontierResult | None,
) -> VerifiedMethodReuseResult:
    values: dict[str, object] = dict(
        tenant_id=request.tenant_id,
        company_id=request.company_id,
        problem_id=request.problem_id,
        method_id=admission.method_id,
        admission=admission,
        frontier_deliberation_invoked=frontier_result is not None,
        frontier_result=frontier_result,
    )
    values["fingerprint"] = _fingerprint_for(VerifiedMethodReuseResult, values)
    return VerifiedMethodReuseResult.model_validate(values)


async def execute_verified_method_reuse_frontier(
    *,
    gateway: NovelFrontierGateway,
    request: VerifiedMethodReuseRequest,
) -> VerifiedMethodReuseResult:
    """Run existing frontier deliberation only after current-regime reuse admission.

    HOLD returns before ``gateway.plan`` or any provider invocation. Admission is
    evidence eligibility only; the downstream frontier runtime still performs its
    own routing/certification/council gates and neither layer grants side effects.
    """

    request = VerifiedMethodReuseRequest.model_validate(request.model_dump(mode="json"))
    admission = build_method_reuse_admission(request)
    if admission.status is MethodReuseAdmissionStatus.HOLD:
        return _result(request=request, admission=admission, frontier_result=None)

    frontier = await execute_verified_novel_frontier(
        gateway=gateway,
        request=request.frontier_request,
    )
    return _result(request=request, admission=admission, frontier_result=frontier)
