from datetime import datetime, timezone

from app.desktop_window_runtime import DesktopRect, MonitorGeometry, WindowGeometry
from app.spatial_interaction import (
    HandLandmarkFrame,
    Handedness,
    Landmark3D,
    SpatialGestureCommand,
    SpatialGestureRecognizer,
    new_spatial_control_session,
)
from app.spatial_window_control import execute_spatial_window_intent

NOW = datetime(2026, 8, 18, 11, 0, tzinfo=timezone.utc)


class _BackendMustNotMove:
    def __init__(self):
        self.calls = 0

    def active_window(self):
        self.calls += 1
        return WindowGeometry(
            window_ref="window:should-not-be-read",
            rect=DesktopRect(left=0, top=0, right=500, bottom=500),
        )

    def monitors(self):
        self.calls += 1
        return (
            MonitorGeometry(
                monitor_id="monitor:1",
                bounds=DesktopRect(left=0, top=0, right=1920, bottom=1080),
                work_area=DesktopRect(left=0, top=0, right=1920, bottom=1040),
                primary=True,
            ),
            MonitorGeometry(
                monitor_id="monitor:2",
                bounds=DesktopRect(left=1920, top=0, right=3840, bottom=1080),
                work_area=DesktopRect(left=1920, top=0, right=3840, bottom=1040),
            ),
        )

    def move_window(self, window_ref, rect, *, restore_maximized):
        self.calls += 1
        raise AssertionError("cancel must never move a window")


def _session():
    return new_spatial_control_session(
        session_id="spatial:cancel-1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/cancel-1",
        arm_evidence_ref="evidence://spatial/armed",
        now=NOW,
    )


def _fist_frame():
    points = [Landmark3D(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    points[0] = Landmark3D(x=0.5, y=0.80, z=0.0)
    points[9] = Landmark3D(x=0.5, y=0.56, z=0.0)
    for mcp, pip, tip, x in (
        (5, 6, 8, 0.42),
        (9, 10, 12, 0.49),
        (13, 14, 16, 0.56),
        (17, 18, 20, 0.63),
    ):
        points[mcp] = Landmark3D(x=x, y=0.54, z=0.0)
        points[pip] = Landmark3D(x=x, y=0.53, z=0.0)
        points[tip] = Landmark3D(x=x, y=0.59, z=0.0)
    points[4] = Landmark3D(x=0.40, y=0.55, z=0.0)
    return HandLandmarkFrame(
        observed_at=NOW,
        handedness=Handedness.RIGHT,
        tracking_confidence=0.97,
        landmarks=tuple(points),
    )


def test_closed_fist_emits_explicit_cancel_intent():
    recognizer = SpatialGestureRecognizer(session=_session())
    intent = recognizer.consume(_fist_frame())
    assert intent is not None
    assert intent.command is SpatialGestureCommand.CANCEL
    assert intent.horizontal_displacement == 0.0
    assert intent.confidence == 0.97
    assert intent.business_side_effects_authorized is False
    assert intent.raw_landmarks_retained is False


def test_cancel_receipt_performs_zero_desktop_backend_calls():
    recognizer = SpatialGestureRecognizer(session=_session())
    intent = recognizer.consume(_fist_frame())
    assert intent is not None
    backend = _BackendMustNotMove()
    receipt = execute_spatial_window_intent(
        session=_session(),
        intent=intent,
        backend=backend,
    )
    assert receipt.command is SpatialGestureCommand.CANCEL
    assert receipt.cancelled is True
    assert receipt.move is None
    assert receipt.business_side_effects_authorized is False
    assert backend.calls == 0
