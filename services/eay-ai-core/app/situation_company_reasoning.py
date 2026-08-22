"""Bind reviewed Jarvis situations to exact company-scoped strong reasoning.

This adapter closes the runtime gap between situation detection/objective admission and
Company Brain-bound strong reasoning. It adds no new truth, causal, replanning,
payment, or business-execution authority.

A situation may reach this runtime only after the existing reviewed read-only
SituationObjectiveAdmission gate. The reasoning task id is deterministically bound
to the exact situation fingerprint + admitted objective. Exact situation/admission
root evidence must already be present in the allowed evidence set; this adapter does
not silently broaden evidence access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .company_brain_runtime import CompanyRuntimeRequestBinding
from .company_context_boundary import CompanyContextSnapshot
from .company_reasoning_runtime import CompanyReasoningExecution, CompanyReasoningRuntime
from .intelligence_router import IntelligenceTask
from .intelligence_supremacy import InformationGainPlan, ReasoningStrengthPlan
from .paid_token_engine_gateway import PaidTokenExecutionContext
from .situation_detection import SituationCandidate
from .situation_objective_admission import SituationObjectiveAdmission

SITUATION_COMPANY_REASONING_CONTRACT = "eay-situation-company-reasoning-v1"


class SituationCompanyReasoningExecution(BaseModel):
    contract: str = SITUATION_COMPANY_REASONING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    situation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    situation_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    rule_ref: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    company_runtime_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning: CompanyReasoningExecution
    causal_claim_proven: bool = False
    firm_truth_authority_granted: bool = False
    replanning_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def execution_is_integral_and_non_authoritative(
        self,
    ) -> "SituationCompanyReasoningExecution":
        if self.reasoning.task_id != self.task_id:
            raise ValueError("situation_company_reasoning_task_result_mismatch")
        if self.reasoning.tenant_id != self.tenant_id:
            raise ValueError("situation_company_reasoning_tenant_result_mismatch")
        if self.reasoning.company_id != self.company_id:
            raise ValueError("situation_company_reasoning_company_result_mismatch")
        if (
            self.reasoning.company_runtime_binding_fingerprint
            != self.company_runtime_binding_fingerprint
        ):
            raise ValueError("situation_company_reasoning_binding_result_mismatch")
        if (
            self.causal_claim_proven
            or self.firm_truth_authority_granted
            or self.replanning_authority_granted
            or self.execution_authority_granted
        ):
            raise ValueError("situation_company_reasoning_never_grants_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("situation_company_reasoning_execution_fingerprint_mismatch")
        return self


def situation_reasoning_task_id(
    *,
    candidate: SituationCandidate,
    admission: SituationObjectiveAdmission,
) -> str:
    candidate = SituationCandidate.model_validate(candidate.model_dump(mode="json"))
    admission = SituationObjectiveAdmission.model_validate(
        admission.model_dump(mode="json")
    )
    if admission.situation_fingerprint != candidate.fingerprint:
        raise ValueError("situation_company_reasoning_admission_candidate_mismatch")
    if admission.admitted.plan.tenant_id != candidate.tenant_id:
        raise ValueError("situation_company_reasoning_objective_tenant_mismatch")
    digest = _fingerprint(
        {
            "tenant_id": candidate.tenant_id,
            "situation_fingerprint": candidate.fingerprint,
            "objective_ref": admission.objective_ref,
            "rule_ref": admission.rule_ref,
        }
    )
    return f"situation-reasoning://{candidate.tenant_id}/{digest}"


@dataclass(frozen=True)
class SituationCompanyReasoningRuntime:
    company_reasoning_runtime: CompanyReasoningRuntime

    async def execute(
        self,
        *,
        candidate: SituationCandidate,
        admission: SituationObjectiveAdmission,
        company_snapshot: CompanyContextSnapshot,
        company_binding: CompanyRuntimeRequestBinding,
        plan: ReasoningStrengthPlan,
        information_gain: InformationGainPlan,
        task: IntelligenceTask,
        prompt: str,
        claim_keys: tuple[str, ...],
        allowed_evidence_refs: tuple[str, ...],
        context: PaidTokenExecutionContext,
    ) -> SituationCompanyReasoningExecution:
        candidate = SituationCandidate.model_validate(candidate.model_dump(mode="json"))
        admission = SituationObjectiveAdmission.model_validate(
            admission.model_dump(mode="json")
        )
        snapshot = CompanyContextSnapshot.model_validate(
            company_snapshot.model_dump(mode="json")
        )
        binding = CompanyRuntimeRequestBinding.model_validate(
            company_binding.model_dump(mode="json")
        )

        if not candidate.actionable_attention:
            raise ValueError("situation_company_reasoning_requires_actionable_attention")
        if admission.situation_fingerprint != candidate.fingerprint:
            raise ValueError("situation_company_reasoning_admission_candidate_mismatch")
        if admission.admitted.plan.tenant_id != candidate.tenant_id:
            raise ValueError("situation_company_reasoning_objective_tenant_mismatch")
        if admission.admitted.mutating_lane_count:
            raise ValueError("situation_company_reasoning_requires_read_only_admission")
        if snapshot.identity.tenant_id != candidate.tenant_id:
            raise ValueError("situation_company_reasoning_company_tenant_mismatch")
        if binding.tenant_id != candidate.tenant_id:
            raise ValueError("situation_company_reasoning_binding_tenant_mismatch")

        expected_task_id = situation_reasoning_task_id(
            candidate=candidate,
            admission=admission,
        )
        if task.task_id != expected_task_id:
            raise ValueError("situation_company_reasoning_task_binding_mismatch")
        if binding.request_id != expected_task_id:
            raise ValueError("situation_company_reasoning_company_request_mismatch")

        situation_ref = f"situation-candidate://{candidate.fingerprint}"
        required_evidence = tuple(
            dict.fromkeys(
                (
                    *candidate.evidence_refs,
                    situation_ref,
                    *admission.admitted.proposal_evidence_refs,
                )
            )
        )
        allowed = set(allowed_evidence_refs)
        missing = tuple(ref for ref in required_evidence if ref not in allowed)
        if missing:
            raise ValueError(
                "situation_company_reasoning_required_evidence_missing:"
                + ",".join(missing)
            )

        reasoning = await self.company_reasoning_runtime.execute(
            company_snapshot=snapshot,
            company_binding=binding,
            plan=plan,
            information_gain=information_gain,
            task=task,
            prompt=prompt,
            claim_keys=claim_keys,
            allowed_evidence_refs=allowed_evidence_refs,
            context=context,
        )
        draft = {
            "contract": SITUATION_COMPANY_REASONING_CONTRACT,
            "tenant_id": candidate.tenant_id,
            "company_id": reasoning.company_id,
            "situation_fingerprint": candidate.fingerprint,
            "situation_id": candidate.situation_id,
            "objective_ref": admission.objective_ref,
            "rule_ref": admission.rule_ref,
            "task_id": task.task_id,
            "company_runtime_binding_fingerprint": binding.fingerprint,
            "reasoning": reasoning.model_dump(mode="json"),
            "causal_claim_proven": False,
            "firm_truth_authority_granted": False,
            "replanning_authority_granted": False,
            "execution_authority_granted": False,
        }
        return SituationCompanyReasoningExecution.model_validate(
            {**draft, "fingerprint": _fingerprint(draft)}
        )


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
