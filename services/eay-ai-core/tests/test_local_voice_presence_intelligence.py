from datetime import datetime, timedelta, timezone

import pytest

from app.local_model_pool import LocalModelSelection
from app.local_voice_presence import (
    LocalIdentitySource,
    TrustedLocalVoiceIdentity,
    WakeGatedVoiceController,
    WakePolicy,
)
from app.local_voice_recognizer import LocalRecognitionReceipt
from app.local_voice_runtime import TransientTranscript
from app.voice_session import VoiceSessionState, new_voice_session

NOW = datetime(2026, 8, 18, 13, 20, tzinfo=timezone.utc)
SECRET_COMMAND = "Jarvis, Bunu sağ ekrana at!"


def _selection():
    return LocalModelSelection(
        task_ref="voice-recognizer:voice:wake",
        deployment_id="deployment:qwen3-asr",
        model_family="qwen3-asr",
        model_id="Qwen3-ASR-0.6B",
        benchmark_score=0.93,
        local_execution_available=True,
        paid_frontier_escalation_required=False,
    )


def _turn(text, *, ref="transcript://local-wake-gated/1", final=True):
    transcript = TransientTranscript(
        text=text,
        transcript_ref=ref,
        language_code="tr",
        confidence=0.97,
        final=final,
    )
    recognition = LocalRecognitionReceipt(
        voice_session_id="voice:wake",
        sequence=1,
        asr_selection=_selection(),
        transcript_ref=ref,
        language_code="tr",
        confidence=0.97,
        final=final,
        backend_evidence_ref="evidence://local-asr/qwen3/tr-v1",
    )
    return transcript, recognition


def _identity(**updates):
    payload = dict(
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://oidc/erdi-session-1",
        local_device_ref="device://erdi-laptop",
        source=LocalIdentitySource.CORPORATE_OIDC,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=2),
    )
    payload.update(updates)
    return TrustedLocalVoiceIdentity(**payload)


def _controller():
    return WakeGatedVoiceController(
        session=new_voice_session("voice:wake"),
        policy=WakePolicy(wake_aliases=("jarvis",), conversational_window_seconds=60),
        command_hmac_key=b"p" * 32,
    )


def test_sleeping_final_without_wake_never_reaches_final_voice_event():
    controller = _controller()
    transcript, recognition = _turn("Bunu sağ ekrana at")
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is None
    assert receipt.command_eligible is False
    assert "local_voice_presence_wake_required" in receipt.blockers
    assert receipt.voice_event_ids == ()
    assert controller.session.state is VoiceSessionState.IDLE


def test_wake_only_opens_conversation_window_but_grants_no_command_authority():
    controller = _controller()
    transcript, recognition = _turn("Jarvis")
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is None
    assert receipt.wake_detected is True
    assert receipt.awake is True
    assert receipt.command_eligible is False
    assert receipt.wake_word_authority is False
    assert len(receipt.voice_event_ids) == 1
    assert controller.session.state is VoiceSessionState.LISTENING


def test_wake_plus_command_creates_verified_final_intent_after_wake():
    controller = _controller()
    transcript, recognition = _turn(SECRET_COMMAND)
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is not None
    assert command.text == "bunu sağ ekrana at"
    assert receipt.command_eligible is True
    assert receipt.command_ref == command.command_ref
    assert len(receipt.voice_event_ids) == 2
    assert controller.session.state is VoiceSessionState.THINKING
    serialized = receipt.model_dump_json()
    assert SECRET_COMMAND not in serialized
    assert receipt.biometric_voice_identity_used is False


def test_follow_up_inside_window_does_not_require_repeating_wake_word():
    controller = _controller()
    first, first_receipt = _turn("Jarvis", ref="transcript://local-wake-gated/a")
    controller.consume(
        transcript=first,
        recognition=first_receipt,
        identity=_identity(),
        occurred_at=NOW,
    )
    follow, follow_receipt = _turn(
        "Bir de KPI panelini aç",
        ref="transcript://local-wake-gated/b",
    )
    command, receipt = controller.consume(
        transcript=follow,
        recognition=follow_receipt,
        identity=_identity(),
        occurred_at=NOW + timedelta(seconds=20),
    )
    assert command is not None
    assert command.text == "Bir de KPI panelini aç"
    assert receipt.command_eligible is True
    assert receipt.wake_detected is False


def test_expired_window_requires_wake_again():
    controller = _controller()
    first, first_receipt = _turn("Jarvis", ref="transcript://local-wake-gated/a")
    controller.consume(
        transcript=first,
        recognition=first_receipt,
        identity=_identity(),
        occurred_at=NOW,
    )
    later, later_receipt = _turn("KPI panelini aç", ref="transcript://local-wake-gated/c")
    command, receipt = controller.consume(
        transcript=later,
        recognition=later_receipt,
        identity=_identity(),
        occurred_at=NOW + timedelta(seconds=61),
    )
    assert command is None
    assert "local_voice_presence_wake_required" in receipt.blockers


def test_identity_evidence_change_closes_awake_window():
    controller = _controller()
    first, first_receipt = _turn("Jarvis", ref="transcript://local-wake-gated/a")
    controller.consume(
        transcript=first,
        recognition=first_receipt,
        identity=_identity(),
        occurred_at=NOW,
    )
    follow, follow_receipt = _turn("Devam et", ref="transcript://local-wake-gated/d")
    command, receipt = controller.consume(
        transcript=follow,
        recognition=follow_receipt,
        identity=_identity(identity_evidence_ref="identity://oidc/other-session"),
        occurred_at=NOW + timedelta(seconds=10),
    )
    assert command is None
    assert receipt.awake is False
    assert "local_voice_presence_identity_changed_during_window" in receipt.blockers


def test_expired_identity_and_voice_biometric_identity_fail_closed():
    controller = _controller()
    transcript, recognition = _turn(SECRET_COMMAND)
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(expires_at=NOW - timedelta(seconds=1)),
        occurred_at=NOW,
    )
    assert command is None
    assert "local_voice_presence_trusted_identity_expired" in receipt.blockers

    with pytest.raises(ValueError, match="does_not_use_voice_biometrics"):
        _identity(biometric_voice_identity_used=True)


def test_partial_transcript_is_never_wake_or_command_eligible():
    controller = _controller()
    transcript, recognition = _turn("Jarvis bunu", final=False)
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is None
    assert receipt.final is False
    assert receipt.command_eligible is False
    assert "partial_not_command_eligible" in receipt.blockers[0]
