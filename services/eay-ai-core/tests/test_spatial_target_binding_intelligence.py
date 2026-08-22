from datetime import datetime, timezone

import pytest

from app.desktop_window_runtime import DesktopRect, MonitorGeometry, WindowGeometry
from app.spatial_multimodal_fusion import (
    SpatialFusionCommand,
    SpatialFusionIntent,
    SpatialModality,
)
from app.spatial_target_binding import (
    WindowInventorySnapshot,
    bind_exact_window,
    execute_bound_window_move,
    gaze_candidates,
)

NOW = datetime(2026, 8, 18, 11, 40, tzinfo=timezone.utc)


class _Backend:
    def __init__(self, *, drift=False):
        self.moves = []
        self.drift = drift

    def monitors(self):
        second_left = 2100 if self.drift else 1920
        return (
            MonitorGeometry(
                monitor_id="monitor:left",
                bounds=DesktopRect(left=0, top=0, right=1920, bottom=1080),
                work_area=DesktopRect(left=0, top=0, right=1920, bottom=1040),
                primary=True,
            ),
            MonitorGeometry(
                monitor_id="monitor:right",
                bounds=DesktopRect(left=second_left, top=0, right=second_left + 1920, bottom=1080),
                work_area=DesktopRect(left=second_left, top=0, right=second_left + 1920, bottom=1040),
            ),
        )

    def windows(self):
        return _windows()

    def move_window(self, window_ref, rect, *, restore_maximized):
        self.moves.append((window_ref, rect, restore_maximized))


def _windows():
    return (
        WindowGeometry(
            window_ref="window:planogram-3d",
            rect=DesktopRect(left=100, top=100, right=900, bottom=700),
        ),
        WindowGeometry(
            window_ref="window:kpi",
            rect=DesktopRect(left=1000, top=120, right=1800, bottom=720),
        ),
    )


def _monitors():
    return _Backend().monitors()


def _snapshot():
    return WindowInventorySnapshot(
        observed_at_ms=int(NOW.timestamp() * 1000),
        windows=_windows(),
        monitors=_monitors(),
    )


def _intent(target="window:planogram-3d", command=SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT):
    return SpatialFusionIntent(
        spatial_session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        command=command,
        target_ref=target,
        emitted_at=NOW,
        confidence=0.95,
        modalities=(SpatialModality.VOICE, SpatialModality.GAZE),
        evidence_refs=("evidence://voice/1", "evidence://gaze/1"),
    )


def test_gaze_candidates_use_opaque_window_refs_and_virtual_desktop_geometry():
    candidates = gaze_candidates(_snapshot())
    assert {item.target_ref for item in candidates} == {"window:planogram-3d", "window:kpi"}
    assert all(0.0 <= item.left < item.right <= 1.0 for item in candidates)
    assert all(0.0 <= item.top < item.bottom <= 1.0 for item in candidates)


def test_fused_target_binds_exact_window_and_moves_that_window_only():
    snapshot = _snapshot()
    intent = _intent()
    bound = bind_exact_window(intent=intent, snapshot=snapshot)
    assert bound.window.window_ref == "window:planogram-3d"
    backend = _Backend()
    receipt = execute_bound_window_move(intent=intent, bound=bound, backend=backend)
    assert receipt.window_ref == "window:planogram-3d"
    assert receipt.target_monitor_id == "monitor:right"
    assert backend.moves[0][0] == "window:planogram-3d"
    assert all(move[0] != "window:kpi" for move in backend.moves)


def test_missing_or_cancel_target_cannot_bind():
    with pytest.raises(ValueError, match="exact_window_match_required"):
        bind_exact_window(intent=_intent(target="window:missing"), snapshot=_snapshot())
    with pytest.raises(ValueError, match="cancel_does_not_bind_window"):
        bind_exact_window(
            intent=SpatialFusionIntent(
                spatial_session_id="spatial:1",
                principal_ref="principal:erdi",
                identity_evidence_ref="identity://erdi/1",
                command=SpatialFusionCommand.CANCEL,
                emitted_at=NOW,
                confidence=1.0,
                modalities=(SpatialModality.VOICE,),
                evidence_refs=("evidence://voice/cancel",),
            ),
            snapshot=_snapshot(),
        )


def test_monitor_topology_drift_blocks_move_before_backend_action():
    intent = _intent()
    bound = bind_exact_window(intent=intent, snapshot=_snapshot())
    backend = _Backend(drift=True)
    # Source monitor remains left, so drift of the target monitor is legal; now
    # simulate source identity drift by binding a tampered source ref.
    tampered = bound.model_copy(update={"source_monitor_id": "monitor:old"})
    with pytest.raises(ValueError, match="monitor_topology_drift"):
        execute_bound_window_move(intent=intent, bound=tampered, backend=backend)
    assert backend.moves == []
