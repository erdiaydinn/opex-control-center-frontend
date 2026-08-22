from datetime import datetime, timedelta, timezone

from app.spatial_interaction import (
    HandLandmarkFrame,
    Handedness,
    Landmark3D,
    SpatialGestureCommand,
    SpatialGestureRecognizer,
    new_spatial_control_session,
)

T0 = datetime(2026, 8, 18, 9, 30, tzinfo=timezone.utc)


def _landmarks(*, pinch_x=None, pinch_y=0.34):
    points = [Landmark3D(x=0.5, y=0.6, z=0.0) for _ in range(21)]
    points[0] = Landmark3D(x=0.5, y=0.82, z=0.0)
    points[9] = Landmark3D(x=0.5, y=0.56, z=0.0)

    for mcp, pip, tip, x in (
        (5, 6, 8, 0.43),
        (9, 10, 12, 0.50),
        (13, 14, 16, 0.57),
        (17, 18, 20, 0.64),
    ):
        points[mcp] = Landmark3D(x=x, y=0.59, z=0.0)
        points[pip] = Landmark3D(x=x, y=0.44, z=0.0)
        points[tip] = Landmark3D(x=x, y=0.24, z=0.0)

    points[4] = Landmark3D(x=0.30, y=0.48, z=0.0)
    if pinch_x is not None:
        points[4] = Landmark3D(x=pinch_x - 0.008, y=pinch_y, z=0.0)
        points[8] = Landmark3D(x=pinch_x + 0.008, y=pinch_y, z=0.0)
    return tuple(points)


def _frame(at, *, pinch_x=None, pinch_y=0.34, confidence=0.96):
    return HandLandmarkFrame(
        observed_at=at,
        handedness=Handedness.RIGHT,
        tracking_confidence=confidence,
        landmarks=_landmarks(pinch_x=pinch_x, pinch_y=pinch_y),
    )


def _session():
    return new_spatial_control_session(
        session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="evidence://identity/erdi",
        arm_evidence_ref="evidence://voice/jarvis-spatial-control",
        now=T0,
        duration_minutes=10,
    )


def _arm_and_grab(recognizer):
    assert recognizer.consume(_frame(T0)) is None
    assert recognizer.consume(_frame(T0 + timedelta(milliseconds=260))) is None
    assert recognizer.consume(_frame(T0 + timedelta(milliseconds=360), pinch_x=0.45)) is None


def test_open_palm_pinch_drag_right_emits_one_window_transfer_intent():
    recognizer = SpatialGestureRecognizer(session=_session())
    _arm_and_grab(recognizer)

    intent = recognizer.consume(_frame(T0 + timedelta(milliseconds=520), pinch_x=0.64))
    assert intent is not None
    assert intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT
    assert intent.principal_ref == "principal:erdi"
    assert intent.horizontal_displacement > 0.16
    assert intent.raw_landmarks_retained is False
    assert intent.business_side_effects_authorized is False

    # cooldown prevents duplicate transfers from the same physical gesture
    assert recognizer.consume(_frame(T0 + timedelta(milliseconds=600), pinch_x=0.68)) is None


def test_open_palm_pinch_drag_left_works_symmetrically():
    recognizer = SpatialGestureRecognizer(session=_session())
    assert recognizer.consume(_frame(T0)) is None
    assert recognizer.consume(_frame(T0 + timedelta(milliseconds=260))) is None
    assert recognizer.consume(_frame(T0 + timedelta(milliseconds=360), pinch_x=0.62)) is None

    intent = recognizer.consume(_frame(T0 + timedelta(milliseconds=520), pinch_x=0.40))
    assert intent is not None
    assert intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_LEFT
    assert intent.horizontal_displacement < -0.16


def test_vertical_drag_and_weak_tracking_do_not_emit_os_command():
    recognizer = SpatialGestureRecognizer(session=_session())
    _arm_and_grab(recognizer)
    assert recognizer.consume(
        _frame(T0 + timedelta(milliseconds=520), pinch_x=0.63, pinch_y=0.52)
    ) is None

    weak = SpatialGestureRecognizer(session=_session())
    assert weak.consume(_frame(T0, confidence=0.40)) is None
    assert weak.consume(_frame(T0 + timedelta(milliseconds=300), confidence=0.40)) is None


def test_expired_spatial_session_cannot_emit_intent():
    session = new_spatial_control_session(
        session_id="spatial:expired",
        principal_ref="principal:erdi",
        identity_evidence_ref="evidence://identity/erdi",
        arm_evidence_ref="evidence://voice/spatial",
        now=T0,
        duration_minutes=1,
    )
    recognizer = SpatialGestureRecognizer(session=session)
    late = T0 + timedelta(minutes=2)
    assert recognizer.consume(_frame(late)) is None
