"""Deterministic multi-monitor workspace choreography for Jarvis.

A workspace profile arranges already-authorized local windows into explicit
monitor slots. It does not inspect titles/content, launch applications, log in,
or authorize business operations. Every movement is reversible local UI state
and is planned from opaque window refs plus current monitor geometry.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .desktop_window_runtime import DesktopRect, MonitorGeometry, WindowGeometry

WORKSPACE_CHOREOGRAPHY_CONTRACT = "eay-workspace-choreography-v1"


class WorkspaceRole(str, Enum):
    PRIMARY = "primary"
    PLANOGRAM_2D = "planogram_2d"
    PLANOGRAM_3D = "planogram_3d"
    RULES = "rules"
    KPI = "kpi"
    JARVIS = "jarvis"
    RESEARCH = "research"
    COMMUNICATION = "communication"


class WorkspaceWindowBinding(BaseModel):
    role: WorkspaceRole
    window_ref: str = Field(min_length=1)


class WorkspaceSlot(BaseModel):
    role: WorkspaceRole
    monitor_id: str = Field(min_length=1)
    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(gt=0.0, le=1.0)
    bottom: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def slot_has_area(self) -> "WorkspaceSlot":
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("workspace_choreography_slot_invalid")
        return self


class WorkspaceProfile(BaseModel):
    contract: str = WORKSPACE_CHOREOGRAPHY_CONTRACT
    profile_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    slots: tuple[WorkspaceSlot, ...] = Field(min_length=1)
    launch_applications_allowed: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def profile_is_local_layout_only(self) -> "WorkspaceProfile":
        roles = [item.role for item in self.slots]
        if len(roles) != len(set(roles)):
            raise ValueError("workspace_choreography_duplicate_role_slot")
        if self.launch_applications_allowed:
            raise ValueError("workspace_choreography_does_not_launch_apps")
        if self.business_side_effects_authorized:
            raise ValueError("workspace_choreography_never_authorizes_business_side_effects")
        return self


class WorkspaceMove(BaseModel):
    role: WorkspaceRole
    window_ref: str
    monitor_id: str
    before_rect: DesktopRect
    after_rect: DesktopRect
    restore_maximized: bool = False


class WorkspacePlan(BaseModel):
    contract: str = WORKSPACE_CHOREOGRAPHY_CONTRACT
    profile_ref: str
    principal_ref: str
    moves: tuple[WorkspaceMove, ...]
    blockers: tuple[str, ...] = ()
    exact_window_binding_required: bool = True
    application_content_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def plan_is_safe(self) -> "WorkspacePlan":
        if self.application_content_retained:
            raise ValueError("workspace_choreography_cannot_retain_content")
        if self.business_side_effects_authorized:
            raise ValueError("workspace_choreography_never_authorizes_business_side_effects")
        if self.moves and self.blockers:
            raise ValueError("workspace_choreography_cannot_move_with_blockers")
        return self


class WorkspaceExecutionReceipt(BaseModel):
    contract: str = WORKSPACE_CHOREOGRAPHY_CONTRACT
    profile_ref: str
    moved_window_refs: tuple[str, ...]
    completed: bool
    local_ui_side_effect_only: bool = True
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def receipt_is_local(self) -> "WorkspaceExecutionReceipt":
        if not self.local_ui_side_effect_only or self.business_side_effects_authorized:
            raise ValueError("workspace_choreography_receipt_boundary_violation")
        return self


class WorkspaceBackend(Protocol):
    def move_window(self, window_ref: str, rect: DesktopRect, *, restore_maximized: bool) -> None: ...


def _slot_rect(slot: WorkspaceSlot, monitor: MonitorGeometry) -> DesktopRect:
    area = monitor.work_area
    left = area.left + round(area.width * slot.left)
    top = area.top + round(area.height * slot.top)
    right = area.left + round(area.width * slot.right)
    bottom = area.top + round(area.height * slot.bottom)
    return DesktopRect(left=left, top=top, right=right, bottom=bottom)


def plan_workspace(
    *,
    profile: WorkspaceProfile,
    bindings: tuple[WorkspaceWindowBinding, ...],
    windows: tuple[WindowGeometry, ...],
    monitors: tuple[MonitorGeometry, ...],
) -> WorkspacePlan:
    binding_roles = [item.role for item in bindings]
    binding_refs = [item.window_ref for item in bindings]
    blockers: list[str] = []
    if len(binding_roles) != len(set(binding_roles)):
        blockers.append("workspace_choreography_duplicate_role_binding")
    if len(binding_refs) != len(set(binding_refs)):
        blockers.append("workspace_choreography_duplicate_window_binding")

    by_window = {item.window_ref: item for item in windows}
    by_monitor = {item.monitor_id: item for item in monitors}
    slots = {item.role: item for item in profile.slots}
    moves: list[WorkspaceMove] = []

    for binding in bindings:
        slot = slots.get(binding.role)
        if slot is None:
            blockers.append(f"workspace_choreography_slot_missing:{binding.role.value}")
            continue
        window = by_window.get(binding.window_ref)
        if window is None:
            blockers.append(f"workspace_choreography_window_missing:{binding.role.value}")
            continue
        monitor = by_monitor.get(slot.monitor_id)
        if monitor is None:
            blockers.append(f"workspace_choreography_monitor_missing:{binding.role.value}")
            continue
        moves.append(
            WorkspaceMove(
                role=binding.role,
                window_ref=window.window_ref,
                monitor_id=monitor.monitor_id,
                before_rect=window.rect,
                after_rect=_slot_rect(slot, monitor),
                restore_maximized=window.maximized,
            )
        )

    if blockers:
        return WorkspacePlan(
            profile_ref=profile.profile_ref,
            principal_ref=profile.principal_ref,
            moves=(),
            blockers=tuple(dict.fromkeys(blockers)),
        )
    return WorkspacePlan(
        profile_ref=profile.profile_ref,
        principal_ref=profile.principal_ref,
        moves=tuple(moves),
    )


def execute_workspace(*, plan: WorkspacePlan, backend: WorkspaceBackend) -> WorkspaceExecutionReceipt:
    if plan.blockers:
        raise ValueError("workspace_choreography_plan_blocked")
    moved: list[str] = []
    for item in plan.moves:
        backend.move_window(item.window_ref, item.after_rect, restore_maximized=item.restore_maximized)
        moved.append(item.window_ref)
    return WorkspaceExecutionReceipt(
        profile_ref=plan.profile_ref,
        moved_window_refs=tuple(moved),
        completed=True,
    )
