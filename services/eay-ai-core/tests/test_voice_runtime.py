import pytest

from app.voice_runtime import (
    CORE_LANGUAGES,
    ProactiveSuggestionPolicy,
    VoiceProfile,
    VoiceState,
    VoiceStateMachine,
    default_jarvis_profile,
)


def test_default_jarvis_profile_covers_core_languages_and_rtl_targets():
    profile = default_jarvis_profile()
    assert set(profile.languages) == {"tr", "en", "de", "ar", "fa"}
    assert set(profile.languages) == set(CORE_LANGUAGES)
    assert profile.full_duplex is True
    assert profile.barge_in is True
    assert profile.local_first is True
    assert profile.clone_reference_voice is False
    assert len(profile.fingerprint) == 64


def test_voice_profile_requires_complete_pipeline():
    profile = default_jarvis_profile()
    broken = VoiceProfile(
        profile_id=profile.profile_id,
        wake_phrases=profile.wake_phrases,
        languages=profile.languages,
        sample_rate_hz=profile.sample_rate_hz,
        full_duplex=profile.full_duplex,
        barge_in=profile.barge_in,
        local_first=profile.local_first,
        voice_identity_id=profile.voice_identity_id,
        clone_reference_voice=False,
        adapters=profile.adapters[:-1],
    )
    with pytest.raises(ValueError, match="voice_pipeline_adapter_coverage_required"):
        broken.validate()


def test_reference_voice_cloning_is_forbidden_by_profile_contract():
    profile = default_jarvis_profile()
    unsafe = VoiceProfile(
        profile_id=profile.profile_id,
        wake_phrases=profile.wake_phrases,
        languages=profile.languages,
        sample_rate_hz=profile.sample_rate_hz,
        full_duplex=profile.full_duplex,
        barge_in=profile.barge_in,
        local_first=profile.local_first,
        voice_identity_id="copied-reference-voice",
        clone_reference_voice=True,
        adapters=profile.adapters,
    )
    with pytest.raises(ValueError, match="voice_reference_clone_forbidden"):
        unsafe.validate()


def test_barge_in_interrupts_tts_and_returns_to_listening():
    machine = VoiceStateMachine(barge_in=True)
    assert machine.wake() == VoiceState.LISTENING
    assert machine.end_utterance() == VoiceState.THINKING
    assert machine.begin_speaking() == VoiceState.SPEAKING
    assert machine.interrupt() == VoiceState.INTERRUPTED
    assert machine.resume_listening() == VoiceState.LISTENING


def test_write_or_critical_action_requires_explicit_approval():
    machine = VoiceStateMachine()
    machine.wake()
    machine.end_utterance()
    assert machine.require_action_approval("write") == VoiceState.APPROVAL_REQUIRED
    assert machine.approve("approval-123") == VoiceState.THINKING


def test_read_only_action_does_not_force_approval():
    machine = VoiceStateMachine()
    machine.wake()
    machine.end_utterance()
    assert machine.require_action_approval("read") == VoiceState.THINKING


def test_proactive_policy_can_surface_read_insight_but_not_write():
    policy = ProactiveSuggestionPolicy()
    assert policy.permits(risk="read", material_signal=True) is True
    assert policy.permits(risk="write", material_signal=True) is False
    assert policy.permits(risk="critical", material_signal=True) is False
    assert policy.permits(risk="read", material_signal=False) is False
