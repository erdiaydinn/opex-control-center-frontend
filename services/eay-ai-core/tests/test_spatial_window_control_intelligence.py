from datetime import datetime, timedelta, timezone

import pytest

from app.desktop_window_runtime import DesktopRect, MonitorGeometry, WindowGeometry
from app.spatial_interaction import (
    Handedness,
    SpatialGestureCommand,
    SpatialGestureIntent,
    new_spatial_control_session,
)
from app.spatial_window_control import execute_spatial_window_intent

NOW = datetime(2026, 8, 18, 9, 45, tzinfo=timezone.utc)


class FakeBackend:
    def __init__(self):
        self.moves = []

    def active_window(self):
        return WindowGeometry(
            window_ref="window:opaque",
            rect=DesktopRect(left=100, top=100, right=900, bottom=700),
        )

    def monitors(self):
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
        self.moves.append((window_ref, rect, restore_maximized))


def _session():
    return new_spatial_control_session(
        session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="evidence://identity/erdi",
        arm_evidence_ref="evidence://voice/spatial-control",
        now=NOW,
    )


def _intent(**updates):
    payload = dict(
        session_id="spatial:1",
        principal_ref="principal:erdi",
        command=SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT,
        emitted_at=NOW + timedelta(seconds=1),
        handedness=Handedness.RIGHT,
        confidence=0.95,
        horizontal_displacement=0.24,
        source_evidence_ref="evidence://spatial-gesture/1",
    )
    payload.update(updates)
    return SpatialGestureIntent(**payload)


def test_identity_bound_gesture_moves_only_local_window():
    backend = FakeBackend()
    receipt = execute_spatial_window_intent(
        session=_session(),
        intent=_intent(),
        backend=backend,
    )

    assert receipt.move.target_monitor_id == "monitor:2"
    assert receipt.local_ui_side_effect_only is True
    assert receipt.business_side_effects_authorized is False
    assert receipt.raw_hand_data_retained is False
    assert len(backend.moves) == 1


def test_wrong_principal_or_session_is_rejected_before_os_action():
    backend = FakeBackend()
    with pytest.raises(ValueError, match="principal_mismatch"):
        execute_spatial_window_intent(
            session=_session(),
            intent=_intent(principal_ref="principal:other"),
            backend=backend,
        )
    assert backend.moves == []

    with pytest.raises(ValueError, match="session_mismatch"):
        execute_spatial_window_intent(
            session=_session(),
            intent=_intent(session_id="spatial:other"),
            backend=backend,
        )
    assert backend.moves == []


def test_gesture_outside_armed_window_is_rejected():
    backend = FakeBackend()
    with pytest.raises(ValueError, match="outside_session_window"):
        execute_spatial_window_intent(
            session=_session(),
            intent=_intent(emitted_at=NOW + timedelta(minutes=11)),
            backend=backend,
        )
    assert backend.moves == []
