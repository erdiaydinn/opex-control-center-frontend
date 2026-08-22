"""Bind Work-style plans to the existing governed Jarvis agent control plane.

This bridge deliberately creates no scheduler and executes no tools. It proves
that an admitted Work plan, specialist mastery decision and attested delegated
worker all refer to the same immutable plan and company scope, then creates the
canonical durable AgentJobSnapshot used by the existing lifecycle/repository.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .agent_job_lifecycle import AgentJobSnapshot, new_agent_job
from .hierarchical_agent_delegation import AgentDelegationAdmission, HiredAgentLease
from .specialist_mastery_registry import (
    MasteryTier,
    SpecialistDomain,
    SpecialistMasteryDecision,
)
from .workstyle_agent_os import (
    WorkPlan,
    WorkPlanAdmission,
    WorkTaskDisposition,
    WorkTaskSpec,
)

WORKSTYLE_CONTROL_PLANE_BRIDGE_CONTRACT = "eay-workstyle-control-plane-bridge-v1"


class WorkAgentAssignment(BaseModel):
    task_id: str = Field(min_length=1)
    child_agent_id: str = Field(min_length=1)
    capability_refs: tuple[str, ...]
    mastery_decision_fingerprints: tuple[str, ...]
    company_scope_ref: str = Field(min_length=1)


class WorkControlPlaneBundle(BaseModel):
    contract: str = WORKSTYLE_CONTROL_PLANE_BRIDGE_CONTRACT
    tenant_id: str
    company_id: str
    session_id: str
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    work_admission_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    delegation_admission_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    assignments: tuple[WorkAgentAssignment, ...]
    agent_job: AgentJobSnapshot
    business_execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def bundle_is_integral_and_non_authoritative(self) -> "WorkControlPlaneBundle":
        if self.business_execution_authority_granted:
            raise ValueError("work_bridge_never_grants_business_execution_authority")
        if self.agent_job.tenant_id != self.tenant_id:
            raise ValueError("work_bridge_agent_job_tenant_mismatch")
        if self.agent_job.objective_ref != self.plan_fingerprint:
            raise ValueError("work_bridge_agent_job_plan_mismatch")
        if {item.child_agent_id for item in self.assignments} != set(
            self.agent_job.required_child_agent_ids
        ):
            raise ValueError("work_bridge_assignment_job_children_mismatch")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("work_bridge_fingerprint_mismatch")
        return self


def compose_work_control_plane(
    *,
    plan: WorkPlan,
    work_admission: WorkPlanAdmission,
    delegation: AgentDelegationAdmission,
    mastery_decisions: tuple[SpecialistMasteryDecision, ...],
    root_agent_id: str,
) -> WorkControlPlaneBundle:
    """Create a canonical durable agent job from an exact admitted Work plan."""

    resolved_plan = WorkPlan.model_validate(plan.model_dump(mode="json"))
    admission = WorkPlanAdmission.model_validate(
        work_admission.model_dump(mode="json")
    )
    delegated = AgentDelegationAdmission.model_validate(
        delegation.model_dump(mode="json")
    )
    if not root_agent_id:
        raise ValueError("work_bridge_root_agent_required")
    if (
        admission.tenant_id != resolved_plan.tenant_id
        or admission.company_id != resolved_plan.company_id
        or admission.session_id != resolved_plan.session_id
    ):
        raise ValueError("work_bridge_admission_scope_mismatch")
    if admission.plan_revision != resolved_plan.revision:
        raise ValueError("work_bridge_admission_revision_mismatch")
    if admission.plan_fingerprint != resolved_plan.fingerprint:
        raise ValueError("work_bridge_admission_plan_fingerprint_mismatch")
    if not admission.all_tasks_ready or any(
        item.disposition is not WorkTaskDisposition.READY
        for item in admission.task_admissions
    ):
        raise ValueError("work_bridge_plan_not_fully_admitted")
    if delegated.tenant_id != resolved_plan.tenant_id:
        raise ValueError("work_bridge_delegation_tenant_mismatch")
    if delegated.objective_ref != resolved_plan.fingerprint:
        raise ValueError("work_bridge_delegation_plan_fingerprint_mismatch")

    company_scope = f"company:{resolved_plan.company_id}"
    leases = tuple(
        HiredAgentLease.model_validate(item.model_dump(mode="json"))
        for item in delegated.leases
    )
    for lease in leases:
        if lease.parent_session_ref != resolved_plan.session_id:
            raise ValueError("work_bridge_delegation_session_mismatch")
        if lease.objective_ref != resolved_plan.fingerprint:
            raise ValueError("work_bridge_lease_plan_fingerprint_mismatch")
        if company_scope not in set(lease.authority_scope_refs):
            raise ValueError("work_bridge_company_scope_missing")

    mastery_by_domain: dict[SpecialistDomain, SpecialistMasteryDecision] = {}
    for raw in mastery_decisions:
        decision = SpecialistMasteryDecision.model_validate(raw.model_dump(mode="json"))
        if decision.domain in mastery_by_domain:
            raise ValueError("work_bridge_duplicate_mastery_domain")
        mastery_by_domain[decision.domain] = decision

    assignments: list[WorkAgentAssignment] = []
    unused = {item.child_agent_id: item for item in leases}
    for task in resolved_plan.tasks:
        lease, mastery_fingerprints = _assign_task(
            task=task,
            unused=unused,
            mastery_by_domain=mastery_by_domain,
            company_scope=company_scope,
        )
        assignments.append(
            WorkAgentAssignment(
                task_id=task.task_id,
                child_agent_id=lease.child_agent_id,
                capability_refs=lease.capability_refs,
                mastery_decision_fingerprints=mastery_fingerprints,
                company_scope_ref=company_scope,
            )
        )
        unused.pop(lease.child_agent_id)

    job_id = _fingerprint(
        {
            "contract": WORKSTYLE_CONTROL_PLANE_BRIDGE_CONTRACT,
            "tenant_id": resolved_plan.tenant_id,
            "company_id": resolved_plan.company_id,
            "session_id": resolved_plan.session_id,
            "plan_fingerprint": resolved_plan.fingerprint,
            "delegation_admission_fingerprint": delegated.admission_fingerprint,
            "root_agent_id": root_agent_id,
        }
    )
    job = new_agent_job(
        job_id=job_id,
        objective_ref=resolved_plan.fingerprint,
        tenant_id=resolved_plan.tenant_id,
        root_agent_id=root_agent_id,
        child_agent_ids=tuple(item.child_agent_id for item in assignments),
    )
    draft = {
        "contract": WORKSTYLE_CONTROL_PLANE_BRIDGE_CONTRACT,
        "tenant_id": resolved_plan.tenant_id,
        "company_id": resolved_plan.company_id,
        "session_id": resolved_plan.session_id,
        "plan_fingerprint": resolved_plan.fingerprint,
        "work_admission_fingerprint": admission.fingerprint,
        "delegation_admission_fingerprint": delegated.admission_fingerprint,
        "assignments": [item.model_dump(mode="json") for item in assignments],
        "agent_job": job.model_dump(mode="json"),
        "business_execution_authority_granted": False,
    }
    return WorkControlPlaneBundle.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _assign_task(
    *,
    task: WorkTaskSpec,
    unused: dict[str, HiredAgentLease],
    mastery_by_domain: dict[SpecialistDomain, SpecialistMasteryDecision],
    company_scope: str,
) -> tuple[HiredAgentLease, tuple[str, ...]]:
    required_capabilities = {f"work:{item.value}" for item in task.required_capabilities}
    required_specialist_ids: set[str] = set()
    mastery_fingerprints: list[str] = []
    for requirement in task.specialist_requirements:
        decision = mastery_by_domain.get(requirement.domain)
        if decision is None:
            raise ValueError("work_bridge_specialist_mastery_missing")
        if _tier_rank(decision.admitted_tier) < _tier_rank(requirement.minimum_tier):
            raise ValueError("work_bridge_specialist_mastery_insufficient")
        required_specialist_ids.add(decision.specialist_id)
        mastery_fingerprints.append(decision.fingerprint)
    if len(required_specialist_ids) > 1:
        raise ValueError("work_bridge_task_requires_specialist_decomposition")

    specialist_id = next(iter(required_specialist_ids), None)
    candidates = [
        lease
        for lease in unused.values()
        if (specialist_id is None or lease.child_agent_id == specialist_id)
        and required_capabilities.issubset(set(lease.capability_refs))
        and company_scope in set(lease.authority_scope_refs)
    ]
    candidates.sort(key=lambda item: item.child_agent_id)
    if not candidates:
        if specialist_id is not None:
            raise ValueError("work_bridge_specialist_worker_unavailable")
        raise ValueError("work_bridge_capable_worker_unavailable")
    return candidates[0], tuple(mastery_fingerprints)


def _tier_rank(tier: MasteryTier) -> int:
    return {
        MasteryTier.UNADMITTED: 0,
        MasteryTier.PRACTITIONER: 1,
        MasteryTier.EXPERT: 2,
        MasteryTier.MASTER: 3,
    }[tier]


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
