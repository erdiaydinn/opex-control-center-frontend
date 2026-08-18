from pathlib import Path

from app.local_model_pool import load_local_model_catalog
from app.local_voice_pipeline import WakeGatedLocalVoicePipeline
from app.local_voice_pipeline_factory import build_wake_gated_local_voice_pipeline
from app.local_voice_runtime import LocalVoicePolicy
from app.voice_session import new_voice_session

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"


def test_v5_production_builder_exposes_wake_gated_pipeline_not_direct_intent_runtime():
    pipeline = build_wake_gated_local_voice_pipeline(
        policy=LocalVoicePolicy(
            voice_session_id="voice:v5",
            principal_ref="principal:erdi",
            identity_evidence_ref="identity://erdi/v5",
            language_code="tr",
        ),
        session=new_voice_session("voice:v5"),
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(),
        asr_backends={},
    )
    assert type(pipeline) is WakeGatedLocalVoicePipeline
    assert pipeline.recognizer.policy.voice_session_id == "voice:v5"
    assert pipeline.presence.session.session_id == "voice:v5"
    assert pipeline.presence.policy.wake_required_when_sleeping is True
    assert pipeline.presence.policy.wake_word_grants_authority is False
