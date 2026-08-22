"""Governed hand-gesture interaction for Jarvis spatial computer control.

The goal is Iron-Man-like input without turning every camera movement into an
OS command. Raw video is outside this contract. A vision adapter may provide
21 normalized hand landmarks, but persisted output is limited to a compact,
identity-bound gesture intent.

Safety / UX rules:
- spatial control must be explicitly armed for a short-lived session;
- an open-palm dwell arms the hand, then a thumb/index pinch grabs;
- horizontal drag while pinched emits one left/right window-transfer intent;
- vertical/noisy motion, weak tracking and stale sessions do nothing;
- a closed-fist observation emits an explicit CANCEL intent and resets state;
- no business/application mutation authority is granted by a gesture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator

SPATIAL_INTERACTION_CONTRACT = "eay-spatial-interaction-v1"


class Handedness(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UNKNOWN = "unknown"


class SpatialGestureCommand(str, Enum):
    MOVE_ACTIVE_WINDOW_LEFT = "move_active_window_left"
    MOVE_ACTIVE_WINDOW_RIGHT = "move_active_window_right"
    CANCEL = "cancel"


class Landmark3D(BaseModel):
    x: float = Field(ge=-0.5, le=1.5)
    y: float = Field(ge=-0.5, le=1.5)
    z: float = Field(ge=-2.0, le=2.0)


class HandLandmarkFrame(BaseModel):
    observed_at: datetime
    handedness: Handedness = Handedness.UNKNOWN
    tracking_confidence: float = Field(ge=0.0, le=1.0)
    landmarks: tuple[Landmark3D, ...]
    raw_video_retained: bool = False

    @model_validator(mode="after")
    def frame_is_safe_and_complete(self) -> "HandLandmarkFrame":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("spatial_hand_frame_requires_timezone")
        if len(self.landmarks) != 21:
            raise ValueError("spatial_hand_frame_requires_21_landmarks")
        if self.raw_video_retained:
            raise ValueError("spatial_interaction_contract_cannot_retain_raw_video")
        return self


class SpatialControlSession(BaseModel):
    contract: str = SPATIAL_INTERACTION_CONTRACT
    session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    arm_evidence_ref: str = Field(min_length=1)
    armed_at: datetime
    expires_at: datetime
    camera_authorized: bool = False
    allowed_commands: frozenset[SpatialGestureCommand] = frozenset(
        {
            SpatialGestureCommand.MOVE_ACTIVE_WINDOW_LEFT,
            SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT,
            SpatialGestureCommand.CANCEL,
        }
    )
    raw_video_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def spatial_session_is_short_lived_and_local_only(self) -> "SpatialControlSession":
        for value in (self.armed_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("spatial_control_session_requires_timezone")
        if self.expires_at <= self.armed_at:
            raise ValueError("spatial_control_session_expiry_invalid")
        if self.expires_at - self.armed_at > timedelta(minutes=30):
            raise ValueError("spatial_control_session_too_long")
        if not self.camera_authorized:
            raise ValueError("spatial_control_requires_camera_authorization")
        if self.raw_video_retained:
            raise ValueError("spatial_control_cannot_retain_raw_video")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_gesture_never_authorizes_business_side_effects")
        return self


class SpatialGestureIntent(BaseModel):
    contract: str = SPATIAL_INTERACTION_CONTRACT
    session_id: str
    principal_ref: str
    command: SpatialGestureCommand
    emitted_at: datetime
    handedness: Handedness
    confidence: float = Field(ge=0.0, le=1.0)
    horizontal_displacement: float
    source_evidence_ref: str = Field(min_length=1)
    raw_landmarks_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def intent_is_compact_local_ui_control(self) -> "SpatialGestureIntent":
        if self.emitted_at.tzinfo is None or self.emitted_at.utcoffset() is None:
            raise ValueError("spatial_gesture_intent_requires_timezone")
        if self.command is SpatialGestureCommand.CANCEL and abs(self.horizontal_displacement) > 1e-12:
            raise ValueError("spatial_cancel_cannot_claim_displacement")
        if self.raw_landmarks_retained:
            raise ValueError("spatial_gesture_intent_cannot_retain_landmarks")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_gesture_intent_never_authorizes_business_side_effects")
        return self


def _distance(a: Landmark3D, b: Landmark3D) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _palm_scale(frame: HandLandmarkFrame) -> float:
    # wrist (0) to middle-finger MCP (9) is stable enough to normalize distance.
    return max(_distance(frame.landmarks[0], frame.landmarks[9]), 1e-4)


def _pinch_ratio(frame: HandLandmarkFrame) -> float:
    return _distance(frame.landmarks[4], frame.landmarks[8]) / _palm_scale(frame)


def _finger_extended(frame: HandLandmarkFrame, tip: int, pip: int, mcp: int) -> bool:
    # MediaPipe image coordinates grow downward. An extended finger normally
    # places tip above PIP and PIP above MCP. A small tolerance avoids jitter.
    return frame.landmarks[tip].y + 0.015 < frame.landmarks[pip].y < frame.landmarks[mcp].y + 0.04


def _open_palm_score(frame: HandLandmarkFrame) -> float:
    extended = sum(
        (
            _finger_extended(frame, 8, 6, 5),
            _finger_extended(frame, 12, 10, 9),
            _finger_extended(frame, 16, 14, 13),
            _finger_extended(frame, 20, 18, 17),
        )
    )
    return extended / 4.0


def _closed_fist(frame: HandLandmarkFrame) -> bool:
    folded = 0
    for tip, pip, mcp in ((8, 6, 5), (12, 10, 9), (16, 14, 13), (20, 18, 17)):
        if frame.landmarks[tip].y > frame.landmarks[pip].y - 0.01 and frame.landmarks[pip].y > frame.landmarks[mcp].y - 0.03:
            folded += 1
    return folded >= 3


def _control_point(frame: HandLandmarkFrame) -> tuple[float, float]:
    # midpoint of thumb/index tips feels like "grabbing" an object in space.
    thumb = frame.landmarks[4]
    index = frame.landmarks[8]
    return ((thumb.x + index.x) / 2.0, (thumb.y + index.y) / 2.0)


@dataclass
class _TrackerState:
    open_palm_since: datetime | None = None
    palm_armed_until: datetime | None = None
    pinch_started_at: datetime | None = None
    pinch_start_x: float | None = None
    pinch_start_y: float | None = None
    cooldown_until: datetime | None = None


class SpatialGestureRecognizer:
    """Stateful open-palm -> pinch-grab -> horizontal-drag recognizer."""

    def __init__(
        self,
        *,
        session: SpatialControlSession,
        minimum_tracking_confidence: float = 0.70,
        open_palm_dwell_ms: int = 220,
        palm_arm_window_ms: int = 1500,
        pinch_threshold: float = 0.42,
        release_threshold: float = 0.58,
        horizontal_trigger: float = 0.16,
        maximum_vertical_drift: float = 0.13,
        maximum_drag_ms: int = 1800,
        cooldown_ms: int = 900,
    ) -> None:
        self.session = session
        self.minimum_tracking_confidence = minimum_tracking_confidence
        self.open_palm_dwell = timedelta(milliseconds=open_palm_dwell_ms)
        self.palm_arm_window = timedelta(milliseconds=palm_arm_window_ms)
        self.pinch_threshold = pinch_threshold
        self.release_threshold = release_threshold
        self.horizontal_trigger = horizontal_trigger
        self.maximum_vertical_drift = maximum_vertical_drift
        self.maximum_drag = timedelta(milliseconds=maximum_drag_ms)
        self.cooldown = timedelta(milliseconds=cooldown_ms)
        self._state = _TrackerState()

    def _reset_hand_state(self) -> None:
        self._state.open_palm_since = None
        self._state.palm_armed_until = None
        self._state.pinch_started_at = None
        self._state.pinch_start_x = None
        self._state.pinch_start_y = None

    def _evidence_ref(self, now: datetime, suffix: str = "") -> str:
        tail = f"/{suffix}" if suffix else ""
        return f"evidence://spatial-gesture/{self.session.session_id}/{int(now.timestamp() * 1000)}{tail}"

    def consume(self, frame: HandLandmarkFrame) -> SpatialGestureIntent | None:
        now = frame.observed_at
        if now < self.session.armed_at or now > self.session.expires_at:
            self._reset_hand_state()
            return None
        if frame.tracking_confidence < self.minimum_tracking_confidence:
            self._reset_hand_state()
            return None
        if self._state.cooldown_until is not None and now < self._state.cooldown_until:
            return None
        if _closed_fist(frame):
            self._reset_hand_state()
            if SpatialGestureCommand.CANCEL not in self.session.allowed_commands:
                return None
            self._state.cooldown_until = now + self.cooldown
            return SpatialGestureIntent(
                session_id=self.session.session_id,
                principal_ref=self.session.principal_ref,
                command=SpatialGestureCommand.CANCEL,
                emitted_at=now,
                handedness=frame.handedness,
                confidence=frame.tracking_confidence,
                horizontal_displacement=0.0,
                source_evidence_ref=self._evidence_ref(now, "cancel"),
            )

        palm_score = _open_palm_score(frame)
        if self._state.pinch_started_at is None:
            if palm_score >= 0.75:
                if self._state.open_palm_since is None:
                    self._state.open_palm_since = now
                elif now - self._state.open_palm_since >= self.open_palm_dwell:
                    self._state.palm_armed_until = now + self.palm_arm_window
            elif self._state.palm_armed_until is None:
                self._state.open_palm_since = None

            palm_armed = self._state.palm_armed_until is not None and now <= self._state.palm_armed_until
            if palm_armed and _pinch_ratio(frame) <= self.pinch_threshold:
                x, y = _control_point(frame)
                self._state.pinch_started_at = now
                self._state.pinch_start_x = x
                self._state.pinch_start_y = y
                return None
            return None

        # A drag is active.
        if now - self._state.pinch_started_at > self.maximum_drag:
            self._reset_hand_state()
            return None
        if _pinch_ratio(frame) >= self.release_threshold:
            self._reset_hand_state()
            return None

        x, y = _control_point(frame)
        start_x = self._state.pinch_start_x if self._state.pinch_start_x is not None else x
        start_y = self._state.pinch_start_y if self._state.pinch_start_y is not None else y
        dx = x - start_x
        dy = y - start_y
        if abs(dy) > self.maximum_vertical_drift:
            self._reset_hand_state()
            return None
        if abs(dx) < self.horizontal_trigger:
            return None

        command = (
            SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT
            if dx > 0
            else SpatialGestureCommand.MOVE_ACTIVE_WINDOW_LEFT
        )
        if command not in self.session.allowed_commands:
            self._reset_hand_state()
            return None

        confidence = min(1.0, frame.tracking_confidence * min(1.0, abs(dx) / self.horizontal_trigger))
        intent = SpatialGestureIntent(
            session_id=self.session.session_id,
            principal_ref=self.session.principal_ref,
            command=command,
            emitted_at=now,
            handedness=frame.handedness,
            confidence=confidence,
            horizontal_displacement=dx,
            source_evidence_ref=self._evidence_ref(now),
        )
        self._reset_hand_state()
        self._state.cooldown_until = now + self.cooldown
        return intent


def new_spatial_control_session(
    *,
    session_id: str,
    principal_ref: str,
    identity_evidence_ref: str,
    arm_evidence_ref: str,
    now: datetime | None = None,
    duration_minutes: int = 10,
) -> SpatialControlSession:
    if duration_minutes < 1 or duration_minutes > 30:
        raise ValueError("spatial_control_duration_out_of_bounds")
    armed_at = now or datetime.now(timezone.utc)
    return SpatialControlSession(
        session_id=session_id,
        principal_ref=principal_ref,
        identity_evidence_ref=identity_evidence_ref,
        arm_evidence_ref=arm_evidence_ref,
        armed_at=armed_at,
        expires_at=armed_at + timedelta(minutes=duration_minutes),
        camera_authorized=True,
    )
