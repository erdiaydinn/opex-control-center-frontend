import platform
from datetime import datetime, timezone

import pytest

from app.spatial_hud import HudPhase, SpatialHudSnapshot
from app.spatial_hud_overlay import (
    HudOverlayController,
    HudOverlayReceipt,
    WindowsHudOverlayRenderer,
    _safe_text,
    frame_from_snapshot,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


class _Backend:
    def __init__(self):
        self.frames = []
        self.hidden = 0
        self.closed = False

    def render(self, frame):
        self.frames.append(frame)
        return HudOverlayReceipt(
            phase=frame.phase,
            rendered=True,
            visible=True,
        )

    def hide(self):
        self.hidden += 1
        return HudOverlayReceipt(
            phase=HudPhase.IDLE,
            rendered=True,
            visible=False,
        )

    def close(self):
        self.closed = True


def _snapshot(**updates):
    payload = dict(
        spatial_session_id="spatial:1",
        principal_ref="principal:erdi",
        phase=HudPhase.FOCUSED,
        target_ref="window:secret-opaque-ref",
        confidence=0.934,
        cue="hud.focused",
    )
    payload.update(updates)
    return SpatialHudSnapshot(**payload)


def test_overlay_frame_contains_only_feedback_metadata_not_target_ref():
    frame = frame_from_snapshot(_snapshot())
    assert frame.target_present is True
    assert frame.confidence_percent == 93
    text = _safe_text(frame)
    assert text == "JARVIS  ·  HUD.FOCUSED  93%"
    assert "window:secret-opaque-ref" not in text
    serialized = frame.model_dump_json()
    assert "window:secret-opaque-ref" not in serialized
    assert frame.action_execution_authorized is False
    assert frame.business_side_effects_authorized is False


def test_overlay_controller_hides_idle_and_never_captures_input():
    backend = _Backend()
    controller = HudOverlayController(backend=backend)
    receipt = controller.present(_snapshot())
    assert receipt.visible is True
    assert receipt.click_through is True
    assert receipt.no_activate is True
    assert receipt.input_captured is False
    idle = controller.present(_snapshot(phase=HudPhase.IDLE, target_ref=None, confidence=None, cue="hud.idle"))
    assert idle.visible is False
    assert backend.hidden == 1
    controller.close()
    assert backend.closed is True


def test_native_windows_overlay_fails_closed_off_windows():
    if platform.system() == "Windows":
        pytest.skip("non-Windows failure contract")
    with pytest.raises(RuntimeError, match="requires_windows"):
        WindowsHudOverlayRenderer()
