"""Privacy-safe spatial HUD state for Jarvis.

The HUD is feedback, not authority. It tells the user what Jarvis believes the
current spatial interaction state is (focus, armed, ready, moving, cancelled or
blocked) without retaining raw camera frames, voice transcripts, face/hand
landmarks or application content. The HUD can never authorize an OS/business
side effect by itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

SPATIAL_HUD_CONTRACT = "eay-spatial-hud-v1"


class HudPhase(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    FOCUSED = "focused"
    ARMED = "armed"
    GRABBED = "grabbed"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class HudEventKind(str, Enum):
    LISTEN = "listen"
    GAZE_FOCUS = "gaze_focus"
    ARM = "arm"
    GRAB = "grab"
    FUSION_READY = "fusion_ready"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    CANCEL = "cancel"
    BLOCK = "block"
    RESET = "reset"


class SpatialHudSession(BaseModel):
    contract: str = SPATIAL_HUD_CONTRACT
    spatial_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    started_at: datetime
    expires_at: datetime
    raw_sensor_retention_allowed: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def session_is_safe(self) -> "SpatialHudSession":
        for value in (self.started_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("spatial_hud_session_requires_timezone")
        if self.expires_at <= self.started_at:
            raise ValueError("spatial_hud_session_expiry_invalid")
        if self.expires_at - self.started_at > timedelta(minutes=30):
            raise ValueError("spatial_hud_session_too_long")
        if self.raw_sensor_retention_allowed:
            raise ValueError("spatial_hud_cannot_retain_raw_sensor_data")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_hud_never_authorizes_business_side_effects")
        return self


class SpatialHudEvent(BaseModel):
    event_id: str = Field(min_length=1)
    spatial_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    occurred_at: datetime
    kind: HudEventKind
    target_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    blocker_code: str | None = None
    source_evidence_refs: tuple[str, ...] = Field(min_length=1)
    raw_sensor_data_retained: bool = False

    @model_validator(mode="after")
    def event_is_compact(self) -> "SpatialHudEvent":
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("spatial_hud_event_requires_timezone")
        if self.kind is HudEventKind.GAZE_FOCUS and not self.target_ref:
            raise ValueError("spatial_hud_focus_requires_target")
        if self.kind is HudEventKind.BLOCK and not self.blocker_code:
            raise ValueError("spatial_hud_block_requires_code")
        if self.raw_sensor_data_retained:
            raise ValueError("spatial_hud_event_cannot_retain_raw_sensor_data")
        return self


class SpatialHudSnapshot(BaseModel):
    contract: str = SPATIAL_HUD_CONTRACT
    spatial_session_id: str
    principal_ref: str
    phase: HudPhase = HudPhase.IDLE
    target_ref: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    cue: str = "hud.idle"
    blockers: tuple[str, ...] = ()
    processed_event_ids: tuple[str, ...] = ()
    raw_sensor_data_retained: bool = False
    application_content_retained: bool = False
    action_execution_authorized: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def snapshot_is_feedback_only(self) -> "SpatialHudSnapshot":
        if self.raw_sensor_data_retained or self.application_content_retained:
            raise ValueError("spatial_hud_snapshot_cannot_retain_content")
        if self.action_execution_authorized or self.business_side_effects_authorized:
            raise ValueError("spatial_hud_snapshot_never_authorizes_actions")
        return self


def new_hud_snapshot(session: SpatialHudSession) -> SpatialHudSnapshot:
    return SpatialHudSnapshot(
        spatial_session_id=session.spatial_session_id,
        principal_ref=session.principal_ref,
    )


_PHASES = {
    HudEventKind.LISTEN: (HudPhase.LISTENING, "hud.listening"),
    HudEventKind.GAZE_FOCUS: (HudPhase.FOCUSED, "hud.focused"),
    HudEventKind.ARM: (HudPhase.ARMED, "hud.armed"),
    HudEventKind.GRAB: (HudPhase.GRABBED, "hud.grabbed"),
    HudEventKind.FUSION_READY: (HudPhase.READY, "hud.ready"),
    HudEventKind.EXECUTION_STARTED: (HudPhase.EXECUTING, "hud.executing"),
    HudEventKind.EXECUTION_COMPLETED: (HudPhase.COMPLETED, "hud.completed"),
    HudEventKind.CANCEL: (HudPhase.CANCELLED, "hud.cancelled"),
    HudEventKind.BLOCK: (HudPhase.BLOCKED, "hud.blocked"),
    HudEventKind.RESET: (HudPhase.IDLE, "hud.idle"),
}


def apply_hud_event(
    *,
    session: SpatialHudSession,
    snapshot: SpatialHudSnapshot,
    event: SpatialHudEvent,
) -> SpatialHudSnapshot:
    if snapshot.spatial_session_id != session.spatial_session_id:
        raise ValueError("spatial_hud_snapshot_session_mismatch")
    if event.spatial_session_id != session.spatial_session_id:
        raise ValueError("spatial_hud_event_session_mismatch")
    if event.principal_ref != session.principal_ref or event.principal_ref != snapshot.principal_ref:
        raise ValueError("spatial_hud_principal_mismatch")
    if event.identity_evidence_ref != session.identity_evidence_ref:
        raise ValueError("spatial_hud_identity_mismatch")
    if event.occurred_at < session.started_at or event.occurred_at > session.expires_at:
        raise ValueError("spatial_hud_event_outside_session")
    if event.event_id in snapshot.processed_event_ids:
        raise ValueError("spatial_hud_duplicate_event")

    phase, cue = _PHASES[event.kind]
    target = event.target_ref if event.target_ref is not None else snapshot.target_ref
    confidence = event.confidence if event.confidence is not None else snapshot.confidence
    blockers: tuple[str, ...] = ()

    if event.kind is HudEventKind.BLOCK:
        blockers = (event.blocker_code or "spatial_hud_blocked",)
    elif event.kind in {HudEventKind.CANCEL, HudEventKind.RESET}:
        target = None
        confidence = None

    return snapshot.model_copy(
        update={
            "phase": phase,
            "target_ref": target,
            "confidence": confidence,
            "cue": cue,
            "blockers": blockers,
            "processed_event_ids": (*snapshot.processed_event_ids, event.event_id),
        }
    )
