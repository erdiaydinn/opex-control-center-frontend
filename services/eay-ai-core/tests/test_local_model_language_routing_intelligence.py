from pathlib import Path

from app.local_model_pool import (
    LocalCapability,
    LocalModelDeployment,
    LocalModelTask,
    load_local_model_catalog,
    select_local_model,
)

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"


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


def test_turkish_asr_selects_qwen3_asr_when_benchmarked_and_reachable():
    catalog = load_local_model_catalog(CATALOG_PATH)
    deployment = _deployment(
        "qwen3-asr",
        "Qwen3-ASR-0.6B",
        0.91,
        {LocalCapability.AUDIO, LocalCapability.ASR, LocalCapability.MULTILINGUAL},
    )
    result = select_local_model(
        task=LocalModelTask(
            task_ref="voice:asr:tr",
            task_class="STREAMING_ASR",
            required_capabilities=frozenset(
                {LocalCapability.AUDIO, LocalCapability.ASR, LocalCapability.MULTILINGUAL}
            ),
            minimum_benchmark_score=0.85,
            language_code="tr",
        ),
        deployments=(deployment,),
        catalog=catalog,
    )
    assert result.local_execution_available is True
    assert result.model_family == "qwen3-asr"
    assert result.paid_frontier_escalation_required is False


def test_turkish_tts_selects_chatterbox_and_rejects_unverified_qwen3_tts_language():
    catalog = load_local_model_catalog(CATALOG_PATH)
    chatterbox = _deployment(
        "chatterbox-multilingual-v3",
        "ResembleAI/Chatterbox-Multilingual-v3",
        0.87,
        {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL},
    )
    qwen = _deployment(
        "qwen3-tts",
        "Qwen3-TTS-1.7B",
        0.99,
        {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL},
    )
    result = select_local_model(
        task=LocalModelTask(
            task_ref="voice:tts:tr",
            task_class="TURKISH_TTS",
            required_capabilities=frozenset(
                {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL}
            ),
            minimum_benchmark_score=0.80,
            language_code="tr",
        ),
        deployments=(qwen, chatterbox),
        catalog=catalog,
    )
    assert result.local_execution_available is True
    assert result.model_family == "chatterbox-multilingual-v3"
    assert result.model_id == "ResembleAI/Chatterbox-Multilingual-v3"

    qwen_only = select_local_model(
        task=LocalModelTask(
            task_ref="voice:tts:tr:qwen-only",
            task_class="TURKISH_TTS",
            required_capabilities=frozenset(
                {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL}
            ),
            minimum_benchmark_score=0.80,
            language_code="tr",
        ),
        deployments=(qwen,),
        catalog=catalog,
    )
    assert qwen_only.local_execution_available is False
    assert qwen_only.paid_frontier_escalation_required is True
    assert "local_model_language_support_not_verified" in qwen_only.blockers


def test_language_code_must_be_explicitly_normalized():
    import pytest

    with pytest.raises(ValueError, match="language_code_must_be_lowercase"):
        LocalModelTask(
            task_ref="voice:bad-language",
            task_class="STREAMING_ASR",
            required_capabilities=frozenset({LocalCapability.AUDIO, LocalCapability.ASR}),
            language_code="TR",
        )
