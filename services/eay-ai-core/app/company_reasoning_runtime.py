"""Company-scoped interlock for canonical Jarvis strong reasoning.

The strong reasoning executor is shared infrastructure. Enterprise reasoning that
uses Company Brain context must first prove an exact tenant + company + profile
binding. This module performs that fail-closed binding and then delegates to the
canonical StrongReasoningRuntime; it does not create a second model/provider,
truth, payment, or execution authority.

A valid Company Brain binding proves only which company context was selected.
It never upgrades context into authoritative Company World truth and never
authorizes a business side effect.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from .company_brain_runtime import (
    CompanyRuntimeDisposition,
    CompanyRuntimeRequestBinding,
    validate_company_runtime_request_binding,
)
from .company_context_boundary import CompanyContextPlane, CompanyContextSnapshot
from .intelligence_router import IntelligenceTask
from .intelligence_supremacy import InformationGainPlan, ReasoningStrengthPlan
from .paid_token_engine_gateway import PaidTokenExecutionContext
from .strong_reasoning_runtime import StrongReasoningExecution

COMPANY_REASONING_RUNTIME_CONTRACT = "eay-company-reasoning-runtime-v1"
COMPANY_REASONING_REQUIRED_PLANES: tuple[CompanyContextPlane, ...] = (
    CompanyContextPlane.KNOWLEDGE,
    CompanyContextPlane.MODEL_PROFILE,
)


class StrongReasoningExecutor(Protocol):
    async def execute(
        self,
        *,
        plan: ReasoningStrengthPlan,
        information_gain: InformationGainPlan,
        task: IntelligenceTask,
        prompt: str,
        claim_keys: tuple[str, ...],
        allowed_evidence_refs: tuple[str, ...],
        context: PaidTokenExecutionContext,
    ) -> StrongReasoningExecution: ...


class CompanyReasoningExecution(BaseModel):
    contract: str = COMPANY_REASONING_RUNTIME_CONTRACT
    task_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    profile_revision: str = Field(min_length=1)
    company_identity_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_context_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_runtime_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_execution: StrongReasoningExecution
    cross_company_fallback_allowed: bool = False
    firm_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def execution_is_integral_and_non_authoritative(self) -> "CompanyReasoningExecution":
        if self.task_id != self.reasoning_execution.task_id:
            raise ValueError("company_reasoning_task_result_mismatch")
        if self.cross_company_fallback_allowed:
            raise ValueError("company_reasoning_cross_company_fallback_forbidden")
        if self.firm_truth_authority_granted:
            raise ValueError("company_reasoning_never_grants_firm_truth")
        if self.execution_authority_granted:
            raise ValueError("company_reasoning_never_grants_execution_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("company_reasoning_execution_fingerprint_mismatch")
        return self


@dataclass(frozen=True)
class CompanyReasoningRuntime:
    reasoning_runtime: StrongReasoningExecutor

    async def execute(
        self,
        *,
        company_snapshot: CompanyContextSnapshot,
        company_binding: CompanyRuntimeRequestBinding,
        plan: ReasoningStrengthPlan,
        information_gain: InformationGainPlan,
        task: IntelligenceTask,
        prompt: str,
        claim_keys: tuple[str, ...],
        allowed_evidence_refs: tuple[str, ...],
        context: PaidTokenExecutionContext,
    ) -> CompanyReasoningExecution:
        snapshot = CompanyContextSnapshot.model_validate(
            company_snapshot.model_dump(mode="json")
        )
        binding = validate_company_runtime_request_binding(
            binding=company_binding,
            snapshot=snapshot,
        )
        required = set(COMPANY_REASONING_REQUIRED_PLANES)
        if not required.issubset(set(binding.required_planes)):
            raise ValueError("company_reasoning_required_planes_not_bound")
        if binding.disposition is not CompanyRuntimeDisposition.PROCEED:
            raise ValueError(
                "company_reasoning_company_brain_not_ready:"
                + ",".join(binding.blockers)
            )
        if binding.request_id != task.task_id:
            raise ValueError("company_reasoning_task_binding_mismatch")
        if context.tenant_ref != binding.tenant_id:
            raise ValueError("company_reasoning_paid_context_tenant_mismatch")

        reasoning = StrongReasoningExecution.model_validate(
            (
                await self.reasoning_runtime.execute(
                    plan=plan,
                    information_gain=information_gain,
                    task=task,
                    prompt=prompt,
                    claim_keys=claim_keys,
                    allowed_evidence_refs=allowed_evidence_refs,
                    context=context,
                )
            ).model_dump(mode="json")
        )
        draft = {
            "contract": COMPANY_REASONING_RUNTIME_CONTRACT,
            "task_id": task.task_id,
            "tenant_id": binding.tenant_id,
            "company_id": binding.company_id,
            "profile_revision": binding.profile_revision,
            "company_identity_fingerprint": binding.company_identity_fingerprint,
            "company_context_snapshot_fingerprint": (
                binding.company_context_snapshot_fingerprint
            ),
            "company_runtime_binding_fingerprint": binding.fingerprint,
            "reasoning_execution": reasoning.model_dump(mode="json"),
            "cross_company_fallback_allowed": False,
            "firm_truth_authority_granted": False,
            "execution_authority_granted": False,
        }
        return CompanyReasoningExecution.model_validate(
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
