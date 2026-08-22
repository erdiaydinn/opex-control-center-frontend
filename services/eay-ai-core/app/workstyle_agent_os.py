"""Persistent Work-style orchestration contract for Jarvis.

This module models the user-facing operating principle of a long-running work
session: decompose an objective into a dependency-aware plan, bind capabilities
and admitted specialists, preserve artifacts and progress, accept steering, and
hold consequential actions until an exact approval exists.

It intentionally does not execute tools, mint credentials, or grant business
authority. READY means ready to enter the existing governed dispatcher. Any real
mutation must still pass the Jarvis authority, budget, fencing, connector and
execution-receipt layers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .specialist_mastery_registry import (
    MasteryTier,
    SpecialistDomain,
    SpecialistMasteryDecision,
)

WORKSTYLE_AGENT_OS_CONTRACT = "eay-workstyle-agent-os-v1"


class WorkCapability(str, Enum):
    REASONING = "reasoning"
    DEEP_RESEARCH = "deep_research"
    CURRENT_WORLD = "current_world"
    CODE = "code"
    FILES = "files"
    DOCUMENTS = "documents"
    SPREADSHEETS = "spreadsheets"
    PRESENTATIONS = "presentations"
    VISION = "vision"
    COMMUNICATIONS = "communications"
    DATA_ANALYTICS = "data_analytics"
    PLANNING = "planning"
    RPA = "rpa"
    DOMAIN_EXPERT = "domain_expert"


class WorkActionClass(str, Enum):
    READ_ONLY = "read_only"
    ARTIFACT_WRITE = "artifact_write"
    EXTERNAL_MUTATION = "external_mutation"
    HIGH_IMPACT = "high_impact"


class RPAExecutionMode(str, Enum):
    OBSERVE = "observe"
    PLAN = "plan"
    DRY_RUN = "dry_run"
    ARTIFACT_MUTATION = "artifact_mutation"
    EXTERNAL_MUTATION = "external_mutation"


class WorkTaskDisposition(str, Enum):
    READY = "ready"
    HOLD = "hold"


class WorkTaskState(str, Enum):
    PLANNED = "planned"
    READY = "ready"
    HOLD = "hold"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    INVALIDATED = "invalidated"


class WorkSessionState(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    HELD = "held"
    COMPLETE = "complete"
    CANCELED = "canceled"


class SpecialistRequirement(BaseModel):
    domain: SpecialistDomain
    minimum_tier: MasteryTier = MasteryTier.EXPERT

    @model_validator(mode="after")
    def minimum_tier_must_be_admitted(self) -> "SpecialistRequirement":
        if self.minimum_tier is MasteryTier.UNADMITTED:
            raise ValueError("work_specialist_requirement_must_be_admitted")
        return self


class WorkTaskSpec(BaseModel):
    task_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    required_capabilities: tuple[WorkCapability, ...] = Field(min_length=1)
    specialist_requirements: tuple[SpecialistRequirement, ...] = ()
    dependencies: tuple[str, ...] = ()
    action_class: WorkActionClass = WorkActionClass.READ_ONLY
    rpa_mode: RPAExecutionMode | None = None
    input_artifact_ids: tuple[str, ...] = ()
    output_artifact_kinds: tuple[str, ...] = ()

    @model_validator(mode="after")
    def task_contract_is_consistent(self) -> "WorkTaskSpec":
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("work_task_capabilities_must_be_unique")
        domains = tuple(item.domain for item in self.specialist_requirements)
        if len(set(domains)) != len(domains):
            raise ValueError("work_task_specialist_requirements_must_be_unique")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("work_task_dependencies_must_be_unique")
        if self.task_id in self.dependencies:
            raise ValueError("work_task_cannot_depend_on_itself")
        if self.rpa_mode is not None and WorkCapability.RPA not in set(
            self.required_capabilities
        ):
            raise ValueError("work_rpa_mode_requires_rpa_capability")
        if (
            self.rpa_mode is RPAExecutionMode.EXTERNAL_MUTATION
            and self.action_class
            not in {
                WorkActionClass.EXTERNAL_MUTATION,
                WorkActionClass.HIGH_IMPACT,
            }
        ):
            raise ValueError("work_external_rpa_requires_mutation_action_class")
        return self


class WorkPlan(BaseModel):
    contract: str = WORKSTYLE_AGENT_OS_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    objective: str = Field(min_length=1)
    tasks: tuple[WorkTaskSpec, ...] = Field(min_length=1)
    created_at: datetime
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def plan_is_integral(self) -> "WorkPlan":
        _require_aware(self.created_at, "work_plan_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("work_plan_never_grants_execution_authority")
        task_ids = tuple(item.task_id for item in self.tasks)
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("work_plan_task_ids_must_be_unique")
        known = set(task_ids)
        for task in self.tasks:
            if set(task.dependencies) - known:
                raise ValueError("work_plan_dependency_unknown")
        _require_acyclic(self.tasks)
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("work_plan_fingerprint_mismatch")
        return self


class WorkApprovalReceipt(BaseModel):
    contract: str = WORKSTYLE_AGENT_OS_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    plan_revision: int = Field(ge=1)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id: str = Field(min_length=1)
    action_class: WorkActionClass
    approved_by: str = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    credential_material_present: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def approval_is_narrow_and_integral(self) -> "WorkApprovalReceipt":
        _require_aware(self.issued_at, "work_approval_requires_timezone")
        _require_aware(self.expires_at, "work_approval_expiry_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("work_approval_expiry_must_follow_issue")
        if self.action_class not in {
            WorkActionClass.EXTERNAL_MUTATION,
            WorkActionClass.HIGH_IMPACT,
        }:
            raise ValueError("work_approval_only_for_consequential_action")
        if self.credential_material_present:
            raise ValueError("work_approval_must_not_embed_credentials")
        if self.execution_authority_granted:
            raise ValueError("work_approval_does_not_grant_execution_authority")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("work_approval_fingerprint_mismatch")
        return self


class WorkTaskAdmission(BaseModel):
    task_id: str
    disposition: WorkTaskDisposition
    blockers: tuple[str, ...]
    approval_bound: bool
    ready_for_governed_dispatch: bool
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_remains_non_authoritative(self) -> "WorkTaskAdmission":
        if self.execution_authority_granted:
            raise ValueError("work_task_admission_never_grants_execution_authority")
        if self.ready_for_governed_dispatch != (
            self.disposition is WorkTaskDisposition.READY
        ):
            raise ValueError("work_task_dispatch_readiness_mismatch")
        return self


class WorkPlanAdmission(BaseModel):
    contract: str = WORKSTYLE_AGENT_OS_CONTRACT
    tenant_id: str
    company_id: str
    session_id: str
    plan_revision: int
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime
    task_admissions: tuple[WorkTaskAdmission, ...]
    all_tasks_ready: bool
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def admission_is_integral(self) -> "WorkPlanAdmission":
        _require_aware(self.evaluated_at, "work_admission_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("work_plan_admission_never_grants_execution_authority")
        expected_all_ready = all(
            item.disposition is WorkTaskDisposition.READY
            for item in self.task_admissions
        )
        if self.all_tasks_ready != expected_all_ready:
            raise ValueError("work_plan_all_ready_mismatch")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("work_plan_admission_fingerprint_mismatch")
        return self


class WorkArtifactRef(BaseModel):
    artifact_id: str = Field(min_length=1)
    artifact_kind: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_task_id: str = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def artifact_requires_timezone(self) -> "WorkArtifactRef":
        _require_aware(self.created_at, "work_artifact_requires_timezone")
        return self


class WorkProgressEvent(BaseModel):
    event_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    state: WorkTaskState
    observed_at: datetime
    summary: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def progress_requires_timezone(self) -> "WorkProgressEvent":
        _require_aware(self.observed_at, "work_progress_requires_timezone")
        return self


class WorkSteeringReceipt(BaseModel):
    previous_revision: int = Field(ge=1)
    new_revision: int = Field(ge=2)
    issued_at: datetime
    issued_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    invalidated_task_ids: tuple[str, ...]
    previous_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def steering_is_sequential(self) -> "WorkSteeringReceipt":
        _require_aware(self.issued_at, "work_steering_requires_timezone")
        if self.new_revision != self.previous_revision + 1:
            raise ValueError("work_steering_revision_must_increment_once")
        return self


class WorkSessionSnapshot(BaseModel):
    contract: str = WORKSTYLE_AGENT_OS_CONTRACT
    tenant_id: str
    company_id: str
    session_id: str
    state: WorkSessionState
    current_plan: WorkPlan
    artifacts: tuple[WorkArtifactRef, ...] = ()
    progress_events: tuple[WorkProgressEvent, ...] = ()
    steering_receipts: tuple[WorkSteeringReceipt, ...] = ()
    updated_at: datetime
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def session_is_integral(self) -> "WorkSessionSnapshot":
        _require_aware(self.updated_at, "work_session_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("work_session_never_grants_execution_authority")
        if (
            self.current_plan.tenant_id != self.tenant_id
            or self.current_plan.company_id != self.company_id
            or self.current_plan.session_id != self.session_id
        ):
            raise ValueError("work_session_plan_scope_mismatch")
        task_ids = {item.task_id for item in self.current_plan.tasks}
        if any(item.producer_task_id not in task_ids for item in self.artifacts):
            raise ValueError("work_session_artifact_task_unknown")
        if any(item.task_id not in task_ids for item in self.progress_events):
            raise ValueError("work_session_progress_task_unknown")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("work_session_fingerprint_mismatch")
        return self


def build_work_plan(
    *,
    tenant_id: str,
    company_id: str,
    session_id: str,
    revision: int,
    objective: str,
    tasks: tuple[WorkTaskSpec, ...],
    created_at: datetime,
) -> WorkPlan:
    draft = {
        "contract": WORKSTYLE_AGENT_OS_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "session_id": session_id,
        "revision": revision,
        "objective": objective,
        "tasks": [item.model_dump(mode="json") for item in tasks],
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "execution_authority_granted": False,
    }
    return WorkPlan.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_work_approval(
    *,
    plan: WorkPlan,
    task_id: str,
    action_class: WorkActionClass,
    approved_by: str,
    issued_at: datetime,
    expires_at: datetime,
) -> WorkApprovalReceipt:
    if task_id not in {item.task_id for item in plan.tasks}:
        raise ValueError("work_approval_task_unknown")
    draft = {
        "contract": WORKSTYLE_AGENT_OS_CONTRACT,
        "tenant_id": plan.tenant_id,
        "company_id": plan.company_id,
        "session_id": plan.session_id,
        "plan_revision": plan.revision,
        "plan_fingerprint": plan.fingerprint,
        "task_id": task_id,
        "action_class": action_class.value,
        "approved_by": approved_by,
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "credential_material_present": False,
        "execution_authority_granted": False,
    }
    return WorkApprovalReceipt.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def admit_work_plan(
    *,
    plan: WorkPlan,
    available_capabilities: tuple[WorkCapability, ...],
    mastery_decisions: tuple[SpecialistMasteryDecision, ...],
    approvals: tuple[WorkApprovalReceipt, ...],
    now: datetime,
) -> WorkPlanAdmission:
    """Evaluate whether every task may enter the governed dispatcher."""

    _require_aware(now, "work_admission_now_requires_timezone")
    validated_plan = WorkPlan.model_validate(plan.model_dump(mode="json"))
    capabilities = set(available_capabilities)
    if len(capabilities) != len(available_capabilities):
        raise ValueError("work_available_capabilities_must_be_unique")

    mastery_by_domain: dict[SpecialistDomain, SpecialistMasteryDecision] = {}
    for raw in mastery_decisions:
        decision = SpecialistMasteryDecision.model_validate(raw.model_dump(mode="json"))
        if decision.domain in mastery_by_domain:
            raise ValueError("work_duplicate_specialist_mastery_decision")
        mastery_by_domain[decision.domain] = decision

    approvals_by_task: dict[str, WorkApprovalReceipt] = {}
    for raw in approvals:
        receipt = WorkApprovalReceipt.model_validate(raw.model_dump(mode="json"))
        if (
            receipt.tenant_id != validated_plan.tenant_id
            or receipt.company_id != validated_plan.company_id
            or receipt.session_id != validated_plan.session_id
        ):
            raise ValueError("work_approval_scope_mismatch")
        if receipt.plan_revision != validated_plan.revision:
            raise ValueError("work_approval_plan_revision_mismatch")
        if receipt.plan_fingerprint != validated_plan.fingerprint:
            raise ValueError("work_approval_plan_fingerprint_mismatch")
        if receipt.task_id in approvals_by_task:
            raise ValueError("work_duplicate_task_approval")
        approvals_by_task[receipt.task_id] = receipt

    admissions: list[WorkTaskAdmission] = []
    for task in validated_plan.tasks:
        blockers: list[str] = []
        missing_capabilities = set(task.required_capabilities) - capabilities
        blockers.extend(
            f"work_capability_unavailable:{item.value}"
            for item in sorted(missing_capabilities, key=lambda value: value.value)
        )

        for requirement in task.specialist_requirements:
            decision = mastery_by_domain.get(requirement.domain)
            if decision is None:
                blockers.append(
                    f"work_specialist_unadmitted:{requirement.domain.value}"
                )
                continue
            if _tier_rank(decision.admitted_tier) < _tier_rank(
                requirement.minimum_tier
            ):
                blockers.append(
                    "work_specialist_tier_insufficient:"
                    f"{requirement.domain.value}:"
                    f"{requirement.minimum_tier.value}"
                )

        approval_bound = False
        if task.action_class in {
            WorkActionClass.EXTERNAL_MUTATION,
            WorkActionClass.HIGH_IMPACT,
        }:
            receipt = approvals_by_task.get(task.task_id)
            if receipt is None:
                blockers.append("work_consequential_action_approval_required")
            elif receipt.action_class is not task.action_class:
                blockers.append("work_approval_action_class_mismatch")
            elif receipt.expires_at <= now:
                blockers.append("work_approval_expired")
            elif receipt.issued_at > now:
                blockers.append("work_approval_from_future")
            else:
                approval_bound = True

        disposition = (
            WorkTaskDisposition.READY if not blockers else WorkTaskDisposition.HOLD
        )
        admissions.append(
            WorkTaskAdmission(
                task_id=task.task_id,
                disposition=disposition,
                blockers=tuple(blockers),
                approval_bound=approval_bound,
                ready_for_governed_dispatch=(
                    disposition is WorkTaskDisposition.READY
                ),
                execution_authority_granted=False,
            )
        )

    draft = {
        "contract": WORKSTYLE_AGENT_OS_CONTRACT,
        "tenant_id": validated_plan.tenant_id,
        "company_id": validated_plan.company_id,
        "session_id": validated_plan.session_id,
        "plan_revision": validated_plan.revision,
        "plan_fingerprint": validated_plan.fingerprint,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "task_admissions": [item.model_dump(mode="json") for item in admissions],
        "all_tasks_ready": all(
            item.disposition is WorkTaskDisposition.READY for item in admissions
        ),
        "execution_authority_granted": False,
    }
    return WorkPlanAdmission.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def build_work_session(
    *,
    plan: WorkPlan,
    updated_at: datetime,
    state: WorkSessionState = WorkSessionState.PLANNING,
    artifacts: tuple[WorkArtifactRef, ...] = (),
    progress_events: tuple[WorkProgressEvent, ...] = (),
    steering_receipts: tuple[WorkSteeringReceipt, ...] = (),
) -> WorkSessionSnapshot:
    draft = {
        "contract": WORKSTYLE_AGENT_OS_CONTRACT,
        "tenant_id": plan.tenant_id,
        "company_id": plan.company_id,
        "session_id": plan.session_id,
        "state": state.value,
        "current_plan": plan.model_dump(mode="json"),
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
        "progress_events": [item.model_dump(mode="json") for item in progress_events],
        "steering_receipts": [
            item.model_dump(mode="json") for item in steering_receipts
        ],
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
        "execution_authority_granted": False,
    }
    return WorkSessionSnapshot.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def steer_work_session(
    *,
    session: WorkSessionSnapshot,
    new_plan: WorkPlan,
    issued_at: datetime,
    issued_by: str,
    reason: str,
) -> WorkSessionSnapshot:
    """Replace the current plan and invalidate changed tasks plus dependants."""

    _require_aware(issued_at, "work_steering_now_requires_timezone")
    current = WorkSessionSnapshot.model_validate(session.model_dump(mode="json"))
    replacement = WorkPlan.model_validate(new_plan.model_dump(mode="json"))
    if (
        replacement.tenant_id != current.tenant_id
        or replacement.company_id != current.company_id
        or replacement.session_id != current.session_id
    ):
        raise ValueError("work_steering_scope_mismatch")
    if replacement.revision != current.current_plan.revision + 1:
        raise ValueError("work_steering_revision_must_increment_once")
    if issued_at < current.updated_at:
        raise ValueError("work_steering_time_regression")

    invalidated = _invalidated_tasks(current.current_plan, replacement)
    receipt = WorkSteeringReceipt(
        previous_revision=current.current_plan.revision,
        new_revision=replacement.revision,
        issued_at=issued_at,
        issued_by=issued_by,
        reason=reason,
        invalidated_task_ids=tuple(sorted(invalidated)),
        previous_plan_fingerprint=current.current_plan.fingerprint,
        new_plan_fingerprint=replacement.fingerprint,
    )
    replacement_ids = {task.task_id for task in replacement.tasks}
    preserved_progress = tuple(
        item
        for item in current.progress_events
        if item.task_id not in invalidated and item.task_id in replacement_ids
    )
    preserved_artifacts = tuple(
        item
        for item in current.artifacts
        if item.producer_task_id not in invalidated
        and item.producer_task_id in replacement_ids
    )
    return build_work_session(
        plan=replacement,
        updated_at=issued_at,
        state=WorkSessionState.PLANNING,
        artifacts=preserved_artifacts,
        progress_events=preserved_progress,
        steering_receipts=(*current.steering_receipts, receipt),
    )


def _invalidated_tasks(previous: WorkPlan, current: WorkPlan) -> set[str]:
    old = {item.task_id: item for item in previous.tasks}
    new = {item.task_id: item for item in current.tasks}
    changed = {
        task_id
        for task_id in set(old) | set(new)
        if task_id not in old
        or task_id not in new
        or old[task_id].model_dump(mode="json")
        != new[task_id].model_dump(mode="json")
    }
    invalidated = set(changed)
    grew = True
    while grew:
        grew = False
        for task in current.tasks:
            if task.task_id in invalidated:
                continue
            if set(task.dependencies) & invalidated:
                invalidated.add(task.task_id)
                grew = True
    return invalidated


def _tier_rank(tier: MasteryTier) -> int:
    return {
        MasteryTier.UNADMITTED: 0,
        MasteryTier.PRACTITIONER: 1,
        MasteryTier.EXPERT: 2,
        MasteryTier.MASTER: 3,
    }[tier]


def _require_acyclic(tasks: tuple[WorkTaskSpec, ...]) -> None:
    dependencies = {item.task_id: set(item.dependencies) for item in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            raise ValueError("work_plan_dependency_cycle")
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


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
