from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.local_model_pool import (
    LocalCapability,
    LocalModelDeployment,
    load_local_model_catalog,
)
from app.local_voice_privacy_runtime import HardenedLocalVoiceRuntime
from app.local_voice_runtime import (
    LocalAsrResult,
    LocalPlaybackHandle,
    LocalSpeechReceipt,
    LocalTtsResult,
    LocalVoicePolicy,
    TransientAudioFrame,
    TransientSpeechAudio,
)
from app.voice_session import VoiceSessionState, new_voice_session

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"
NOW = datetime(2026, 8, 18, 12, 30, tzinfo=timezone.utc)
SECRET_UTTERANCE = "Jarvis bunu sağ ekrana at"
SECRET_REPLY = "Elbette, pencereyi taşıyorum"


def _deployment(family, model_id, score, capabilities):
    return LocalModelDeployment(
        deployment_id=f"deployment:{family}",
        model_family=family,
        model_id=model_id,
        runtime="LOCAL",
        endpoint_ref=f"runtime://local/{family}",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"benchmark://voice/{family}/tr-v1",
        observed_capabilities=frozenset(capabilities),
        hardware_profile_ref="hardware://voice-lab-1",
    )


ASR = _deployment(
    "qwen3-asr",
    "Qwen3-ASR-0.6B",
    0.92,
    {LocalCapability.AUDIO, LocalCapability.ASR, LocalCapability.MULTILINGUAL},
)
TTS = _deployment(
    "chatterbox-multilingual-v3",
    "ResembleAI/Chatterbox-Multilingual-v3",
    0.90,
    {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL},
)


class _Asr:
    def __init__(self, *, final):
        self.final = final
        self.calls = 0

    def transcribe(self, audio, *, language_code):
        self.calls += 1
        assert language_code == "tr"
        return SECRET_UTTERANCE, LocalAsrResult(
            language_code="tr",
            confidence=0.97,
            final=self.final,
            backend_evidence_ref="evidence://local-asr/qwen3/tr-v1",
        )


class _Tts:
    def __init__(self):
        self.calls = 0

    def synthesize(self, text, *, language_code):
        self.calls += 1
        assert text == SECRET_REPLY
        assert language_code == "tr"
        return TransientSpeechAudio(pcm16=b"\x01\x00" * 160, sample_rate_hz=24000), LocalTtsResult(
            language_code="tr",
            backend_evidence_ref="evidence://local-tts/chatterbox/tr-v1",
        )


class _Playback:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    def start(self, audio, *, started_at):
        self.starts += 1
        return LocalPlaybackHandle(
            playback_ref=f"playback:{self.starts}",
            started_at=started_at,
            local_device_ref="device://local-speaker",
            active=True,
        )

    def stop(self, playback_ref):
        self.stops += 1
        return LocalPlaybackHandle(
            playback_ref=playback_ref,
            started_at=NOW,
            local_device_ref="device://local-speaker",
            active=False,
        )


def _runtime(*, asr_final=True, hmac_key=None, deployments=(ASR, TTS)):
    playback = _Playback()
    runtime = HardenedLocalVoiceRuntime(
        policy=LocalVoicePolicy(
            voice_session_id="voice:1",
            principal_ref="principal:erdi",
            identity_evidence_ref="identity://erdi/1",
            language_code="tr",
        ),
        session=new_voice_session("voice:1"),
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=deployments,
        asr_backends={"deployment:qwen3-asr": _Asr(final=asr_final)},
        tts_backends={"deployment:chatterbox-multilingual-v3": _Tts()},
        playback=playback,
        transcript_hmac_key=hmac_key,
    )
    return runtime, playback


def _audio(sequence, *, final_chunk):
    return TransientAudioFrame(
        pcm16=b"\x01\x00" * 320,
        captured_at=NOW + timedelta(milliseconds=sequence),
        sequence=sequence,
        final_chunk=final_chunk,
    )


def test_partial_asr_never_creates_intent_even_with_identity_available():
    runtime, _ = _runtime(asr_final=False)
    transient, receipt = runtime.transcribe(_audio(1, final_chunk=False), identity_verified=True)
    assert transient.final is False
    assert receipt.final is False
    assert receipt.intent_eligible is False
    assert runtime.session.state is VoiceSessionState.LISTENING


def test_final_without_verified_identity_is_not_intent_eligible():
    runtime, _ = _runtime()
    _, receipt = runtime.transcribe(_audio(2, final_chunk=True), identity_verified=False)
    assert receipt.final is True
    assert receipt.intent_eligible is False
    assert runtime.session.state is VoiceSessionState.LISTENING


def test_verified_final_utterance_becomes_intent_eligible_without_persisting_content():
    runtime, _ = _runtime()
    transient, receipt = runtime.transcribe(_audio(3, final_chunk=True), identity_verified=True)
    assert transient.text == SECRET_UTTERANCE
    assert receipt.intent_eligible is True
    assert runtime.session.state is VoiceSessionState.THINKING
    serialized = receipt.model_dump_json()
    assert SECRET_UTTERANCE not in serialized
    assert "0100" * 4 not in serialized
    assert receipt.raw_audio_retained is False
    assert receipt.transcript_text_retained is False
    assert receipt.paid_frontier_used is False


def test_ephemeral_hmac_makes_same_utterance_unlinkable_across_runtime_instances():
    first, _ = _runtime(hmac_key=b"a" * 32)
    second, _ = _runtime(hmac_key=b"b" * 32)
    _, first_receipt = first.transcribe(_audio(4, final_chunk=True), identity_verified=True)
    _, second_receipt = second.transcribe(_audio(4, final_chunk=True), identity_verified=True)
    assert first_receipt.transcript_ref != second_receipt.transcript_ref
    assert first_receipt.transcript_ref.startswith("transcript://local-hmac/")
    with pytest.raises(PermissionError, match="ephemeral_secret_export_forbidden"):
        first.export_secret_state()


def test_duplicate_audio_sequence_is_rejected():
    runtime, _ = _runtime()
    runtime.transcribe(_audio(5, final_chunk=False), identity_verified=False)
    with pytest.raises(ValueError, match="sequence_duplicate"):
        runtime.transcribe(_audio(5, final_chunk=False), identity_verified=False)


def test_turkish_speech_uses_local_tts_and_barge_in_stops_playback_first():
    runtime, playback = _runtime()
    speech = runtime.speak(SECRET_REPLY, started_at=NOW)
    assert isinstance(speech, LocalSpeechReceipt)
    assert speech.tts_selection.model_family == "chatterbox-multilingual-v3"
    assert speech.paid_frontier_used is False
    serialized = speech.model_dump_json()
    assert SECRET_REPLY not in serialized
    assert runtime.session.state is VoiceSessionState.SPEAKING

    barge = runtime.barge_in(occurred_at=NOW + timedelta(milliseconds=100))
    assert playback.stops == 1
    assert barge.playback_stopped is True
    assert barge.voice_transition.assistant_speech_cancel_requested is True
    assert runtime.session.state is VoiceSessionState.LISTENING


def test_missing_verified_local_asr_or_tts_fails_instead_of_spending_frontier_tokens():
    runtime, _ = _runtime(deployments=(TTS,))
    with pytest.raises(RuntimeError, match="verified_asr_unavailable"):
        runtime.transcribe(_audio(6, final_chunk=True), identity_verified=True)

    runtime, _ = _runtime(deployments=(ASR,))
    with pytest.raises(RuntimeError, match="verified_tts_unavailable"):
        runtime.speak(SECRET_REPLY, started_at=NOW)
