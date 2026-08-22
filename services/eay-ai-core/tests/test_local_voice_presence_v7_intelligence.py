from datetime import datetime, timedelta, timezone

from app.local_model_pool import LocalModelSelection
from app.local_voice_presence import LocalIdentitySource, TrustedLocalVoiceIdentity, WakePolicy
from app.local_voice_presence_v7 import (
    PreservingWakeGatedVoiceController,
    _split_wake_prefix_preserving_text,
)
from app.local_voice_recognizer import LocalRecognitionReceipt
from app.local_voice_runtime import TransientTranscript
from app.voice_session import VoiceSessionState, new_voice_session

NOW = datetime(2026, 8, 18, 13, 30, tzinfo=timezone.utc)
COMMAND = "Jarvis, Fulya'daki ÇarşıPortal Order ID TR-ABC-009'u aç!"
REMAINDER = "Fulya'daki ÇarşıPortal Order ID TR-ABC-009'u aç!"


def _selection():
    return LocalModelSelection(
        task_ref="voice-recognizer:voice:v7",
        deployment_id="deployment:qwen3-asr",
        model_family="qwen3-asr",
        model_id="Qwen3-ASR-0.6B",
        benchmark_score=0.93,
        local_execution_available=True,
        paid_frontier_escalation_required=False,
    )


def _turn(text, ref="transcript://local-wake-gated/v7"):
    transcript = TransientTranscript(
        text=text,
        transcript_ref=ref,
        language_code="tr",
        confidence=0.98,
        final=True,
    )
    recognition = LocalRecognitionReceipt(
        voice_session_id="voice:v7",
        sequence=1,
        asr_selection=_selection(),
        transcript_ref=ref,
        language_code="tr",
        confidence=0.98,
        final=True,
        backend_evidence_ref="evidence://local-asr/qwen3/tr-v1",
    )
    return transcript, recognition


def _identity():
    return TrustedLocalVoiceIdentity(
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://oidc/erdi-v7",
        local_device_ref="device://erdi-laptop",
        source=LocalIdentitySource.CORPORATE_OIDC,
        authenticated_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=2),
    )


def test_wake_split_preserves_original_turkish_entity_casing_ids_and_punctuation():
    detected, remainder = _split_wake_prefix_preserving_text(COMMAND, ("jarvis",))
    assert detected is True
    assert remainder == REMAINDER
    assert "ÇarşıPortal" in remainder
    assert "TR-ABC-009" in remainder
    assert remainder.endswith("!")


def test_wake_plus_command_keeps_exact_transient_remainder_but_receipt_is_content_free():
    controller = PreservingWakeGatedVoiceController(
        session=new_voice_session("voice:v7"),
        policy=WakePolicy(wake_aliases=("jarvis",), conversational_window_seconds=60),
        command_hmac_key=b"v" * 32,
    )
    transcript, recognition = _turn(COMMAND)
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is not None
    assert command.text == REMAINDER
    assert receipt.wake_detected is True
    assert receipt.command_eligible is True
    assert len(receipt.voice_event_ids) == 2
    assert controller.session.state is VoiceSessionState.THINKING
    serialized = receipt.model_dump_json()
    assert COMMAND not in serialized
    assert REMAINDER not in serialized
    assert "TR-ABC-009" not in serialized


def test_wake_only_and_wake_less_sleeping_behavior_remain_v5_safe():
    controller = PreservingWakeGatedVoiceController(
        session=new_voice_session("voice:v7"),
        policy=WakePolicy(wake_aliases=("jarvis",), conversational_window_seconds=60),
        command_hmac_key=b"v" * 32,
    )
    transcript, recognition = _turn("Jarvis")
    command, receipt = controller.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is None
    assert receipt.awake is True
    assert receipt.wake_detected is True

    second = PreservingWakeGatedVoiceController(
        session=new_voice_session("voice:v7"),
        policy=WakePolicy(wake_aliases=("jarvis",)),
        command_hmac_key=b"w" * 32,
    )
    transcript, recognition = _turn("Fulya'daki ÇarşıPortal'ı aç", ref="transcript://local-wake-gated/v7b")
    command, receipt = second.consume(
        transcript=transcript,
        recognition=recognition,
        identity=_identity(),
        occurred_at=NOW,
    )
    assert command is None
    assert "local_voice_presence_wake_required" in receipt.blockers
    assert receipt.voice_event_ids == ()
