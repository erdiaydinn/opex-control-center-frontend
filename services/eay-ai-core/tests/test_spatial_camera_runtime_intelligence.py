from datetime import datetime, timedelta, timezone

import pytest

from app.spatial_camera_runtime import (
    SpatialCameraPolicy,
    SpatialHandCameraRuntime,
    hand_landmarker_result_to_frames,
)
from app.spatial_interaction import Handedness

NOW = datetime(2026, 8, 18, 10, 30, tzinfo=timezone.utc)


class _Landmark:
    def __init__(self, x=0.5, y=0.5, z=0.0):
        self.x = x
        self.y = y
        self.z = z


class _Category:
    def __init__(self, name="Right", score=0.93):
        self.category_name = name
        self.score = score


class _Result:
    def __init__(self, *, landmark_count=21, handedness=True):
        self.hand_landmarks = [[_Landmark(x=0.10 + index * 0.01) for index in range(landmark_count)]]
        self.handedness = [[_Category()]] if handedness else []


class _Capture:
    def __init__(self, frame=object()):
        self.frame = frame
        self.reads = 0
        self.closed = False

    def read_frame(self):
        self.reads += 1
        return self.frame

    def close(self):
        self.closed = True


class _Detector:
    def __init__(self, result=None):
        self.result = result or _Result()
        self.timestamps = []
        self.frames = []
        self.closed = False

    def detect(self, frame, timestamp_ms):
        self.frames.append(frame)
        self.timestamps.append(timestamp_ms)
        return self.result

    def close(self):
        self.closed = True


def _policy(**updates):
    payload = dict(
        principal_ref="user:spatial-1",
        identity_evidence_ref="identity://session/spatial-1",
        camera_device_ref="camera://integrated-front",
        camera_index=0,
        model_asset_path="/opt/eay/models/hand_landmarker.task",
        camera_authorized=True,
    )
    payload.update(updates)
    return SpatialCameraPolicy(**payload)


def test_mediapipe_like_result_converts_exact_21_landmarks_without_raw_video():
    frames = hand_landmarker_result_to_frames(result=_Result(), observed_at=NOW)
    assert len(frames) == 1
    frame = frames[0]
    assert len(frame.landmarks) == 21
    assert frame.handedness is Handedness.RIGHT
    assert frame.tracking_confidence == pytest.approx(0.93)
    assert frame.raw_video_retained is False


def test_malformed_hand_result_fails_closed_instead_of_guessing():
    assert hand_landmarker_result_to_frames(result=_Result(landmark_count=20), observed_at=NOW) == ()
    frames = hand_landmarker_result_to_frames(
        result=_Result(handedness=False),
        observed_at=NOW,
    )
    assert len(frames) == 1
    assert frames[0].handedness is Handedness.UNKNOWN
    assert frames[0].tracking_confidence == 0.0


def test_camera_runtime_requires_explicit_identity_bound_authorization():
    with pytest.raises(PermissionError, match="explicit_authorization_required"):
        SpatialHandCameraRuntime(
            policy=_policy(camera_authorized=False),
            capture=_Capture(),
            detector=_Detector(),
        )

    with pytest.raises(ValueError, match="cannot_record_or_retain_frames"):
        _policy(recording_allowed=True)
    with pytest.raises(ValueError, match="requires_local_processing"):
        _policy(remote_processing_allowed=True)
    with pytest.raises(ValueError, match="never_authorizes_business_side_effects"):
        _policy(business_side_effects_authorized=True)


def test_camera_observation_returns_transient_landmarks_and_content_free_receipt():
    raw_marker = "RAW_FRAME_PAYLOAD_SHOULD_NOT_PERSIST_7e5d"
    capture = _Capture(frame=raw_marker)
    detector = _Detector()
    runtime = SpatialHandCameraRuntime(
        policy=_policy(),
        capture=capture,
        detector=detector,
    )

    frames, receipt = runtime.observe(observed_at=NOW)
    assert len(frames) == 1
    assert capture.reads == 1
    assert detector.frames == [raw_marker]
    assert receipt.principal_ref == "user:spatial-1"
    assert receipt.identity_evidence_ref == "identity://session/spatial-1"
    assert receipt.camera_frame_available is True
    assert receipt.hand_count == 1
    assert receipt.raw_frame_retained is False
    assert receipt.landmark_frames_retained is False
    assert receipt.remote_processing_used is False
    assert receipt.business_side_effects_authorized is False
    serialized = receipt.model_dump_json()
    assert raw_marker not in serialized
    assert '"landmarks"' not in serialized


def test_camera_timestamp_must_increase_and_close_is_idempotent():
    capture = _Capture()
    detector = _Detector()
    runtime = SpatialHandCameraRuntime(
        policy=_policy(),
        capture=capture,
        detector=detector,
    )
    runtime.observe(observed_at=NOW)
    with pytest.raises(ValueError, match="timestamp_must_increase"):
        runtime.observe(observed_at=NOW)
    runtime.observe(observed_at=NOW + timedelta(milliseconds=1))
    assert detector.timestamps[1] > detector.timestamps[0]

    runtime.close()
    runtime.close()
    assert capture.closed is True
    assert detector.closed is True
    with pytest.raises(RuntimeError, match="runtime_closed"):
        runtime.observe(observed_at=NOW + timedelta(seconds=1))


def test_missing_camera_frame_yields_safe_empty_observation():
    capture = _Capture(frame=None)
    detector = _Detector()
    runtime = SpatialHandCameraRuntime(
        policy=_policy(),
        capture=capture,
        detector=detector,
    )
    frames, receipt = runtime.observe(observed_at=NOW)
    assert frames == ()
    assert receipt.camera_frame_available is False
    assert receipt.hand_count == 0
    assert detector.timestamps == []
