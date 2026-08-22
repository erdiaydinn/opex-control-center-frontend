"""Compose governed spatial gesture intents with local desktop window control.

This is deliberately limited to reversible local UI actions. A hand gesture can
move the currently focused window between monitors, but it cannot authorize a
portal/API/business mutation, send messages, approve finance, or submit forms.
A CANCEL gesture is observable but performs no OS window movement.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .desktop_window_runtime import (
    DesktopWindowBackend,
    MonitorDirection,
    WindowMoveReceipt,
    move_active_window_to_adjacent_monitor,
)
from .spatial_interaction import (
    SPATIAL_INTERACTION_CONTRACT,
    SpatialControlSession,
    SpatialGestureCommand,
    SpatialGestureIntent,
)

SPATIAL_WINDOW_CONTROL_CONTRACT = "eay-spatial-window-control-v1"


class SpatialWindowControlReceipt(BaseModel):
    contract: str = SPATIAL_WINDOW_CONTROL_CONTRACT
    session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    gesture_evidence_ref: str = Field(min_length=1)
    command: SpatialGestureCommand
    move: WindowMoveReceipt | None = None
    cancelled: bool = False
    local_ui_side_effect_only: bool = True
    business_side_effects_authorized: bool = False
    raw_hand_data_retained: bool = False

    @model_validator(mode="after")
    def receipt_preserves_spatial_boundary(self) -> "SpatialWindowControlReceipt":
        if self.command is SpatialGestureCommand.CANCEL:
            if self.move is not None or not self.cancelled:
                raise ValueError("spatial_window_cancel_must_not_move_window")
        elif self.move is None or self.cancelled:
            raise ValueError("spatial_window_move_command_requires_move_receipt")
        if not self.local_ui_side_effect_only:
            raise ValueError("spatial_window_control_must_remain_local_ui_only")
        if self.business_side_effects_authorized:
            raise ValueError("spatial_window_control_never_authorizes_business_side_effects")
        if self.raw_hand_data_retained:
            raise ValueError("spatial_window_control_cannot_retain_raw_hand_data")
        return self


def execute_spatial_window_intent(
    *,
    session: SpatialControlSession,
    intent: SpatialGestureIntent,
    backend: DesktopWindowBackend,
) -> SpatialWindowControlReceipt:
    if intent.contract != SPATIAL_INTERACTION_CONTRACT:
        raise ValueError("spatial_intent_contract_mismatch")
    if intent.session_id != session.session_id:
        raise ValueError("spatial_intent_session_mismatch")
    if intent.principal_ref != session.principal_ref:
        raise ValueError("spatial_intent_principal_mismatch")
    if intent.command not in session.allowed_commands:
        raise ValueError("spatial_intent_command_not_allowed")
    if intent.emitted_at < session.armed_at or intent.emitted_at > session.expires_at:
        raise ValueError("spatial_intent_outside_session_window")

    if intent.command is SpatialGestureCommand.CANCEL:
        return SpatialWindowControlReceipt(
            session_id=session.session_id,
            principal_ref=session.principal_ref,
            gesture_evidence_ref=intent.source_evidence_ref,
            command=intent.command,
            move=None,
            cancelled=True,
        )

    if intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT:
        direction = MonitorDirection.RIGHT
    elif intent.command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_LEFT:
        direction = MonitorDirection.LEFT
    else:  # pragma: no cover - enum exhaustiveness after CANCEL branch
        raise ValueError("spatial_window_command_unsupported")

    move = move_active_window_to_adjacent_monitor(backend=backend, direction=direction)
    return SpatialWindowControlReceipt(
        session_id=session.session_id,
        principal_ref=session.principal_ref,
        gesture_evidence_ref=intent.source_evidence_ref,
        command=intent.command,
        move=move,
        cancelled=False,
    )
