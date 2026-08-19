"""Bridge Information-Gain selections to canonical reviewed company reads.

The Intelligence Supremacy planner can decide that a company read would reduce
uncertainty. That decision must not let a model invent SQL, URLs, credentials or
an alternate truth path. This bridge binds selected COMPANY_READ investigations
to pre-reviewed ReadOnlySourcePlan objects and executes them only through the
existing Company Source Adapter Registry/runtime.

Collection remains collection evidence. No result here becomes Company World
truth without the existing independent LiveSourceAttestation promotion path.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .company_source_adapter_execution import (
    CompanySourceExecutionReceipt,
    CompanySourceRuntimeBinding,
    execute_registered_company_read,
)
from .company_source_adapter_registry import CompanySourceAdapterRegistry
from .intelligence_supremacy import (
    InformationGainPlan,
    InvestigationCandidate,
    InvestigationKind,
)
from .live_company_reality import LiveSourceBindingPolicy
from .live_company_source_runtime import ReadOnlySourcePlan

INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT = "eay-information-gain-company-bridge-v1"


class CompanyInvestigationDisposition(str, Enum):
    COLLECTED = "collected"
    BLOCKED_EXTERNAL = "blocked_external"


class ReviewedCompanyInvestigation(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    investigation_id: str = Field(min_length=1)
    investigation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_ref: str = Field(min_length=1)
    plan: ReadOnlySourcePlan
    policy_binding_id: str = Field(min_length=1)
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def reviewed_mapping_is_non_authoritative(self) -> "ReviewedCompanyInvestigation":
        if self.truth_authority_granted or self.execution_authority_granted:
            raise ValueError("company_investigation_mapping_never_grants_authority")
        if self.plan.binding_id != self.policy_binding_id:
            raise ValueError("company_investigation_policy_binding_mismatch")
        return self


class CompanyInvestigationRegistry(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    tenant_id: str = Field(min_length=1)
    mappings: tuple[ReviewedCompanyInvestigation, ...]

    @model_validator(mode="after")
    def mappings_are_unique_and_tenant_bound(self) -> "CompanyInvestigationRegistry":
        ids = [item.investigation_id for item in self.mappings]
        if len(ids) != len(set(ids)):
            raise ValueError("company_investigation_duplicate_mapping")
        if any(item.plan.tenant_id != self.tenant_id for item in self.mappings):
            raise ValueError("company_investigation_cross_tenant_mapping")
        return self


class PreparedCompanyInvestigation(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    investigation_id: str
    adapter_ref: str
    plan: ReadOnlySourcePlan
    policy_binding_id: str
    investigation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False


class InformationGainCompanyPreparation(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    tenant_id: str
    prepared: tuple[PreparedCompanyInvestigation, ...]
    delegated_investigation_ids: tuple[str, ...]
    automatic_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def preparation_never_grants_authority(self) -> "InformationGainCompanyPreparation":
        if self.automatic_execution_authority_granted:
            raise ValueError("company_investigation_preparation_never_grants_execution")
        return self


class CompanyInvestigationExecution(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    investigation_id: str
    disposition: CompanyInvestigationDisposition
    receipt: CompanySourceExecutionReceipt | None = None
    blocker: str | None = None

    @model_validator(mode="after")
    def result_shape_matches_disposition(self) -> "CompanyInvestigationExecution":
        if self.disposition is CompanyInvestigationDisposition.COLLECTED:
            if self.receipt is None or self.blocker is not None:
                raise ValueError("company_investigation_collected_result_invalid")
            if self.receipt.truth_promoted or self.receipt.execution_authority_granted:
                raise ValueError("company_investigation_collection_cannot_grant_authority")
        else:
            if self.receipt is not None or not self.blocker:
                raise ValueError("company_investigation_blocked_result_invalid")
        return self


class InformationGainCompanyExecution(BaseModel):
    contract: str = INFORMATION_GAIN_COMPANY_BRIDGE_CONTRACT
    tenant_id: str
    results: tuple[CompanyInvestigationExecution, ...]
    delegated_investigation_ids: tuple[str, ...]
    truth_promoted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def execution_is_collection_only(self) -> "InformationGainCompanyExecution":
        if self.truth_promoted:
            raise ValueError("information_gain_company_bridge_never_promotes_truth")
        if self.execution_authority_granted:
            raise ValueError("information_gain_company_bridge_never_grants_execution")
        return self


def investigation_fingerprint(candidate: InvestigationCandidate) -> str:
    payload = candidate.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def prepare_information_gain_company_reads(
    *,
    information_gain: InformationGainPlan,
    investigations: tuple[InvestigationCandidate, ...],
    registry: CompanyInvestigationRegistry,
) -> InformationGainCompanyPreparation:
    candidates = {item.investigation_id: item for item in investigations}
    if len(candidates) != len(investigations):
        raise ValueError("company_investigation_duplicate_candidate_id")
    mappings = {item.investigation_id: item for item in registry.mappings}
    prepared: list[PreparedCompanyInvestigation] = []
    delegated: list[str] = []

    for investigation_id in information_gain.selected_investigation_ids:
        candidate = candidates.get(investigation_id)
        if candidate is None:
            raise ValueError("company_investigation_selected_candidate_missing")
        if candidate.kind is not InvestigationKind.COMPANY_READ:
            delegated.append(investigation_id)
            continue
        mapping = mappings.get(investigation_id)
        if mapping is None:
            raise ValueError("company_investigation_selected_company_read_not_reviewed")
        actual_fingerprint = investigation_fingerprint(candidate)
        if mapping.investigation_fingerprint != actual_fingerprint:
            raise ValueError("company_investigation_candidate_fingerprint_mismatch")
        if mapping.plan.tenant_id != registry.tenant_id:
            raise ValueError("company_investigation_plan_tenant_mismatch")
        prepared.append(
            PreparedCompanyInvestigation(
                investigation_id=investigation_id,
                adapter_ref=mapping.adapter_ref,
                plan=mapping.plan,
                policy_binding_id=mapping.policy_binding_id,
                investigation_fingerprint=actual_fingerprint,
            )
        )

    return InformationGainCompanyPreparation(
        tenant_id=registry.tenant_id,
        prepared=tuple(prepared),
        delegated_investigation_ids=tuple(delegated),
    )


def execute_information_gain_company_reads(
    *,
    preparation: InformationGainCompanyPreparation,
    company_source_registry: CompanySourceAdapterRegistry,
    policies: Mapping[str, LiveSourceBindingPolicy],
    runtime_bindings: Mapping[str, CompanySourceRuntimeBinding],
) -> InformationGainCompanyExecution:
    if company_source_registry.tenant_id != preparation.tenant_id:
        raise ValueError("company_investigation_source_registry_tenant_mismatch")
    results: list[CompanyInvestigationExecution] = []

    for item in preparation.prepared:
        policy = policies.get(item.policy_binding_id)
        if policy is None:
            raise ValueError("company_investigation_policy_not_registered")
        if policy.tenant_id != preparation.tenant_id:
            raise ValueError("company_investigation_policy_tenant_mismatch")
        if item.adapter_ref not in runtime_bindings:
            results.append(
                CompanyInvestigationExecution(
                    investigation_id=item.investigation_id,
                    disposition=CompanyInvestigationDisposition.BLOCKED_EXTERNAL,
                    blocker="company_investigation_runtime_binding_missing",
                )
            )
            continue

        receipt = execute_registered_company_read(
            registry=company_source_registry,
            plan=item.plan,
            policy=policy,
            adapter_ref=item.adapter_ref,
            runtime_bindings=runtime_bindings,
        )
        results.append(
            CompanyInvestigationExecution(
                investigation_id=item.investigation_id,
                disposition=CompanyInvestigationDisposition.COLLECTED,
                receipt=receipt,
            )
        )

    return InformationGainCompanyExecution(
        tenant_id=preparation.tenant_id,
        results=tuple(results),
        delegated_investigation_ids=preparation.delegated_investigation_ids,
    )
