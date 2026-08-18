"""Native multi-monitor window movement for Jarvis spatial control.

The pure planning layer is platform-independent and testable. The Windows
backend uses Win32 APIs directly through ``ctypes``. No window titles, document
text, clipboard data or application content are persisted; receipts retain only
opaque window/monitor identifiers and geometry.
"""

from __future__ import annotations

import ctypes
import hashlib
import platform
from ctypes import wintypes
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

DESKTOP_WINDOW_RUNTIME_CONTRACT = "eay-desktop-window-runtime-v1"


class _WinRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _WinMonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _WinRect),
        ("rcWork", _WinRect),
        ("dwFlags", wintypes.DWORD),
    ]


class MonitorDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"


class DesktopRect(BaseModel):
    left: int
    top: int
    right: int
    bottom: int

    @model_validator(mode="after")
    def rect_has_area(self) -> "DesktopRect":
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("desktop_rect_requires_positive_area")
        return self

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


class MonitorGeometry(BaseModel):
    monitor_id: str = Field(min_length=1)
    bounds: DesktopRect
    work_area: DesktopRect
    primary: bool = False


class WindowGeometry(BaseModel):
    window_ref: str = Field(min_length=1)
    rect: DesktopRect
    maximized: bool = False


class WindowMoveReceipt(BaseModel):
    contract: str = DESKTOP_WINDOW_RUNTIME_CONTRACT
    window_ref: str
    direction: MonitorDirection
    source_monitor_id: str
    target_monitor_id: str
    before_rect: DesktopRect
    after_rect: DesktopRect
    was_maximized: bool
    completed: bool
    window_title_retained: bool = False
    application_content_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def receipt_stays_local_and_content_free(self) -> "WindowMoveReceipt":
        if self.window_title_retained or self.application_content_retained:
            raise ValueError("desktop_window_receipt_cannot_retain_content")
        if self.business_side_effects_authorized:
            raise ValueError("desktop_window_move_never_authorizes_business_side_effects")
        if self.source_monitor_id == self.target_monitor_id:
            raise ValueError("desktop_window_move_requires_different_monitor")
        return self


class DesktopWindowBackend(Protocol):
    def active_window(self) -> WindowGeometry: ...
    def monitors(self) -> tuple[MonitorGeometry, ...]: ...
    def move_window(self, window_ref: str, rect: DesktopRect, *, restore_maximized: bool) -> None: ...


def _distance_squared_to_rect_center(rect: DesktopRect, monitor: MonitorGeometry) -> float:
    dx = rect.center_x - monitor.work_area.center_x
    dy = rect.center_y - monitor.work_area.center_y
    return dx * dx + dy * dy


def _source_monitor(window: WindowGeometry, monitors: tuple[MonitorGeometry, ...]) -> MonitorGeometry:
    cx, cy = window.rect.center_x, window.rect.center_y
    containing = [
        monitor
        for monitor in monitors
        if monitor.work_area.left <= cx < monitor.work_area.right
        and monitor.work_area.top <= cy < monitor.work_area.bottom
    ]
    if containing:
        return containing[0]
    return min(monitors, key=lambda monitor: _distance_squared_to_rect_center(window.rect, monitor))


def _adjacent_monitor(source: MonitorGeometry, monitors: tuple[MonitorGeometry, ...], direction: MonitorDirection) -> MonitorGeometry:
    others = [monitor for monitor in monitors if monitor.monitor_id != source.monitor_id]
    if direction is MonitorDirection.RIGHT:
        directional = [monitor for monitor in others if monitor.work_area.center_x > source.work_area.center_x]
        if not directional:
            raise ValueError("desktop_no_monitor_to_right")
        return min(directional, key=lambda monitor: (monitor.work_area.center_x - source.work_area.center_x, abs(monitor.work_area.center_y - source.work_area.center_y)))
    directional = [monitor for monitor in others if monitor.work_area.center_x < source.work_area.center_x]
    if not directional:
        raise ValueError("desktop_no_monitor_to_left")
    return min(directional, key=lambda monitor: (source.work_area.center_x - monitor.work_area.center_x, abs(monitor.work_area.center_y - source.work_area.center_y)))


def _project_window_rect(window: WindowGeometry, source: MonitorGeometry, target: MonitorGeometry) -> DesktopRect:
    src = source.work_area
    dst = target.work_area
    width = min(window.rect.width, dst.width)
    height = min(window.rect.height, dst.height)
    src_x_range = max(1, src.width - window.rect.width)
    src_y_range = max(1, src.height - window.rect.height)
    rel_x = min(1.0, max(0.0, (window.rect.left - src.left) / src_x_range))
    rel_y = min(1.0, max(0.0, (window.rect.top - src.top) / src_y_range))
    dst_x_range = max(0, dst.width - width)
    dst_y_range = max(0, dst.height - height)
    left = dst.left + round(rel_x * dst_x_range)
    top = dst.top + round(rel_y * dst_y_range)
    return DesktopRect(left=left, top=top, right=left + width, bottom=top + height)


def move_active_window_to_adjacent_monitor(*, backend: DesktopWindowBackend, direction: MonitorDirection) -> WindowMoveReceipt:
    monitors = backend.monitors()
    if len(monitors) < 2:
        raise ValueError("desktop_multi_monitor_required")
    window = backend.active_window()
    source = _source_monitor(window, monitors)
    target = _adjacent_monitor(source, monitors, direction)
    after = _project_window_rect(window, source, target)
    backend.move_window(window.window_ref, after, restore_maximized=window.maximized)
    return WindowMoveReceipt(
        window_ref=window.window_ref,
        direction=direction,
        source_monitor_id=source.monitor_id,
        target_monitor_id=target.monitor_id,
        before_rect=window.rect,
        after_rect=after,
        was_maximized=window.maximized,
        completed=True,
    )


def _opaque_ref(prefix: str, native_id: int | str) -> str:
    digest = hashlib.sha256(str(native_id).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _handle_int(value: object) -> int:
    if isinstance(value, int):
        return value
    raw = ctypes.cast(value, ctypes.c_void_p).value
    if raw is None:
        return 0
    return int(raw)


class WindowsNativeWindowBackend:
    SW_RESTORE = 9
    SW_MAXIMIZE = 3
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    MONITORINFOF_PRIMARY = 0x00000001

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("windows_native_window_backend_requires_windows")
        self._user32 = ctypes.windll.user32
        self._window_handles: dict[str, int] = {}

        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_WinRect)]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        self._user32.IsZoomed.argtypes = [wintypes.HWND]
        self._user32.IsZoomed.restype = wintypes.BOOL
        self._user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_WinMonitorInfo)]
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL
        self._user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self._user32.SetWindowPos.restype = wintypes.BOOL
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL

    @staticmethod
    def _rect(value: _WinRect) -> DesktopRect:
        return DesktopRect(left=value.left, top=value.top, right=value.right, bottom=value.bottom)

    def active_window(self) -> WindowGeometry:
        hwnd_native = self._user32.GetForegroundWindow()
        hwnd = _handle_int(hwnd_native)
        if not hwnd:
            raise RuntimeError("windows_active_window_missing")
        rect = _WinRect()
        if not self._user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            raise RuntimeError("windows_get_window_rect_failed")
        ref = _opaque_ref("window", hwnd)
        self._window_handles[ref] = hwnd
        return WindowGeometry(window_ref=ref, rect=self._rect(rect), maximized=bool(self._user32.IsZoomed(wintypes.HWND(hwnd))))

    def monitors(self) -> tuple[MonitorGeometry, ...]:
        found: list[MonitorGeometry] = []
        monitor_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(_WinRect), wintypes.LPARAM)

        def callback(hmonitor, _hdc, _rect, _data):
            info = _WinMonitorInfo()
            info.cbSize = ctypes.sizeof(_WinMonitorInfo)
            if not self._user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                return 1
            handle = _handle_int(hmonitor)
            found.append(
                MonitorGeometry(
                    monitor_id=_opaque_ref("monitor", handle),
                    bounds=self._rect(info.rcMonitor),
                    work_area=self._rect(info.rcWork),
                    primary=bool(info.dwFlags & self.MONITORINFOF_PRIMARY),
                )
            )
            return 1

        callback_ref = monitor_enum_proc(callback)
        self._user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(_WinRect), monitor_enum_proc, wintypes.LPARAM]
        self._user32.EnumDisplayMonitors.restype = wintypes.BOOL
        if not self._user32.EnumDisplayMonitors(0, None, callback_ref, 0):
            raise RuntimeError("windows_enum_display_monitors_failed")
        if not found:
            raise RuntimeError("windows_monitor_inventory_empty")
        return tuple(found)

    def move_window(self, window_ref: str, rect: DesktopRect, *, restore_maximized: bool) -> None:
        hwnd = self._window_handles.get(window_ref)
        if hwnd is None:
            raise KeyError("windows_window_ref_unknown")
        hwnd_value = wintypes.HWND(hwnd)
        if restore_maximized:
            self._user32.ShowWindow(hwnd_value, self.SW_RESTORE)
        flags = self.SWP_NOZORDER | self.SWP_NOACTIVATE
        ok = self._user32.SetWindowPos(hwnd_value, 0, rect.left, rect.top, rect.width, rect.height, flags)
        if not ok:
            raise RuntimeError("windows_set_window_pos_failed")
        if restore_maximized:
            self._user32.ShowWindow(hwnd_value, self.SW_MAXIMIZE)
