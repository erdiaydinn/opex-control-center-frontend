"""Calibrated, privacy-safe gaze intent for Jarvis spatial interaction.

Gaze is a referent signal, never an action authorization. The module derives a
coarse normalized screen point from local face/iris landmarks, requires an
identity/session-bound calibration, checks bilateral eye agreement and emits a
focus intent only after a stable dwell over exactly one local UI candidate.

Raw face frames and landmark arrays are transient inputs only and are never
retained in gaze observations or focus receipts. A focus intent cannot click,
move, submit, approve or otherwise authorize a business side effect by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, model_validator

SPATIAL_GAZE_CONTRACT = "eay-spatial-gaze-v1"

# MediaPipe refined face-landmark topology. Iris centers are computed from the
# official ring points rather than assuming a synthetic center landmark.
_RIGHT_IRIS = (469, 470, 471, 472)
_LEFT_IRIS = (474, 475, 476, 477)
_RIGHT_EYE_HORIZONTAL = (33, 133)
_LEFT_EYE_HORIZONTAL = (263, 362)
_RIGHT_EYE_VERTICAL = (159, 145)
_LEFT_EYE_VERTICAL = (386, 374)
_MIN_REFINED_FACE_LANDMARKS = 478


class FaceLandmark2D(BaseModel):
    x: float = Field(ge=-0.5, le=1.5)
    y: float = Field(ge=-0.5, le=1.5)
    z: float = Field(default=0.0, ge=-2.0, le=2.0)


class FaceLandmarkFrame(BaseModel):
    observed_at: datetime
    tracking_confidence: float = Field(ge=0.0, le=1.0)
    landmarks: tuple[FaceLandmark2D, ...]
    raw_video_retained: bool = False

    @model_validator(mode="after")
    def refined_face_frame_is_safe(self) -> "FaceLandmarkFrame":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("spatial_gaze_frame_requires_timezone")
        if len(self.landmarks) < _MIN_REFINED_FACE_LANDMARKS:
            raise ValueError("spatial_gaze_refined_face_landmarks_required")
        if len(self.landmarks) > 512:
            raise ValueError("spatial_gaze_landmark_count_unexpected")
        if self.raw_video_retained:
            raise ValueError("spatial_gaze_cannot_retain_raw_video")
        return self


class GazeCalibration(BaseModel):
    calibration_ref: str = Field(min_length=1)
    spatial_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    calibrated_at: datetime
    expires_at: datetime
    center_horizontal_ratio: float = Field(ge=0.0, le=1.0)
    center_vertical_ratio: float = Field(ge=0.0, le=1.0)
    horizontal_gain: float = Field(default=3.0, gt=0.0, le=12.0)
    vertical_gain: float = Field(default=3.0, gt=0.0, le=12.0)
    minimum_tracking_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    maximum_bilateral_disagreement: float = Field(default=0.14, gt=0.0, le=0.5)
    raw_landmarks_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def calibration_is_short_lived_and_non_authorizing(self) -> "GazeCalibration":
        for value in (self.calibrated_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("spatial_gaze_calibration_requires_timezone")
        if self.expires_at <= self.calibrated_at:
            raise ValueError("spatial_gaze_calibration_expiry_invalid")
        if self.expires_at - self.calibrated_at > timedelta(hours=8):
            raise ValueError("spatial_gaze_calibration_too_long")
        if self.raw_landmarks_retained:
            raise ValueError("spatial_gaze_calibration_cannot_retain_landmarks")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_gaze_never_authorizes_business_side_effects")
        return self


class GazePointObservation(BaseModel):
    contract: str = SPATIAL_GAZE_CONTRACT
    spatial_session_id: str
    principal_ref: str
    identity_evidence_ref: str
    calibration_ref: str
    observed_at: datetime
    screen_x: float = Field(ge=0.0, le=1.0)
    screen_y: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    bilateral_disagreement: float = Field(ge=0.0)
    source_evidence_ref: str = Field(min_length=1)
    raw_landmarks_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def point_is_compact_observation(self) -> "GazePointObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("spatial_gaze_point_requires_timezone")
        if self.raw_landmarks_retained:
            raise ValueError("spatial_gaze_point_cannot_retain_landmarks")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_gaze_point_never_authorizes_business_side_effects")
        return self


class GazeTargetCandidate(BaseModel):
    target_ref: str = Field(min_length=1)
    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)
    local_ui_only: bool = True

    @model_validator(mode="after")
    def target_rect_has_area(self) -> "GazeTargetCandidate":
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("spatial_gaze_target_rect_invalid")
        if not self.local_ui_only:
            raise ValueError("spatial_gaze_target_must_be_local_ui_only")
        return self

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


class GazeFocusIntent(BaseModel):
    contract: str = SPATIAL_GAZE_CONTRACT
    spatial_session_id: str
    principal_ref: str
    identity_evidence_ref: str
    target_ref: str
    focused_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    source_evidence_ref: str = Field(min_length=1)
    dwell_ms: int = Field(ge=1)
    local_ui_referent_only: bool = True
    click_authorized: bool = False
    business_side_effects_authorized: bool = False
    raw_landmarks_retained: bool = False

    @model_validator(mode="after")
    def focus_never_becomes_action_authority(self) -> "GazeFocusIntent":
        if not self.local_ui_referent_only:
            raise ValueError("spatial_gaze_focus_must_remain_referent_only")
        if self.click_authorized or self.business_side_effects_authorized:
            raise ValueError("spatial_gaze_focus_never_authorizes_actions")
        if self.raw_landmarks_retained:
            raise ValueError("spatial_gaze_focus_cannot_retain_landmarks")
        return self


def _centroid(frame: FaceLandmarkFrame, indices: tuple[int, ...]) -> tuple[float, float]:
    points = [frame.landmarks[index] for index in indices]
    return (
        sum(item.x for item in points) / len(points),
        sum(item.y for item in points) / len(points),
    )


def _axis_ratio(value: float, boundary_a: float, boundary_b: float) -> float | None:
    low = min(boundary_a, boundary_b)
    high = max(boundary_a, boundary_b)
    span = high - low
    if span < 1e-4:
        return None
    return (value - low) / span


def derive_gaze_point(
    *,
    frame: FaceLandmarkFrame,
    calibration: GazeCalibration,
) -> GazePointObservation | None:
    """Derive a calibrated gaze proxy, failing closed on noisy eye geometry."""

    now = frame.observed_at
    if now < calibration.calibrated_at or now > calibration.expires_at:
        return None
    if frame.tracking_confidence < calibration.minimum_tracking_confidence:
        return None

    right_iris_x, right_iris_y = _centroid(frame, _RIGHT_IRIS)
    left_iris_x, left_iris_y = _centroid(frame, _LEFT_IRIS)

    right_h = _axis_ratio(
        right_iris_x,
        frame.landmarks[_RIGHT_EYE_HORIZONTAL[0]].x,
        frame.landmarks[_RIGHT_EYE_HORIZONTAL[1]].x,
    )
    left_h = _axis_ratio(
        left_iris_x,
        frame.landmarks[_LEFT_EYE_HORIZONTAL[0]].x,
        frame.landmarks[_LEFT_EYE_HORIZONTAL[1]].x,
    )
    right_v = _axis_ratio(
        right_iris_y,
        frame.landmarks[_RIGHT_EYE_VERTICAL[0]].y,
        frame.landmarks[_RIGHT_EYE_VERTICAL[1]].y,
    )
    left_v = _axis_ratio(
        left_iris_y,
        frame.landmarks[_LEFT_EYE_VERTICAL[0]].y,
        frame.landmarks[_LEFT_EYE_VERTICAL[1]].y,
    )
    if None in {right_h, left_h, right_v, left_v}:
        return None
    assert right_h is not None and left_h is not None and right_v is not None and left_v is not None

    # Ratios substantially outside the eye aperture usually indicate poor face
    # geometry, blink/occlusion or a topology mismatch. Do not clamp bad input
    # into a plausible screen point.
    ratios = (right_h, left_h, right_v, left_v)
    if any(value < -0.10 or value > 1.10 for value in ratios):
        return None

    disagreement = max(abs(right_h - left_h), abs(right_v - left_v))
    if disagreement > calibration.maximum_bilateral_disagreement:
        return None

    horizontal = (right_h + left_h) / 2.0
    vertical = (right_v + left_v) / 2.0
    screen_x_raw = 0.5 + (horizontal - calibration.center_horizontal_ratio) * calibration.horizontal_gain
    screen_y_raw = 0.5 + (vertical - calibration.center_vertical_ratio) * calibration.vertical_gain
    if screen_x_raw < -0.05 or screen_x_raw > 1.05 or screen_y_raw < -0.05 or screen_y_raw > 1.05:
        return None

    confidence = frame.tracking_confidence * max(
        0.0,
        1.0 - disagreement / calibration.maximum_bilateral_disagreement,
    )
    return GazePointObservation(
        spatial_session_id=calibration.spatial_session_id,
        principal_ref=calibration.principal_ref,
        identity_evidence_ref=calibration.identity_evidence_ref,
        calibration_ref=calibration.calibration_ref,
        observed_at=now,
        screen_x=min(1.0, max(0.0, screen_x_raw)),
        screen_y=min(1.0, max(0.0, screen_y_raw)),
        confidence=min(1.0, max(0.0, confidence)),
        bilateral_disagreement=disagreement,
        source_evidence_ref=(
            f"evidence://spatial-gaze/{calibration.spatial_session_id}/"
            f"{int(now.timestamp() * 1000)}"
        ),
    )


@dataclass
class _FocusState:
    target_ref: str | None = None
    dwell_started_at: datetime | None = None
    anchor_x: float | None = None
    anchor_y: float | None = None
    cooldown_until: datetime | None = None


class GazeTargetTracker:
    """Emit focus only after stable dwell over exactly one candidate."""

    def __init__(
        self,
        *,
        calibration: GazeCalibration,
        minimum_confidence: float = 0.75,
        dwell_ms: int = 320,
        maximum_jitter: float = 0.08,
        cooldown_ms: int = 500,
    ) -> None:
        self.calibration = calibration
        self.minimum_confidence = minimum_confidence
        self.dwell = timedelta(milliseconds=dwell_ms)
        self.maximum_jitter = maximum_jitter
        self.cooldown = timedelta(milliseconds=cooldown_ms)
        self._state = _FocusState()

    def _reset(self) -> None:
        self._state.target_ref = None
        self._state.dwell_started_at = None
        self._state.anchor_x = None
        self._state.anchor_y = None

    def consume(
        self,
        *,
        point: GazePointObservation,
        candidates: tuple[GazeTargetCandidate, ...],
    ) -> GazeFocusIntent | None:
        if point.spatial_session_id != self.calibration.spatial_session_id:
            raise ValueError("spatial_gaze_point_session_mismatch")
        if point.principal_ref != self.calibration.principal_ref:
            raise ValueError("spatial_gaze_point_principal_mismatch")
        if point.identity_evidence_ref != self.calibration.identity_evidence_ref:
            raise ValueError("spatial_gaze_point_identity_mismatch")
        if point.observed_at < self.calibration.calibrated_at or point.observed_at > self.calibration.expires_at:
            self._reset()
            return None
        if self._state.cooldown_until is not None and point.observed_at < self._state.cooldown_until:
            return None
        if point.confidence < self.minimum_confidence:
            self._reset()
            return None

        matches = [item for item in candidates if item.contains(point.screen_x, point.screen_y)]
        if len(matches) != 1:
            self._reset()
            return None
        target = matches[0]

        if self._state.target_ref != target.target_ref:
            self._state.target_ref = target.target_ref
            self._state.dwell_started_at = point.observed_at
            self._state.anchor_x = point.screen_x
            self._state.anchor_y = point.screen_y
            return None

        anchor_x = self._state.anchor_x if self._state.anchor_x is not None else point.screen_x
        anchor_y = self._state.anchor_y if self._state.anchor_y is not None else point.screen_y
        if abs(point.screen_x - anchor_x) > self.maximum_jitter or abs(point.screen_y - anchor_y) > self.maximum_jitter:
            self._state.dwell_started_at = point.observed_at
            self._state.anchor_x = point.screen_x
            self._state.anchor_y = point.screen_y
            return None

        started = self._state.dwell_started_at or point.observed_at
        elapsed = point.observed_at - started
        if elapsed < self.dwell:
            return None

        intent = GazeFocusIntent(
            spatial_session_id=point.spatial_session_id,
            principal_ref=point.principal_ref,
            identity_evidence_ref=point.identity_evidence_ref,
            target_ref=target.target_ref,
            focused_at=point.observed_at,
            confidence=point.confidence,
            source_evidence_ref=point.source_evidence_ref,
            dwell_ms=max(1, int(elapsed.total_seconds() * 1000)),
        )
        self._reset()
        self._state.cooldown_until = point.observed_at + self.cooldown
        return intent
