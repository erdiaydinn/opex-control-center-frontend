from datetime import datetime, timezone
from pathlib import Path

from app.local_model_pool import LocalCapability, LocalModelDeployment, load_local_model_catalog
from app.local_voice_recognizer import LocalVoiceRecognizer
from app.local_voice_runtime import LocalAsrResult, LocalVoicePolicy, TransientAudioFrame

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"
NOW = datetime(2026, 8, 18, 13, 10, tzinfo=timezone.utc)


class _Asr:
    def transcribe(self, audio, *, language_code):
        return "Jarvis bunu sağ ekrana at", LocalAsrResult(
            language_code="tr",
            confidence=0.97,
            final=True,
            backend_evidence_ref="evidence://local-asr/qwen3/tr-v1",
        )


def _deployment():
    return LocalModelDeployment(
        deployment_id="deployment:qwen3-asr",
        model_family="qwen3-asr",
        model_id="Qwen3-ASR-0.6B",
        runtime="LOCAL",
        endpoint_ref="runtime://local/qwen3-asr",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=0.93,
        benchmark_evidence_ref="benchmark://voice/qwen3-asr/tr-v1",
        observed_capabilities=frozenset(
            {LocalCapability.AUDIO, LocalCapability.ASR, LocalCapability.MULTILINGUAL}
        ),
    )


def _recognizer(key):
    return LocalVoiceRecognizer(
        policy=LocalVoicePolicy(
            voice_session_id="voice:wake",
            principal_ref="principal:erdi",
            identity_evidence_ref="identity://erdi/1",
            language_code="tr",
        ),
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(_deployment(),),
        asr_backends={"deployment:qwen3-asr": _Asr()},
        transcript_hmac_key=key,
    )


def _audio(sequence=1):
    return TransientAudioFrame(
        pcm16=b"\x01\x00" * 320,
        captured_at=NOW,
        sequence=sequence,
        final_chunk=True,
    )


def test_recognizer_returns_transient_text_but_never_voice_event_or_intent():
    recognizer = _recognizer(b"a" * 32)
    transcript, receipt = recognizer.recognize(_audio())
    assert transcript.text == "Jarvis bunu sağ ekrana at"
    assert receipt.final is True
    assert receipt.voice_event_created is False
    assert receipt.intent_eligible is False
    serialized = receipt.model_dump_json()
    assert transcript.text not in serialized
    assert receipt.raw_audio_retained is False
    assert receipt.transcript_text_retained is False
    assert receipt.paid_frontier_used is False


def test_recognizer_hmac_refs_are_unlinkable_across_runtime_keys():
    first = _recognizer(b"a" * 32)
    second = _recognizer(b"b" * 32)
    _, a = first.recognize(_audio())
    _, b = second.recognize(_audio())
    assert a.transcript_ref != b.transcript_ref
    assert a.transcript_ref.startswith("transcript://local-wake-gated/")
