"""Native, feedback-only overlay renderer for Jarvis Spatial HUD.

The overlay renders compact ``hud.*`` cues from ``SpatialHudSnapshot``. It does
not read application content, capture keyboard/mouse input, accept clicks, or
become an authorization surface. The Windows implementation uses a topmost,
layered, transparent, no-activate built-in STATIC window and therefore does not
require an extra GUI framework.
"""

from __future__ import annotations

import ctypes
import platform
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .spatial_hud import HudPhase, SpatialHudSnapshot

SPATIAL_HUD_OVERLAY_CONTRACT = "eay-spatial-hud-overlay-v1"


class HudOverlayFrame(BaseModel):
    contract: str = SPATIAL_HUD_OVERLAY_CONTRACT
    phase: HudPhase
    cue: str = Field(pattern=r"^hud\.[a-z_]+$")
    confidence_percent: int | None = Field(default=None, ge=0, le=100)
    target_present: bool = False
    blocker_present: bool = False
    click_through_required: bool = True
    activation_forbidden: bool = True
    application_content_retained: bool = False
    raw_sensor_data_retained: bool = False
    action_execution_authorized: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def frame_is_feedback_only(self) -> "HudOverlayFrame":
        if not self.click_through_required or not self.activation_forbidden:
            raise ValueError("spatial_hud_overlay_must_be_click_through_no_activate")
        if self.application_content_retained or self.raw_sensor_data_retained:
            raise ValueError("spatial_hud_overlay_cannot_retain_content")
        if self.action_execution_authorized or self.business_side_effects_authorized:
            raise ValueError("spatial_hud_overlay_never_authorizes_actions")
        return self


class HudOverlayReceipt(BaseModel):
    contract: str = SPATIAL_HUD_OVERLAY_CONTRACT
    phase: HudPhase
    rendered: bool
    visible: bool
    click_through: bool = True
    no_activate: bool = True
    application_content_retained: bool = False
    input_captured: bool = False

    @model_validator(mode="after")
    def receipt_preserves_input_boundary(self) -> "HudOverlayReceipt":
        if not self.click_through or not self.no_activate or self.input_captured:
            raise ValueError("spatial_hud_overlay_input_boundary_violation")
        if self.application_content_retained:
            raise ValueError("spatial_hud_overlay_receipt_cannot_retain_content")
        return self


class HudOverlayBackend(Protocol):
    def render(self, frame: HudOverlayFrame) -> HudOverlayReceipt: ...
    def hide(self) -> HudOverlayReceipt: ...
    def close(self) -> None: ...


def frame_from_snapshot(snapshot: SpatialHudSnapshot) -> HudOverlayFrame:
    confidence = None
    if snapshot.confidence is not None:
        confidence = round(snapshot.confidence * 100)
    return HudOverlayFrame(
        phase=snapshot.phase,
        cue=snapshot.cue,
        confidence_percent=confidence,
        target_present=snapshot.target_ref is not None,
        blocker_present=bool(snapshot.blockers),
    )


def _safe_text(frame: HudOverlayFrame) -> str:
    # Never include target refs, application titles, transcripts or blocker text.
    suffix = f"  {frame.confidence_percent}%" if frame.confidence_percent is not None else ""
    return f"JARVIS  ·  {frame.cue.upper()}{suffix}"


@dataclass
class HudOverlayController:
    backend: HudOverlayBackend

    def present(self, snapshot: SpatialHudSnapshot) -> HudOverlayReceipt:
        frame = frame_from_snapshot(snapshot)
        if snapshot.phase is HudPhase.IDLE:
            return self.backend.hide()
        return self.backend.render(frame)

    def close(self) -> None:
        self.backend.close()


class WindowsHudOverlayRenderer:
    """Minimal Win32 overlay using the built-in STATIC control class."""

    WS_POPUP = 0x80000000
    WS_VISIBLE = 0x10000000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_LAYERED = 0x00080000
    WS_EX_NOACTIVATE = 0x08000000
    LWA_ALPHA = 0x00000002
    SW_HIDE = 0
    SW_SHOWNOACTIVATE = 4
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    HWND_TOPMOST = -1

    def __init__(self, *, left: int = 32, top: int = 32, width: int = 460, height: int = 54) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("windows_hud_overlay_requires_windows")
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._closed = False
        self._visible = False

        self._user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        self._user32.CreateWindowExW.restype = wintypes.HWND
        self._user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
        self._user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
        self._user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        self._user32.SetWindowTextW.restype = wintypes.BOOL
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wintypes.BOOL
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
        self._user32.DestroyWindow.argtypes = [wintypes.HWND]
        self._user32.DestroyWindow.restype = wintypes.BOOL
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

        ex_style = (
            self.WS_EX_TOPMOST
            | self.WS_EX_TRANSPARENT
            | self.WS_EX_TOOLWINDOW
            | self.WS_EX_LAYERED
            | self.WS_EX_NOACTIVATE
        )
        instance = self._kernel32.GetModuleHandleW(None)
        hwnd = self._user32.CreateWindowExW(
            ex_style,
            "STATIC",
            "JARVIS",
            self.WS_POPUP,
            left,
            top,
            width,
            height,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            raise RuntimeError("windows_hud_overlay_create_failed")
        self._hwnd = hwnd
        if not self._user32.SetLayeredWindowAttributes(hwnd, 0, 220, self.LWA_ALPHA):
            self.close()
            raise RuntimeError("windows_hud_overlay_layered_attributes_failed")
        self._user32.SetWindowPos(
            hwnd,
            wintypes.HWND(self.HWND_TOPMOST),
            0,
            0,
            0,
            0,
            self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("windows_hud_overlay_closed")

    def render(self, frame: HudOverlayFrame) -> HudOverlayReceipt:
        self._ensure_open()
        if not self._user32.SetWindowTextW(self._hwnd, _safe_text(frame)):
            raise RuntimeError("windows_hud_overlay_text_failed")
        self._user32.ShowWindow(self._hwnd, self.SW_SHOWNOACTIVATE)
        self._visible = True
        return HudOverlayReceipt(
            phase=frame.phase,
            rendered=True,
            visible=True,
        )

    def hide(self) -> HudOverlayReceipt:
        self._ensure_open()
        self._user32.ShowWindow(self._hwnd, self.SW_HIDE)
        self._visible = False
        return HudOverlayReceipt(
            phase=HudPhase.IDLE,
            rendered=True,
            visible=False,
        )

    def close(self) -> None:
        if self._closed:
            return
        hwnd = getattr(self, "_hwnd", None)
        if hwnd:
            self._user32.DestroyWindow(hwnd)
        self._closed = True
        self._visible = False
