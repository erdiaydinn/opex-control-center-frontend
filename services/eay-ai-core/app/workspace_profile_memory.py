"""Explicit, approval-bound workspace profile memory for Jarvis.

Jarvis may remember a user's chosen workspace layout only after an explicit
approval artifact. Observation alone never creates durable preference memory.
Profiles are principal/device-topology bound, versioned, expiring and contain
only role/slot layout metadata—never application content or window titles.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from .desktop_window_runtime import MonitorGeometry
from .workspace_choreography import WorkspaceProfile, WorkspaceSlot

WORKSPACE_PROFILE_MEMORY_CONTRACT = "eay-workspace-profile-memory-v1"


class WorkspaceApproval(BaseModel):
    approval_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime
    purpose: str = Field(pattern=r"^remember_workspace_layout$")
    automatic_observation_persistence_allowed: bool = False

    @model_validator(mode="after")
    def approval_is_explicit_and_bounded(self) -> "WorkspaceApproval":
        for value in (self.approved_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("workspace_memory_approval_requires_timezone")
        if self.expires_at <= self.approved_at:
            raise ValueError("workspace_memory_approval_expiry_invalid")
        if self.expires_at - self.approved_at > timedelta(days=365):
            raise ValueError("workspace_memory_approval_too_long")
        if self.automatic_observation_persistence_allowed:
            raise ValueError("workspace_memory_cannot_learn_from_observation_without_approval")
        return self


class StoredWorkspaceProfile(BaseModel):
    contract: str = WORKSPACE_PROFILE_MEMORY_CONTRACT
    memory_ref: str = Field(min_length=1)
    profile_ref: str = Field(min_length=1)
    profile_version: int = Field(ge=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    approval_ref: str = Field(min_length=1)
    topology_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    slots: tuple[WorkspaceSlot, ...] = Field(min_length=1)
    stored_at: datetime
    expires_at: datetime
    application_content_retained: bool = False
    window_titles_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def memory_is_metadata_only(self) -> "StoredWorkspaceProfile":
        if self.application_content_retained or self.window_titles_retained:
            raise ValueError("workspace_memory_cannot_retain_application_content")
        if self.business_side_effects_authorized:
            raise ValueError("workspace_memory_never_authorizes_business_side_effects")
        if self.expires_at <= self.stored_at:
            raise ValueError("workspace_memory_expiry_invalid")
        return self


class WorkspaceMemoryResolution(BaseModel):
    contract: str = WORKSPACE_PROFILE_MEMORY_CONTRACT
    profile: WorkspaceProfile | None = None
    blockers: tuple[str, ...] = ()
    automatic_execution_authorized: bool = False

    @model_validator(mode="after")
    def resolution_never_auto_executes(self) -> "WorkspaceMemoryResolution":
        if self.automatic_execution_authorized:
            raise ValueError("workspace_memory_never_auto_executes_layout")
        if self.profile is not None and self.blockers:
            raise ValueError("workspace_memory_resolution_invalid")
        return self


def monitor_topology_fingerprint(monitors: tuple[MonitorGeometry, ...]) -> str:
    rows = sorted(
        (
            item.monitor_id,
            item.bounds.left,
            item.bounds.top,
            item.bounds.right,
            item.bounds.bottom,
            item.work_area.left,
            item.work_area.top,
            item.work_area.right,
            item.work_area.bottom,
            item.primary,
        )
        for item in monitors
    )
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def store_workspace_profile(
    *,
    profile: WorkspaceProfile,
    approval: WorkspaceApproval,
    monitors: tuple[MonitorGeometry, ...],
    stored_at: datetime,
    profile_version: int,
) -> StoredWorkspaceProfile:
    if stored_at.tzinfo is None or stored_at.utcoffset() is None:
        raise ValueError("workspace_memory_store_requires_timezone")
    if profile.principal_ref != approval.principal_ref:
        raise ValueError("workspace_memory_principal_mismatch")
    if profile.identity_evidence_ref != approval.identity_evidence_ref:
        raise ValueError("workspace_memory_identity_mismatch")
    if not (approval.approved_at <= stored_at <= approval.expires_at):
        raise ValueError("workspace_memory_store_outside_approval_window")
    monitor_ids = {item.monitor_id for item in monitors}
    if any(slot.monitor_id not in monitor_ids for slot in profile.slots):
        raise ValueError("workspace_memory_profile_monitor_not_observed")
    fingerprint = monitor_topology_fingerprint(monitors)
    digest = hashlib.sha256(
        f"{profile.principal_ref}|{profile.profile_ref}|{profile_version}|{fingerprint}".encode("utf-8")
    ).hexdigest()[:24]
    return StoredWorkspaceProfile(
        memory_ref=f"workspace-memory:{digest}",
        profile_ref=profile.profile_ref,
        profile_version=profile_version,
        principal_ref=profile.principal_ref,
        identity_evidence_ref=profile.identity_evidence_ref,
        approval_ref=approval.approval_ref,
        topology_fingerprint=fingerprint,
        slots=profile.slots,
        stored_at=stored_at,
        expires_at=approval.expires_at,
    )


def resolve_workspace_memory(
    *,
    memory: StoredWorkspaceProfile,
    principal_ref: str,
    identity_evidence_ref: str,
    monitors: tuple[MonitorGeometry, ...],
    now: datetime,
) -> WorkspaceMemoryResolution:
    blockers: list[str] = []
    if principal_ref != memory.principal_ref:
        blockers.append("workspace_memory_principal_mismatch")
    if identity_evidence_ref != memory.identity_evidence_ref:
        blockers.append("workspace_memory_identity_mismatch")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("workspace_memory_resolution_requires_timezone")
    if now > memory.expires_at:
        blockers.append("workspace_memory_expired")
    if monitor_topology_fingerprint(monitors) != memory.topology_fingerprint:
        blockers.append("workspace_memory_topology_changed")
    if blockers:
        return WorkspaceMemoryResolution(blockers=tuple(blockers))
    return WorkspaceMemoryResolution(
        profile=WorkspaceProfile(
            profile_ref=memory.profile_ref,
            principal_ref=memory.principal_ref,
            identity_evidence_ref=memory.identity_evidence_ref,
            slots=memory.slots,
        )
    )
