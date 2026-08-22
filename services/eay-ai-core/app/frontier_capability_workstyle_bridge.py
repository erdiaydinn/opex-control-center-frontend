"""Bridge Frontier capability gaps into the existing Workstyle Agent OS.

The capability-gap controller produces evidence-bound remediation work, while
Workstyle Agent OS owns persistent dependency-aware work plans.  This adapter
connects the two without creating a scheduler and without converting a gap plan
into execution, training, provider, policy, code-change or Company Truth
authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .frontier_capability_gap_intelligence import (
    CapabilityGapWorkItem,
    CapabilityGapWorkKind,
    CapabilityImprovementPlan,
    CapabilityImprovementPlanState,
)
from .workstyle_agent_os import (
    WorkActionClass,
    WorkCapability,
    WorkPlan,
    WorkTaskSpec,
    build_work_plan,
)

FRONTIER_CAPABILITY_WORKSTYLE_BRIDGE_CONTRACT = (
    "eay-frontier-capability-workstyle-bridge-v1"
)
_DIGEST = r"^[0-9a-f]{64}$"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"


class CapabilityWorkstyleDisposition(str, Enum):
    PLANNED = "planned"
    NO_WORK = "no_work"


class CapabilityWorkTaskBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    work_item_id: str = Field(pattern=_DIGEST)
    task_id: str = Field(pattern=_SCOPE)
    priority: int = Field(ge=1, le=100)
    dependencies: tuple[str, ...]


class CapabilityWorkstyleBridgeArtifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str = FRONTIER_CAPABILITY_WORKSTYLE_BRIDGE_CONTRACT
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    session_id: str = Field(pattern=_SCOPE)
    source_plan_fingerprint: str = Field(pattern=_DIGEST)
    disposition: CapabilityWorkstyleDisposition
    task_bindings: tuple[CapabilityWorkTaskBinding, ...]
    work_plan: WorkPlan | None = None
    execution_authority_granted: bool = False
    automatic_training_allowed: bool = False
    automatic_code_change_allowed: bool = False
    automatic_provider_change_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    company_truth_promoted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def bridge_is_integral_and_non_authoritative(
        self,
    ) -> "CapabilityWorkstyleBridgeArtifact":
        if any(
            (
                self.execution_authority_granted,
                self.automatic_training_allowed,
                self.automatic_code_change_allowed,
                self.automatic_provider_change_allowed,
                self.automatic_policy_update_allowed,
                self.company_truth_promoted,
            )
        ):
            raise ValueError("capability_workstyle_bridge_never_mints_authority")
        if self.disposition is CapabilityWorkstyleDisposition.NO_WORK:
            if self.work_plan is not None or self.task_bindings:
                raise ValueError("capability_workstyle_no_work_must_be_empty")
        else:
            if self.work_plan is None or not self.task_bindings:
                raise ValueError("capability_workstyle_planned_requires_work_plan")
            if (
                self.work_plan.tenant_id != self.tenant_id
                or self.work_plan.company_id != self.company_id
                or self.work_plan.session_id != self.session_id
            ):
                raise ValueError("capability_workstyle_plan_scope_mismatch")
            if tuple(item.task_id for item in self.task_bindings) != tuple(
                item.task_id for item in self.work_plan.tasks
            ):
                raise ValueError("capability_workstyle_binding_task_order_mismatch")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("capability_workstyle_bridge_fingerprint_mismatch")
        return self


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


def _task_id(item: CapabilityGapWorkItem) -> str:
    return f"frontier-gap:{item.work_item_id[:32]}"


def _capabilities(kind: CapabilityGapWorkKind) -> tuple[WorkCapability, ...]:
    mapping = {
        CapabilityGapWorkKind.SAFETY_REMEDIATION: (
            WorkCapability.REASONING,
            WorkCapability.CODE,
            WorkCapability.DATA_ANALYTICS,
        ),
        CapabilityGapWorkKind.PROTOCOL_REPAIR: (
            WorkCapability.CODE,
            WorkCapability.DATA_ANALYTICS,
        ),
        CapabilityGapWorkKind.BENCHMARK_REFRESH: (
            WorkCapability.DATA_ANALYTICS,
            WorkCapability.REASONING,
        ),
        CapabilityGapWorkKind.PROVIDER_DIVERSITY: (
            WorkCapability.PLANNING,
            WorkCapability.REASONING,
        ),
        CapabilityGapWorkKind.EVALUATION_HARDENING: (
            WorkCapability.DATA_ANALYTICS,
            WorkCapability.CODE,
        ),
        CapabilityGapWorkKind.EVIDENCE_COMPLETION: (
            WorkCapability.DEEP_RESEARCH,
            WorkCapability.DATA_ANALYTICS,
        ),
        CapabilityGapWorkKind.CAPABILITY_IMPROVEMENT: (
            WorkCapability.REASONING,
            WorkCapability.CODE,
        ),
        CapabilityGapWorkKind.UNCERTAINTY_REDUCTION: (
            WorkCapability.DATA_ANALYTICS,
            WorkCapability.REASONING,
        ),
    }
    return mapping[kind]


def _sorted_work_items(
    work_items: tuple[CapabilityGapWorkItem, ...],
) -> tuple[CapabilityGapWorkItem, ...]:
    return tuple(
        sorted(
            work_items,
            key=lambda item: (
                -item.priority,
                item.domain.value,
                item.kind.value,
                item.work_item_id,
            ),
        )
    )


def build_capability_gap_workstyle_bridge(
    *,
    plan: CapabilityImprovementPlan,
    session_id: str,
    created_at: datetime,
) -> CapabilityWorkstyleBridgeArtifact:
    """Turn measurable open gaps into a bounded Workstyle work graph.

    Tasks are serialized only within the same certification domain, from highest
    priority to lowest priority.  Different domains remain parallelizable.  The
    bridge creates artifact-producing work only; no task is classified as an
    external mutation or high-impact action.
    """

    source = CapabilityImprovementPlan.model_validate(plan.model_dump(mode="json"))
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("capability_workstyle_created_at_requires_timezone")

    if source.state is CapabilityImprovementPlanState.COMPLETE:
        draft = {
            "contract": FRONTIER_CAPABILITY_WORKSTYLE_BRIDGE_CONTRACT,
            "tenant_id": source.tenant_id,
            "company_id": source.company_id,
            "session_id": session_id,
            "source_plan_fingerprint": source.fingerprint,
            "disposition": CapabilityWorkstyleDisposition.NO_WORK.value,
            "task_bindings": [],
            "work_plan": None,
            "execution_authority_granted": False,
            "automatic_training_allowed": False,
            "automatic_code_change_allowed": False,
            "automatic_provider_change_allowed": False,
            "automatic_policy_update_allowed": False,
            "company_truth_promoted": False,
        }
        return CapabilityWorkstyleBridgeArtifact.model_validate(
            {**draft, "fingerprint": _seal(draft)}
        )

    ordered = _sorted_work_items(source.work_items)
    if not ordered:
        raise ValueError("capability_workstyle_open_plan_requires_work_items")

    prior_by_domain: dict[str, str] = {}
    tasks: list[WorkTaskSpec] = []
    bindings: list[CapabilityWorkTaskBinding] = []
    for item in ordered:
        task_id = _task_id(item)
        prior = prior_by_domain.get(item.domain.value)
        dependencies = (prior,) if prior is not None else ()
        tasks.append(
            WorkTaskSpec(
                task_id=task_id,
                objective=item.objective,
                required_capabilities=_capabilities(item.kind),
                dependencies=dependencies,
                action_class=WorkActionClass.ARTIFACT_WRITE,
                input_artifact_ids=(
                    f"frontier3-certification:{source.source_certification_fingerprint}",
                    f"frontier-gap-plan:{source.fingerprint}",
                    f"frontier-gap-work-item:{item.work_item_id}",
                ),
                output_artifact_kinds=(
                    f"frontier-gap-evidence:{item.kind.value}",
                    "frontier3-recertification-input",
                ),
            )
        )
        bindings.append(
            CapabilityWorkTaskBinding(
                work_item_id=item.work_item_id,
                task_id=task_id,
                priority=item.priority,
                dependencies=dependencies,
            )
        )
        prior_by_domain[item.domain.value] = task_id

    work_plan = build_work_plan(
        tenant_id=source.tenant_id,
        company_id=source.company_id,
        session_id=session_id,
        revision=1,
        objective=(
            "Close measured Frontier-3 capability gaps and produce evidence for a newer "
            "independent certification without self-granting deployment or claim authority."
        ),
        tasks=tuple(tasks),
        created_at=created_at,
    )
    draft = {
        "contract": FRONTIER_CAPABILITY_WORKSTYLE_BRIDGE_CONTRACT,
        "tenant_id": source.tenant_id,
        "company_id": source.company_id,
        "session_id": session_id,
        "source_plan_fingerprint": source.fingerprint,
        "disposition": CapabilityWorkstyleDisposition.PLANNED.value,
        "task_bindings": [item.model_dump(mode="json") for item in bindings],
        "work_plan": work_plan.model_dump(mode="json"),
        "execution_authority_granted": False,
        "automatic_training_allowed": False,
        "automatic_code_change_allowed": False,
        "automatic_provider_change_allowed": False,
        "automatic_policy_update_allowed": False,
        "company_truth_promoted": False,
    }
    return CapabilityWorkstyleBridgeArtifact.model_validate(
        {**draft, "fingerprint": _seal(draft)}
    )
