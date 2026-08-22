from datetime import datetime, timedelta, timezone

import pytest

from app.spatial_hud import (
    HudEventKind,
    HudPhase,
    SpatialHudEvent,
    SpatialHudSession,
    apply_hud_event,
    new_hud_snapshot,
)

NOW = datetime(2026, 8, 18, 11, 30, tzinfo=timezone.utc)


def _session():
    return SpatialHudSession(
        spatial_session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        started_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )


def _event(kind, **updates):
    payload = dict(
        event_id=f"event:{kind.value}",
        spatial_session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        occurred_at=NOW + timedelta(seconds=1),
        kind=kind,
        source_evidence_refs=("evidence://spatial/1",),
    )
    payload.update(updates)
    return SpatialHudEvent(**payload)


def test_hud_focus_ready_execution_is_feedback_only():
    session = _session()
    state = new_hud_snapshot(session)
    state = apply_hud_event(
        session=session,
        snapshot=state,
        event=_event(HudEventKind.GAZE_FOCUS, target_ref="window:opaque", confidence=0.93),
    )
    assert state.phase is HudPhase.FOCUSED
    assert state.target_ref == "window:opaque"
    state = apply_hud_event(
        session=session,
        snapshot=state,
        event=_event(HudEventKind.FUSION_READY, event_id="event:ready"),
    )
    assert state.phase is HudPhase.READY
    assert state.action_execution_authorized is False
    assert state.business_side_effects_authorized is False
    assert state.raw_sensor_data_retained is False


def test_cancel_clears_target_and_never_authorizes_action():
    session = _session()
    state = apply_hud_event(
        session=session,
        snapshot=new_hud_snapshot(session),
        event=_event(HudEventKind.GAZE_FOCUS, target_ref="window:opaque"),
    )
    state = apply_hud_event(
        session=session,
        snapshot=state,
        event=_event(HudEventKind.CANCEL, event_id="event:cancel"),
    )
    assert state.phase is HudPhase.CANCELLED
    assert state.target_ref is None
    assert state.action_execution_authorized is False


def test_hud_wrong_identity_and_duplicate_event_fail_closed():
    session = _session()
    state = new_hud_snapshot(session)
    with pytest.raises(ValueError, match="identity_mismatch"):
        apply_hud_event(
            session=session,
            snapshot=state,
            event=_event(HudEventKind.LISTEN, identity_evidence_ref="identity://other"),
        )
    event = _event(HudEventKind.LISTEN)
    state = apply_hud_event(session=session, snapshot=state, event=event)
    with pytest.raises(ValueError, match="duplicate_event"):
        apply_hud_event(session=session, snapshot=state, event=event)


def test_blocked_hud_retains_only_code_not_raw_sensor_content():
    session = _session()
    state = apply_hud_event(
        session=session,
        snapshot=new_hud_snapshot(session),
        event=_event(
            HudEventKind.BLOCK,
            blocker_code="spatial_fusion_direction_conflict",
        ),
    )
    assert state.phase is HudPhase.BLOCKED
    assert state.blockers == ("spatial_fusion_direction_conflict",)
    serialized = state.model_dump_json()
    assert "camera frame secret" not in serialized
