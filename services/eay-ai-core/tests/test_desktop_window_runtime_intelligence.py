import platform

import pytest

from app.desktop_window_runtime import (
    DesktopRect,
    MonitorDirection,
    MonitorGeometry,
    WindowGeometry,
    WindowsNativeWindowBackend,
    move_active_window_to_adjacent_monitor,
)


class FakeWindowBackend:
    def __init__(self, *, window=None, monitors=None):
        self.window = window or WindowGeometry(
            window_ref="window:opaque",
            rect=DesktopRect(left=120, top=80, right=920, bottom=680),
            maximized=False,
        )
        self._monitors = monitors or (
            MonitorGeometry(
                monitor_id="monitor:left",
                bounds=DesktopRect(left=0, top=0, right=1920, bottom=1080),
                work_area=DesktopRect(left=0, top=0, right=1920, bottom=1040),
                primary=True,
            ),
            MonitorGeometry(
                monitor_id="monitor:right",
                bounds=DesktopRect(left=1920, top=0, right=4480, bottom=1440),
                work_area=DesktopRect(left=1920, top=0, right=4480, bottom=1400),
            ),
        )
        self.moves = []

    def active_window(self):
        return self.window

    def monitors(self):
        return self._monitors

    def move_window(self, window_ref, rect, *, restore_maximized):
        self.moves.append((window_ref, rect, restore_maximized))


def test_move_active_window_right_preserves_geometry_within_target_work_area():
    backend = FakeWindowBackend()
    receipt = move_active_window_to_adjacent_monitor(
        backend=backend,
        direction=MonitorDirection.RIGHT,
    )

    assert receipt.source_monitor_id == "monitor:left"
    assert receipt.target_monitor_id == "monitor:right"
    assert receipt.after_rect.left >= 1920
    assert receipt.after_rect.right <= 4480
    assert receipt.after_rect.bottom <= 1400
    assert receipt.after_rect.width == receipt.before_rect.width
    assert receipt.after_rect.height == receipt.before_rect.height
    assert receipt.window_title_retained is False
    assert receipt.application_content_retained is False
    assert receipt.business_side_effects_authorized is False
    assert backend.moves[0][0] == "window:opaque"


def test_move_left_from_right_monitor_and_preserve_maximized_flag():
    backend = FakeWindowBackend(
        window=WindowGeometry(
            window_ref="window:max",
            rect=DesktopRect(left=2100, top=80, right=3300, bottom=900),
            maximized=True,
        )
    )
    receipt = move_active_window_to_adjacent_monitor(
        backend=backend,
        direction=MonitorDirection.LEFT,
    )

    assert receipt.target_monitor_id == "monitor:left"
    assert receipt.after_rect.left >= 0
    assert receipt.after_rect.right <= 1920
    assert backend.moves[0][2] is True
    assert receipt.was_maximized is True


def test_single_monitor_or_missing_direction_fails_closed():
    single = FakeWindowBackend(monitors=(
        MonitorGeometry(
            monitor_id="monitor:only",
            bounds=DesktopRect(left=0, top=0, right=1920, bottom=1080),
            work_area=DesktopRect(left=0, top=0, right=1920, bottom=1040),
            primary=True,
        ),
    ))
    with pytest.raises(ValueError, match="desktop_multi_monitor_required"):
        move_active_window_to_adjacent_monitor(
            backend=single,
            direction=MonitorDirection.RIGHT,
        )

    rightmost = FakeWindowBackend(
        window=WindowGeometry(
            window_ref="window:rightmost",
            rect=DesktopRect(left=2100, top=100, right=3000, bottom=700),
        )
    )
    with pytest.raises(ValueError, match="desktop_no_monitor_to_right"):
        move_active_window_to_adjacent_monitor(
            backend=rightmost,
            direction=MonitorDirection.RIGHT,
        )


def test_native_windows_backend_is_not_instantiated_on_non_windows_ci():
    if platform.system() == "Windows":
        pytest.skip("non-Windows guard only")
    with pytest.raises(RuntimeError, match="requires_windows"):
        WindowsNativeWindowBackend()
