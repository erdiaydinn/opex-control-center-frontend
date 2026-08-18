from datetime import datetime, timedelta, timezone

import pytest

from app.spatial_gaze import (
    FaceLandmark2D,
    FaceLandmarkFrame,
    GazeCalibration,
    GazePointObservation,
    GazeTargetCandidate,
    GazeTargetTracker,
    derive_gaze_point,
)

NOW = datetime(2026, 8, 18, 10, 40, tzinfo=timezone.utc)


def _calibration(**updates):
    payload = dict(
        calibration_ref="gaze-calibration://session-1",
        spatial_session_id="spatial-session-1",
        principal_ref="user:spatial-1",
        identity_evidence_ref="identity://session/spatial-1",
        calibrated_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=30),
        center_horizontal_ratio=0.50,
        center_vertical_ratio=0.50,
        horizontal_gain=1.0,
        vertical_gain=1.0,
        minimum_tracking_confidence=0.75,
        maximum_bilateral_disagreement=0.14,
    )
    payload.update(updates)
    return GazeCalibration(**payload)


def _frame(*, at=NOW, confidence=0.95, left_iris_x=0.50, right_iris_x=0.50):
    points = [FaceLandmark2D(x=0.50, y=0.50, z=0.0) for _ in range(478)]

    # Horizontal eye aperture corners.
    points[33] = FaceLandmark2D(x=0.40, y=0.50)
    points[133] = FaceLandmark2D(x=0.60, y=0.50)
    points[263] = FaceLandmark2D(x=0.40, y=0.50)
    points[362] = FaceLandmark2D(x=0.60, y=0.50)

    # Vertical eye aperture reference points.
    points[159] = FaceLandmark2D(x=0.50, y=0.40)
    points[145] = FaceLandmark2D(x=0.50, y=0.60)
    points[386] = FaceLandmark2D(x=0.50, y=0.40)
    points[374] = FaceLandmark2D(x=0.50, y=0.60)

    for index in (469, 470, 471, 472):
        points[index] = FaceLandmark2D(x=right_iris_x, y=0.50)
    for index in (474, 475, 476, 477):
        points[index] = FaceLandmark2D(x=left_iris_x, y=0.50)

    return FaceLandmarkFrame(
        observed_at=at,
        tracking_confidence=confidence,
        landmarks=tuple(points),
    )


def _point(*, at=NOW, x=0.50, y=0.50, confidence=0.95, **updates):
    payload = dict(
        spatial_session_id="spatial-session-1",
        principal_ref="user:spatial-1",
        identity_evidence_ref="identity://session/spatial-1",
        calibration_ref="gaze-calibration://session-1",
        observed_at=at,
        screen_x=x,
        screen_y=y,
        confidence=confidence,
        bilateral_disagreement=0.0,
        source_evidence_ref=f"evidence://gaze/{int(at.timestamp() * 1000)}",
    )
    payload.update(updates)
    return GazePointObservation(**payload)


def test_neutral_bilateral_gaze_maps_to_calibrated_screen_center_without_landmark_retention():
    point = derive_gaze_point(frame=_frame(), calibration=_calibration())
    assert point is not None
    assert point.screen_x == pytest.approx(0.50)
    assert point.screen_y == pytest.approx(0.50)
    assert point.confidence == pytest.approx(0.95)
    assert point.bilateral_disagreement == pytest.approx(0.0)
    assert point.raw_landmarks_retained is False
    assert point.business_side_effects_authorized is False
    assert '"landmarks"' not in point.model_dump_json()


def test_bilateral_eye_disagreement_or_weak_tracking_fails_closed():
    assert derive_gaze_point(
        frame=_frame(left_iris_x=0.58, right_iris_x=0.50),
        calibration=_calibration(),
    ) is None
    assert derive_gaze_point(
        frame=_frame(confidence=0.60),
        calibration=_calibration(),
    ) is None


def test_refined_face_landmarks_are_required_and_calibration_cannot_authorize_actions():
    with pytest.raises(ValueError, match="refined_face_landmarks_required"):
        FaceLandmarkFrame(
            observed_at=NOW,
            tracking_confidence=0.95,
            landmarks=tuple(FaceLandmark2D(x=0.5, y=0.5) for _ in range(477)),
        )
    with pytest.raises(ValueError, match="never_authorizes_business_side_effects"):
        _calibration(business_side_effects_authorized=True)
    with pytest.raises(ValueError, match="cannot_retain_landmarks"):
        _calibration(raw_landmarks_retained=True)


def test_gaze_tracker_requires_unique_stable_target_and_dwell():
    tracker = GazeTargetTracker(calibration=_calibration(), dwell_ms=320)
    unique = (
        GazeTargetCandidate(
            target_ref="window://planogram-3d",
            left=0.30,
            top=0.30,
            right=0.70,
            bottom=0.70,
        ),
    )
    assert tracker.consume(point=_point(at=NOW), candidates=unique) is None
    assert tracker.consume(point=_point(at=NOW + timedelta(milliseconds=200)), candidates=unique) is None
    intent = tracker.consume(point=_point(at=NOW + timedelta(milliseconds=350)), candidates=unique)
    assert intent is not None
    assert intent.target_ref == "window://planogram-3d"
    assert intent.dwell_ms >= 320
    assert intent.local_ui_referent_only is True
    assert intent.click_authorized is False
    assert intent.business_side_effects_authorized is False
    assert intent.raw_landmarks_retained is False


def test_overlapping_targets_are_ambiguous_and_never_emit_focus():
    tracker = GazeTargetTracker(calibration=_calibration(), dwell_ms=100)
    overlapping = (
        GazeTargetCandidate(target_ref="window://a", left=0.2, top=0.2, right=0.8, bottom=0.8),
        GazeTargetCandidate(target_ref="window://b", left=0.4, top=0.4, right=0.6, bottom=0.6),
    )
    assert tracker.consume(point=_point(at=NOW), candidates=overlapping) is None
    assert tracker.consume(point=_point(at=NOW + timedelta(milliseconds=200)), candidates=overlapping) is None


def test_gaze_tracker_is_identity_session_and_expiry_bound():
    tracker = GazeTargetTracker(calibration=_calibration(), dwell_ms=100)
    target = (
        GazeTargetCandidate(target_ref="window://a", left=0.2, top=0.2, right=0.8, bottom=0.8),
    )
    with pytest.raises(ValueError, match="point_session_mismatch"):
        tracker.consume(
            point=_point(spatial_session_id="other-session"),
            candidates=target,
        )
    with pytest.raises(ValueError, match="point_principal_mismatch"):
        tracker.consume(
            point=_point(principal_ref="user:other"),
            candidates=target,
        )
    with pytest.raises(ValueError, match="point_identity_mismatch"):
        tracker.consume(
            point=_point(identity_evidence_ref="identity://other"),
            candidates=target,
        )

    expired = _point(at=NOW + timedelta(hours=1))
    assert tracker.consume(point=expired, candidates=target) is None


def test_derive_gaze_point_rejects_expired_calibration():
    calibration = _calibration(expires_at=NOW - timedelta(milliseconds=1))
    assert derive_gaze_point(frame=_frame(), calibration=calibration) is None
