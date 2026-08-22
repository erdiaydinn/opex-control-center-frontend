"""Privacy-safe local camera and MediaPipe hand-landmark runtime for Jarvis.

The existing spatial recognizer consumes ``HandLandmarkFrame`` objects. This
module supplies those frames from a real local camera without turning raw video
into durable Jarvis state.

Design boundaries:
- camera access requires an explicit, identity-bound authorization policy;
- OpenCV and MediaPipe are optional/lazy dependencies, never imported by normal
  AI Core startup or CI tests;
- raw camera frames exist only as transient process objects and are never put in
  receipts, logs or model prompts;
- MediaPipe runs locally in VIDEO mode from a deployment-supplied model asset;
- timestamps must be timezone-aware and monotonically increasing;
- a failed/malformed detection degrades to no actionable hand frame rather than
  guessing confidence or handedness;
- this runtime creates observations only. It never grants OS or business-action
  authority.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from .spatial_interaction import HandLandmarkFrame, Handedness, Landmark3D

SPATIAL_CAMERA_RUNTIME_CONTRACT = "eay-spatial-camera-runtime-v1"


class SpatialCameraPolicy(BaseModel):
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    camera_device_ref: str = Field(min_length=1)
    camera_index: int = Field(default=0, ge=0, le=32)
    model_asset_path: str = Field(min_length=1)
    camera_authorized: bool = False
    mirror_input: bool = False
    max_hands: int = Field(default=1, ge=1, le=2)
    minimum_detection_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    minimum_presence_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    minimum_tracking_confidence: float = Field(default=0.70, ge=0.0, le=1.0)
    raw_frame_retained: bool = False
    remote_processing_allowed: bool = False
    recording_allowed: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def policy_stays_local_and_non_recording(self) -> "SpatialCameraPolicy":
        if self.raw_frame_retained or self.recording_allowed:
            raise ValueError("spatial_camera_policy_cannot_record_or_retain_frames")
        if self.remote_processing_allowed:
            raise ValueError("spatial_camera_policy_requires_local_processing")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_camera_observation_never_authorizes_business_side_effects")
        return self


class SpatialCameraObservationReceipt(BaseModel):
    contract: str = SPATIAL_CAMERA_RUNTIME_CONTRACT
    principal_ref: str
    identity_evidence_ref: str
    camera_device_ref: str
    observed_at: datetime
    camera_frame_available: bool
    hand_count: int = Field(ge=0, le=2)
    raw_frame_retained: bool = False
    landmark_frames_retained: bool = False
    remote_processing_used: bool = False
    recording_used: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def receipt_is_observation_only(self) -> "SpatialCameraObservationReceipt":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("spatial_camera_receipt_requires_timezone")
        if self.raw_frame_retained or self.landmark_frames_retained or self.recording_used:
            raise ValueError("spatial_camera_receipt_cannot_retain_camera_or_landmark_payload")
        if self.remote_processing_used:
            raise ValueError("spatial_camera_receipt_cannot_claim_remote_processing")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_camera_receipt_never_authorizes_business_side_effects")
        return self


class CameraCaptureBackend(Protocol):
    def read_frame(self) -> object | None: ...
    def close(self) -> None: ...


class HandLandmarkerBackend(Protocol):
    def detect(self, frame: object, timestamp_ms: int) -> object: ...
    def close(self) -> None: ...


def _safe_category(handedness_group: object) -> tuple[Handedness, float]:
    try:
        categories = list(handedness_group)  # type: ignore[arg-type]
    except TypeError:
        return Handedness.UNKNOWN, 0.0
    if not categories:
        return Handedness.UNKNOWN, 0.0
    category = categories[0]
    raw_name = getattr(category, "category_name", None) or getattr(category, "display_name", None)
    name = str(raw_name or "").casefold()
    if name == "left":
        hand = Handedness.LEFT
    elif name == "right":
        hand = Handedness.RIGHT
    else:
        hand = Handedness.UNKNOWN
    raw_score = getattr(category, "score", 0.0)
    try:
        score = float(raw_score)
    except (TypeError, ValueError):
        score = 0.0
    return hand, min(1.0, max(0.0, score))


def hand_landmarker_result_to_frames(
    *,
    result: object,
    observed_at: datetime,
) -> tuple[HandLandmarkFrame, ...]:
    """Convert a MediaPipe-like result into transient EAY hand frames.

    This function intentionally uses structural attribute access so it is
    deterministic and testable without importing MediaPipe in CI.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("spatial_camera_observation_requires_timezone")
    raw_hands = getattr(result, "hand_landmarks", None)
    if not isinstance(raw_hands, (list, tuple)):
        return ()
    raw_handedness = getattr(result, "handedness", ())
    if not isinstance(raw_handedness, (list, tuple)):
        raw_handedness = ()

    frames: list[HandLandmarkFrame] = []
    for index, raw_landmarks in enumerate(raw_hands):
        try:
            landmarks = list(raw_landmarks)
        except TypeError:
            continue
        if len(landmarks) != 21:
            continue
        converted: list[Landmark3D] = []
        malformed = False
        for item in landmarks:
            try:
                x = float(getattr(item, "x"))
                y = float(getattr(item, "y"))
                z_raw = getattr(item, "z", 0.0)
                z = float(0.0 if z_raw is None else z_raw)
                converted.append(Landmark3D(x=x, y=y, z=z))
            except (TypeError, ValueError, AttributeError):
                malformed = True
                break
        if malformed:
            continue
        hand, confidence = (
            _safe_category(raw_handedness[index])
            if index < len(raw_handedness)
            else (Handedness.UNKNOWN, 0.0)
        )
        frames.append(
            HandLandmarkFrame(
                observed_at=observed_at,
                handedness=hand,
                tracking_confidence=confidence,
                landmarks=tuple(converted),
                raw_video_retained=False,
            )
        )
    return tuple(frames)


class SpatialHandCameraRuntime:
    """Identity-bound camera orchestrator with no durable frame payload."""

    def __init__(
        self,
        *,
        policy: SpatialCameraPolicy,
        capture: CameraCaptureBackend,
        detector: HandLandmarkerBackend,
    ) -> None:
        if not policy.camera_authorized:
            raise PermissionError("spatial_camera_explicit_authorization_required")
        self.policy = policy
        self.capture = capture
        self.detector = detector
        self._last_timestamp_ms: int | None = None
        self._closed = False

    def observe(
        self,
        *,
        observed_at: datetime,
    ) -> tuple[tuple[HandLandmarkFrame, ...], SpatialCameraObservationReceipt]:
        if self._closed:
            raise RuntimeError("spatial_camera_runtime_closed")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("spatial_camera_observation_requires_timezone")
        timestamp_ms = int(observed_at.timestamp() * 1000)
        if self._last_timestamp_ms is not None and timestamp_ms <= self._last_timestamp_ms:
            raise ValueError("spatial_camera_timestamp_must_increase")
        self._last_timestamp_ms = timestamp_ms

        frame = self.capture.read_frame()
        if frame is None:
            return (), SpatialCameraObservationReceipt(
                principal_ref=self.policy.principal_ref,
                identity_evidence_ref=self.policy.identity_evidence_ref,
                camera_device_ref=self.policy.camera_device_ref,
                observed_at=observed_at,
                camera_frame_available=False,
                hand_count=0,
            )

        try:
            result = self.detector.detect(frame, timestamp_ms)
            frames = hand_landmarker_result_to_frames(result=result, observed_at=observed_at)
        finally:
            # Drop the only orchestration-layer reference immediately. Native
            # backends are forbidden from recording frames by policy.
            del frame

        return frames, SpatialCameraObservationReceipt(
            principal_ref=self.policy.principal_ref,
            identity_evidence_ref=self.policy.identity_evidence_ref,
            camera_device_ref=self.policy.camera_device_ref,
            observed_at=observed_at,
            camera_frame_available=True,
            hand_count=min(len(frames), 2),
        )

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.detector.close()
        finally:
            self.capture.close()
            self._closed = True

    def __enter__(self) -> "SpatialHandCameraRuntime":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


class OpenCVCameraCapture:
    """Lazy OpenCV capture; frames are returned in RGB memory only."""

    def __init__(self, *, camera_index: int, mirror_input: bool = False) -> None:
        try:
            import cv2  # type: ignore
        except ImportError:
            raise RuntimeError("spatial_camera_opencv_dependency_missing") from None
        self._cv2 = cv2
        self._capture = cv2.VideoCapture(camera_index)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError("spatial_camera_device_open_failed")
        self._mirror_input = mirror_input
        self._closed = False

    def read_frame(self) -> object | None:
        if self._closed:
            raise RuntimeError("spatial_camera_capture_closed")
        ok, frame = self._capture.read()
        if not ok or frame is None:
            return None
        if self._mirror_input:
            frame = self._cv2.flip(frame, 1)
        return self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        if not self._closed:
            self._capture.release()
            self._closed = True


class MediaPipeVideoHandLandmarker:
    """Lazy MediaPipe Tasks VIDEO-mode hand detector."""

    def __init__(self, *, policy: SpatialCameraPolicy) -> None:
        model_path = Path(policy.model_asset_path)
        if not model_path.is_file():
            raise FileNotFoundError("spatial_camera_hand_model_asset_missing")
        try:
            import mediapipe as mp  # type: ignore
        except ImportError:
            raise RuntimeError("spatial_camera_mediapipe_dependency_missing") from None
        self._mp = mp
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=policy.max_hands,
            min_hand_detection_confidence=policy.minimum_detection_confidence,
            min_hand_presence_confidence=policy.minimum_presence_confidence,
            min_tracking_confidence=policy.minimum_tracking_confidence,
        )
        self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self._closed = False

    def detect(self, frame: object, timestamp_ms: int) -> object:
        if self._closed:
            raise RuntimeError("spatial_camera_landmarker_closed")
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=frame)
        return self._landmarker.detect_for_video(image, timestamp_ms)

    def close(self) -> None:
        if not self._closed:
            self._landmarker.close()
            self._closed = True


def build_local_spatial_hand_camera(policy: SpatialCameraPolicy) -> SpatialHandCameraRuntime:
    """Build the real local webcam + MediaPipe spatial hand runtime."""

    if not policy.camera_authorized:
        raise PermissionError("spatial_camera_explicit_authorization_required")
    capture = OpenCVCameraCapture(
        camera_index=policy.camera_index,
        mirror_input=policy.mirror_input,
    )
    try:
        detector = MediaPipeVideoHandLandmarker(policy=policy)
    except Exception:
        capture.close()
        raise
    return SpatialHandCameraRuntime(policy=policy, capture=capture, detector=detector)
