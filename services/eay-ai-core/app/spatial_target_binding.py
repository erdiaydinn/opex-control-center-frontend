"""Exact gaze-target binding and selected-window execution for Jarvis.

The fusion layer emits an opaque local ``target_ref``. This module proves that
reference corresponds to exactly one currently observed top-level desktop
window before any OS movement. Window titles/content never enter the contract.
A fused spatial intent remains limited to reversible local UI movement and can
never authorize a business mutation.
"""

from __future__ import annotations

import ctypes
import hashlib
import platform
from ctypes import wintypes
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .desktop_window_runtime import DesktopRect, MonitorDirection, MonitorGeometry, WindowGeometry, WindowMoveReceipt
from .spatial_gaze import GazeTargetCandidate
from .spatial_multimodal_fusion import SpatialFusionCommand, SpatialFusionIntent

SPATIAL_TARGET_BINDING_CONTRACT = "eay-spatial-target-binding-v1"


class _TargetWinRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _TargetWinMonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _TargetWinRect),
        ("rcWork", _TargetWinRect),
        ("dwFlags", wintypes.DWORD),
    ]


class WindowInventoryProvider(Protocol):
    def windows(self) -> tuple[WindowGeometry, ...]: ...
    def monitors(self) -> tuple[MonitorGeometry, ...]: ...
    def move_window(self, window_ref: str, rect: DesktopRect, *, restore_maximized: bool) -> None: ...


class WindowInventorySnapshot(BaseModel):
    contract: str = SPATIAL_TARGET_BINDING_CONTRACT
    observed_at_ms: int = Field(ge=0)
    windows: tuple[WindowGeometry, ...]
    monitors: tuple[MonitorGeometry, ...]
    window_titles_retained: bool = False
    application_content_retained: bool = False

    @model_validator(mode="after")
    def snapshot_is_content_free(self) -> "WindowInventorySnapshot":
        refs = [item.window_ref for item in self.windows]
        if len(refs) != len(set(refs)):
            raise ValueError("spatial_window_inventory_duplicate_ref")
        monitor_refs = [item.monitor_id for item in self.monitors]
        if len(monitor_refs) != len(set(monitor_refs)):
            raise ValueError("spatial_monitor_inventory_duplicate_ref")
        if self.window_titles_retained or self.application_content_retained:
            raise ValueError("spatial_window_inventory_cannot_retain_content")
        return self


class BoundWindowTarget(BaseModel):
    contract: str = SPATIAL_TARGET_BINDING_CONTRACT
    target_ref: str
    window: WindowGeometry
    source_monitor_id: str
    binding_evidence_ref: str
    exact_match: bool = True
    application_content_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def binding_is_local_only(self) -> "BoundWindowTarget":
        if self.target_ref != self.window.window_ref or not self.exact_match:
            raise ValueError("spatial_target_binding_requires_exact_window_ref")
        if self.application_content_retained:
            raise ValueError("spatial_target_binding_cannot_retain_content")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_target_binding_never_authorizes_business_side_effects")
        return self


def _source_monitor(window: WindowGeometry, monitors: tuple[MonitorGeometry, ...]) -> MonitorGeometry:
    if not monitors:
        raise ValueError("spatial_target_monitor_inventory_empty")
    cx = window.rect.center_x
    cy = window.rect.center_y
    containing = [
        monitor
        for monitor in monitors
        if monitor.work_area.left <= cx < monitor.work_area.right
        and monitor.work_area.top <= cy < monitor.work_area.bottom
    ]
    if containing:
        return containing[0]
    return min(
        monitors,
        key=lambda monitor: (
            (window.rect.center_x - monitor.work_area.center_x) ** 2
            + (window.rect.center_y - monitor.work_area.center_y) ** 2
        ),
    )


def _adjacent(
    source: MonitorGeometry,
    monitors: tuple[MonitorGeometry, ...],
    direction: MonitorDirection,
) -> MonitorGeometry:
    others = [item for item in monitors if item.monitor_id != source.monitor_id]
    if direction is MonitorDirection.RIGHT:
        eligible = [item for item in others if item.work_area.center_x > source.work_area.center_x]
        if not eligible:
            raise ValueError("spatial_target_no_monitor_to_right")
        return min(
            eligible,
            key=lambda item: (
                item.work_area.center_x - source.work_area.center_x,
                abs(item.work_area.center_y - source.work_area.center_y),
            ),
        )
    eligible = [item for item in others if item.work_area.center_x < source.work_area.center_x]
    if not eligible:
        raise ValueError("spatial_target_no_monitor_to_left")
    return min(
        eligible,
        key=lambda item: (
            source.work_area.center_x - item.work_area.center_x,
            abs(item.work_area.center_y - source.work_area.center_y),
        ),
    )


def _project(window: WindowGeometry, source: MonitorGeometry, target: MonitorGeometry) -> DesktopRect:
    src = source.work_area
    dst = target.work_area
    width = min(window.rect.width, dst.width)
    height = min(window.rect.height, dst.height)
    source_x_range = max(1, src.width - window.rect.width)
    source_y_range = max(1, src.height - window.rect.height)
    rel_x = min(1.0, max(0.0, (window.rect.left - src.left) / source_x_range))
    rel_y = min(1.0, max(0.0, (window.rect.top - src.top) / source_y_range))
    left = dst.left + round(rel_x * max(0, dst.width - width))
    top = dst.top + round(rel_y * max(0, dst.height - height))
    return DesktopRect(left=left, top=top, right=left + width, bottom=top + height)


def gaze_candidates(snapshot: WindowInventorySnapshot) -> tuple[GazeTargetCandidate, ...]:
    if not snapshot.monitors:
        return ()
    left = min(item.bounds.left for item in snapshot.monitors)
    top = min(item.bounds.top for item in snapshot.monitors)
    right = max(item.bounds.right for item in snapshot.monitors)
    bottom = max(item.bounds.bottom for item in snapshot.monitors)
    width = max(1, right - left)
    height = max(1, bottom - top)

    return tuple(
        GazeTargetCandidate(
            target_ref=window.window_ref,
            left=max(0.0, min(1.0, (window.rect.left - left) / width)),
            top=max(0.0, min(1.0, (window.rect.top - top) / height)),
            right=max(0.0, min(1.0, (window.rect.right - left) / width)),
            bottom=max(0.0, min(1.0, (window.rect.bottom - top) / height)),
        )
        for window in snapshot.windows
    )


def bind_exact_window(*, intent: SpatialFusionIntent, snapshot: WindowInventorySnapshot) -> BoundWindowTarget:
    if intent.command is SpatialFusionCommand.CANCEL:
        raise ValueError("spatial_target_cancel_does_not_bind_window")
    if not intent.target_ref:
        raise ValueError("spatial_target_ref_required")
    matches = [item for item in snapshot.windows if item.window_ref == intent.target_ref]
    if len(matches) != 1:
        raise ValueError("spatial_target_exact_window_match_required")
    window = matches[0]
    source = _source_monitor(window, snapshot.monitors)
    fingerprint = hashlib.sha256(
        f"{intent.spatial_session_id}|{intent.target_ref}|{snapshot.observed_at_ms}".encode("utf-8")
    ).hexdigest()[:24]
    return BoundWindowTarget(
        target_ref=intent.target_ref,
        window=window,
        source_monitor_id=source.monitor_id,
        binding_evidence_ref=f"evidence://spatial-window-binding/{fingerprint}",
    )


def execute_bound_window_move(
    *,
    intent: SpatialFusionIntent,
    bound: BoundWindowTarget,
    backend: WindowInventoryProvider,
) -> WindowMoveReceipt:
    if intent.target_ref != bound.target_ref:
        raise ValueError("spatial_target_binding_intent_mismatch")
    if intent.command is SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT:
        direction = MonitorDirection.RIGHT
    elif intent.command is SpatialFusionCommand.MOVE_FOCUSED_WINDOW_LEFT:
        direction = MonitorDirection.LEFT
    else:
        raise ValueError("spatial_target_command_not_movable")
    monitors = backend.monitors()
    source = _source_monitor(bound.window, monitors)
    if source.monitor_id != bound.source_monitor_id:
        raise ValueError("spatial_target_monitor_topology_drift")
    target = _adjacent(source, monitors, direction)
    after = _project(bound.window, source, target)
    backend.move_window(bound.window.window_ref, after, restore_maximized=bound.window.maximized)
    return WindowMoveReceipt(
        window_ref=bound.window.window_ref,
        direction=direction,
        source_monitor_id=source.monitor_id,
        target_monitor_id=target.monitor_id,
        before_rect=bound.window.rect,
        after_rect=after,
        was_maximized=bound.window.maximized,
        completed=True,
    )


def _opaque_ref(prefix: str, native_id: int) -> str:
    return f"{prefix}:{hashlib.sha256(str(native_id).encode()).hexdigest()[:24]}"


class WindowsNativeTargetBackend:
    """Visible top-level window inventory + movement using Win32 only."""

    SW_RESTORE = 9
    SW_MAXIMIZE = 3
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    MONITORINFOF_PRIMARY = 0x00000001

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("windows_spatial_target_backend_requires_windows")
        self._user32 = ctypes.windll.user32
        self._handles: dict[str, int] = {}

        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_TargetWinRect)]
        self._user32.GetWindowRect.restype = wintypes.BOOL
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.IsWindowVisible.restype = wintypes.BOOL
        self._user32.IsZoomed.argtypes = [wintypes.HWND]
        self._user32.IsZoomed.restype = wintypes.BOOL
        self._user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_TargetWinMonitorInfo)]
        self._user32.GetMonitorInfoW.restype = wintypes.BOOL
        self._user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self._user32.SetWindowPos.restype = wintypes.BOOL
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL

    @staticmethod
    def _rect(value: _TargetWinRect) -> DesktopRect:
        return DesktopRect(left=value.left, top=value.top, right=value.right, bottom=value.bottom)

    def windows(self) -> tuple[WindowGeometry, ...]:
        found: list[WindowGeometry] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if not self._user32.IsWindowVisible(hwnd):
                return True
            rect = _TargetWinRect()
            if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return True
            handle = int(ctypes.cast(hwnd, ctypes.c_void_p).value or 0)
            if not handle:
                return True
            ref = _opaque_ref("window", handle)
            self._handles[ref] = handle
            found.append(
                WindowGeometry(
                    window_ref=ref,
                    rect=self._rect(rect),
                    maximized=bool(self._user32.IsZoomed(hwnd)),
                )
            )
            return True

        callback_ref = callback_type(callback)
        self._user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self._user32.EnumWindows.restype = wintypes.BOOL
        if not self._user32.EnumWindows(callback_ref, 0):
            raise RuntimeError("windows_enum_windows_failed")
        return tuple(found)

    def monitors(self) -> tuple[MonitorGeometry, ...]:
        found: list[MonitorGeometry] = []
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(_TargetWinRect),
            wintypes.LPARAM,
        )

        def callback(hmonitor, _hdc, _rect, _data):
            info = _TargetWinMonitorInfo()
            info.cbSize = ctypes.sizeof(_TargetWinMonitorInfo)
            if not self._user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                return 1
            handle = int(ctypes.cast(hmonitor, ctypes.c_void_p).value or 0)
            found.append(
                MonitorGeometry(
                    monitor_id=_opaque_ref("monitor", handle),
                    bounds=self._rect(info.rcMonitor),
                    work_area=self._rect(info.rcWork),
                    primary=bool(info.dwFlags & self.MONITORINFOF_PRIMARY),
                )
            )
            return 1

        callback_ref = callback_type(callback)
        self._user32.EnumDisplayMonitors.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(_TargetWinRect),
            callback_type,
            wintypes.LPARAM,
        ]
        self._user32.EnumDisplayMonitors.restype = wintypes.BOOL
        if not self._user32.EnumDisplayMonitors(0, None, callback_ref, 0):
            raise RuntimeError("windows_enum_display_monitors_failed")
        return tuple(found)

    def move_window(self, window_ref: str, rect: DesktopRect, *, restore_maximized: bool) -> None:
        hwnd = self._handles.get(window_ref)
        if hwnd is None:
            raise KeyError("windows_spatial_target_ref_unknown")
        hwnd_value = wintypes.HWND(hwnd)
        if restore_maximized:
            self._user32.ShowWindow(hwnd_value, self.SW_RESTORE)
        flags = self.SWP_NOZORDER | self.SWP_NOACTIVATE
        if not self._user32.SetWindowPos(
            hwnd_value,
            0,
            rect.left,
            rect.top,
            rect.width,
            rect.height,
            flags,
        ):
            raise RuntimeError("windows_spatial_target_move_failed")
        if restore_maximized:
            self._user32.ShowWindow(hwnd_value, self.SW_MAXIMIZE)
