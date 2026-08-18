from datetime import datetime, timedelta, timezone

import pytest

from app.spatial_gaze import GazeFocusIntent
from app.spatial_interaction import Handedness, SpatialGestureCommand, SpatialGestureIntent
from app.spatial_multimodal_fusion import (
    SpatialFusionCommand,
    SpatialFusionSession,
    SpatialModality,
    fuse_spatial_modalities,
    voice_event_to_spatial_command,
)
from app.voice_session import VoiceEvent, VoiceEventKind

NOW = datetime(2026, 8, 18, 10, 50, tzinfo=timezone.utc)


def _session(**updates):
    payload = dict(
        spatial_session_id="spatial:1",
        voice_session_id="voice:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/session-1",
        armed_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(minutes=10),
        max_temporal_skew_ms=1200,
    )
    payload.update(updates)
    return SpatialFusionSession(**payload)


def _voice_event(*, at=NOW, kind=VoiceEventKind.FINAL_UTTERANCE, verified=True, **updates):
    payload = dict(
        event_id="voice-event:1",
        session_id="voice:1",
        occurred_at=at,
        kind=kind,
        principal_ref="principal:erdi",
        transcript_ref="transcript://voice/1",
        identity_verified=verified,
        identity_evidence_ref="identity://erdi/session-1" if verified else None,
    )
    payload.update(updates)
    return VoiceEvent(**payload)


def _voice(command=SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT, *, at=NOW, **event_updates):
    return voice_event_to_spatial_command(
        event=_voice_event(at=at, **event_updates),
        spatial_session_id="spatial:1",
        command=command,
    )


def _gaze(*, at=NOW + timedelta(milliseconds=200), **updates):
    payload = dict(
        spatial_session_id="spatial:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/session-1",
        target_ref="window://planogram-3d",
        focused_at=at,
        confidence=0.92,
        source_evidence_ref="evidence://gaze/focus-1",
        dwell_ms=360,
    )
    payload.update(updates)
    return GazeFocusIntent(**payload)


def _gesture(command=SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT, *, at=NOW + timedelta(milliseconds=250), **updates):
    payload = dict(
        session_id="spatial:1",
        principal_ref="principal:erdi",
        command=command,
        emitted_at=at,
        handedness=Handedness.RIGHT,
        confidence=0.94,
        horizontal_displacement=0.22 if command is SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT else -0.22,
        source_evidence_ref="evidence://gesture/1",
    )
    payload.update(updates)
    return SpatialGestureIntent(**payload)


def test_only_verified_final_voice_event_can_become_structured_spatial_command():
    command = _voice()
    assert command.command is SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT
    assert command.raw_transcript_retained is False
    assert command.business_side_effects_authorized is False
    assert "transcript://voice/1" in command.model_dump_json()

    with pytest.raises(ValueError, match="voice_event_not_intent_eligible"):
        voice_event_to_spatial_command(
            event=_voice_event(kind=VoiceEventKind.PARTIAL_UTTERANCE),
            spatial_session_id="spatial:1",
            command=SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT,
        )
    with pytest.raises(ValueError, match="voice_event_not_intent_eligible"):
        voice_event_to_spatial_command(
            event=_voice_event(verified=False),
            spatial_session_id="spatial:1",
            command=SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT,
        )


def test_verified_voice_plus_stable_gaze_emits_local_non_executable_move_intent():
    decision = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(),
        gaze=_gaze(),
    )
    assert decision.blockers == ()
    assert decision.intent is not None
    intent = decision.intent
    assert intent.command is SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT
    assert intent.target_ref == "window://planogram-3d"
    assert intent.modalities == (SpatialModality.VOICE, SpatialModality.GAZE)
    assert intent.local_ui_only is True
    assert intent.target_binding_required_before_execution is True
    assert intent.click_authorized is False
    assert intent.business_side_effects_authorized is False
    assert decision.action_execution_authorized is False


def test_gaze_alone_never_becomes_action_and_move_without_gaze_is_blocked():
    gaze_only = fuse_spatial_modalities(session=_session(), gaze=_gaze())
    assert gaze_only.intent is None
    assert "spatial_fusion_move_requires_voice_or_gesture" in gaze_only.blockers

    voice_only = fuse_spatial_modalities(session=_session(), voice=_voice())
    assert voice_only.intent is None
    assert "spatial_fusion_move_requires_gaze_focus" in voice_only.blockers


def test_three_modalities_must_agree_on_direction():
    agreeing = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(SpatialFusionCommand.MOVE_FOCUSED_WINDOW_RIGHT),
        gaze=_gaze(),
        gesture=_gesture(SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT),
    )
    assert agreeing.intent is not None
    assert set(agreeing.intent.modalities) == {
        SpatialModality.VOICE,
        SpatialModality.GAZE,
        SpatialModality.GESTURE,
    }

    conflict = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(SpatialFusionCommand.MOVE_FOCUSED_WINDOW_LEFT),
        gaze=_gaze(),
        gesture=_gesture(SpatialGestureCommand.MOVE_ACTIVE_WINDOW_RIGHT),
    )
    assert conflict.intent is None
    assert "spatial_fusion_direction_conflict" in conflict.blockers


def test_identity_session_and_temporal_mismatch_fail_closed():
    bad_identity = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(),
        gaze=_gaze(identity_evidence_ref="identity://other"),
    )
    assert bad_identity.intent is None
    assert "spatial_fusion_gaze_identity_mismatch" in bad_identity.blockers

    bad_session = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(),
        gaze=_gaze(spatial_session_id="spatial:other"),
    )
    assert bad_session.intent is None
    assert "spatial_fusion_gaze_session_mismatch" in bad_session.blockers

    stale = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(at=NOW),
        gaze=_gaze(at=NOW + timedelta(seconds=3)),
    )
    assert stale.intent is None
    assert "spatial_fusion_temporal_skew_exceeded" in stale.blockers


def test_verified_voice_cancel_is_safe_without_gaze_or_execution_authority():
    decision = fuse_spatial_modalities(
        session=_session(),
        voice=_voice(SpatialFusionCommand.CANCEL),
    )
    assert decision.blockers == ()
    assert decision.intent is not None
    assert decision.intent.command is SpatialFusionCommand.CANCEL
    assert decision.intent.target_ref is None
    assert decision.intent.modalities == (SpatialModality.VOICE,)
    assert decision.intent.business_side_effects_authorized is False
    assert decision.action_execution_authorized is False


def test_fusion_session_cannot_be_constructed_as_business_authority():
    with pytest.raises(ValueError, match="never_authorizes_business_side_effects"):
        _session(business_side_effects_authorized=True)
