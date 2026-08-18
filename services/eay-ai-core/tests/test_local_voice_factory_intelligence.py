from pathlib import Path

from app.local_model_pool import load_local_model_catalog
from app.local_voice_factory import build_production_local_voice_runtime
from app.local_voice_privacy_runtime import HardenedLocalVoiceRuntime
from app.local_voice_runtime import LocalVoicePolicy
from app.voice_session import new_voice_session

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"


class _Playback:
    def start(self, audio, *, started_at):
        raise AssertionError("not used")

    def stop(self, playback_ref):
        raise AssertionError("not used")


def test_production_builder_never_returns_unhardened_base_runtime():
    runtime = build_production_local_voice_runtime(
        policy=LocalVoicePolicy(
            voice_session_id="voice:factory",
            principal_ref="principal:erdi",
            identity_evidence_ref="identity://erdi/factory",
            language_code="tr",
        ),
        session=new_voice_session("voice:factory"),
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(),
        asr_backends={},
        tts_backends={},
        playback=_Playback(),
    )
    assert type(runtime) is HardenedLocalVoiceRuntime
    first = runtime._transcript_ref("voice:factory", 1, "merhaba")
    second = runtime._transcript_ref("voice:factory", 2, "merhaba")
    assert first.startswith("transcript://local-hmac/")
    assert first != second
