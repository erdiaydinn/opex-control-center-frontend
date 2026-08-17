from datetime import datetime, timezone

import pytest

from app.voice_session import (
    VoiceEvent,
    VoiceEventKind,
    VoiceSessionState,
    apply_voice_event,
    new_voice_session,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 5, 30, tzinfo=UTC)


def _event(event_id, kind, **overrides):
    payload = dict(
        event_id=event_id,
        session_id="voice-1",
        occurred_at=NOW,
        kind=kind,
    )
    payload.update(overrides)
    return VoiceEvent(**payload)


def test_partial_transcript_never_creates_intent():
    session = new_voice_session("voice-1")
    session, transition = apply_voice_event(
        session,
        _event("partial", VoiceEventKind.PARTIAL_UTTERANCE, transcript_ref="transcript://partial"),
    )

    assert transition.intent_accepted is False
    assert session.state is VoiceSessionState.LISTENING
    assert "voice_partial_transcript_not_intent_eligible" in transition.blockers


def test_verified_final_utterance_becomes_intent():
    session = new_voice_session("voice-1")
    session, transition = apply_voice_event(
        session,
        _event(
            "final",
            VoiceEventKind.FINAL_UTTERANCE,
            principal_ref="principal://erdi",
            transcript_ref="transcript://final",
            identity_verified=True,
            identity_evidence_ref="identity://oidc-session/erdi",
        ),
    )

    assert transition.intent_accepted is True
    assert session.state is VoiceSessionState.THINKING
    assert session.active_principal_ref == "principal://erdi"


def test_verified_identity_boolean_without_evidence_is_rejected():
    with pytest.raises(ValueError, match="voice_verified_identity_requires_evidence"):
        _event(
            "fake-verified",
            VoiceEventKind.FINAL_UTTERANCE,
            principal_ref="principal://erdi",
            transcript_ref="transcript://final",
            identity_verified=True,
        )


def test_barge_in_cancels_assistant_speech_and_returns_to_listening():
    session = new_voice_session("voice-1")
    session, _ = apply_voice_event(session, _event("speak", VoiceEventKind.ASSISTANT_SPEECH_STARTED))
    session, transition = apply_voice_event(session, _event("barge", VoiceEventKind.BARGE_IN))

    assert transition.assistant_speech_cancel_requested is True
    assert session.state is VoiceSessionState.LISTENING


def test_stop_during_execution_halts_but_requires_effect_verification():
    session = new_voice_session("voice-1")
    session, _ = apply_voice_event(
        session,
        _event("execute", VoiceEventKind.EXECUTION_STARTED, mission_ref="mission://stock-adjust"),
    )
    session, transition = apply_voice_event(
        session,
        _event("stop", VoiceEventKind.STOP, side_effect_in_flight=True),
    )

    assert session.state is VoiceSessionState.HALTED
    assert transition.mission_halt_requested is True
    assert transition.effect_verification_required is True
    assert "voice_stop_during_execution_requires_effect_verification" in transition.blockers


def test_continue_is_blocked_until_inflight_effect_is_verified():
    session = new_voice_session("voice-1")
    session, _ = apply_voice_event(
        session,
        _event("execute", VoiceEventKind.EXECUTION_STARTED, mission_ref="mission://stock-adjust"),
    )
    session, _ = apply_voice_event(
        session,
        _event("stop", VoiceEventKind.STOP, side_effect_in_flight=True),
    )
    session, transition = apply_voice_event(session, _event("continue", VoiceEventKind.CONTINUE))

    assert session.state is VoiceSessionState.HALTED
    assert "voice_continue_blocked_pending_effect_verification" in transition.blockers
