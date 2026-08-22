from app.spatial_device_acceptance import DeviceEvidenceTier
from app.voice_device_acceptance import (
    VoiceDeviceAcceptanceCase,
    VoiceDeviceAcceptanceRun,
    VoiceDeviceProfile,
    VoiceDeviceScenario,
    evaluate_voice_device_acceptance,
)


def _profile():
    return VoiceDeviceProfile(
        profile_ref="device-lab://voice/1",
        os_build_ref="windows://11/24h2",
        machine_ref="machine://opaque/a",
        microphone_ref="mic://opaque/a",
        speaker_ref="speaker://opaque/a",
        asr_model_ref="model://qwen3-asr/tr-v1",
        tts_model_ref="model://chatterbox-v3/tr-v1",
        language_code="tr",
        acoustic_environment_ref="acoustic://lab/standard",
        device_evidence_refs=("evidence://device/mic/1", "evidence://device/speaker/1"),
    )


def _cases(tier):
    profile = _profile()
    scenarios = list(VoiceDeviceScenario)
    rows = []
    for index in range(40):
        scenario = scenarios[index % len(scenarios)]
        wake_expected = scenario is not VoiceDeviceScenario.WAKE_NEGATIVE
        command_expected = scenario not in {VoiceDeviceScenario.WAKE_NEGATIVE}
        rows.append(
            VoiceDeviceAcceptanceCase(
                case_id=f"voice:{index}",
                scenario=scenario,
                evidence_tier=tier,
                environment_fingerprint=profile.environment_fingerprint,
                wake_expected=wake_expected,
                wake_detected=wake_expected,
                command_expected=command_expected,
                command_eligible=command_expected,
                transcript_semantically_correct=True,
                response_audio_completed=True,
                trusted_identity_valid=True,
                asr_latency_ms=420,
                tts_first_audio_latency_ms=360,
                barge_in_stop_latency_ms=120 if scenario is VoiceDeviceScenario.BARGE_IN else None,
                evidence_refs=(f"evidence://device-lab/voice/{index}",),
            )
        )
    return tuple(rows)


def _run(tier, cases=None):
    return VoiceDeviceAcceptanceRun(
        system_ref="jarvis-local-voice-v6",
        profile=_profile(),
        evidence_tier=tier,
        cases=cases or _cases(tier),
        independent_observer_ref="observer://device-lab/voice",
        repository_ci_only=tier is DeviceEvidenceTier.SYNTHETIC,
    )


def test_synthetic_voice_matrix_never_counts_as_device_acceptance():
    result = evaluate_voice_device_acceptance(_run(DeviceEvidenceTier.SYNTHETIC))
    assert result.device_lab_accepted is False
    assert result.controlled_field_accepted is False
    assert result.production_claim_allowed is False
    assert "voice_device_acceptance_real_device_evidence_required" in result.blockers


def test_clean_device_lab_and_controlled_field_have_distinct_truth_tiers():
    lab = evaluate_voice_device_acceptance(_run(DeviceEvidenceTier.DEVICE_LAB))
    assert lab.device_lab_accepted is True
    assert lab.controlled_field_accepted is False
    assert lab.production_claim_allowed is False
    assert lab.blockers == ()

    field = evaluate_voice_device_acceptance(_run(DeviceEvidenceTier.CONTROLLED_FIELD))
    assert field.device_lab_accepted is True
    assert field.controlled_field_accepted is True
    assert field.production_claim_allowed is True
    assert field.automatic_production_promotion_allowed is False


def _mutate_first(tier, predicate, updates):
    rows = list(_cases(tier))
    index = next(i for i, item in enumerate(rows) if predicate(item))
    rows[index] = rows[index].model_copy(update=updates)
    return tuple(rows)


def test_false_wake_paid_frontier_leakage_biometric_and_untrusted_identity_each_block():
    tier = DeviceEvidenceTier.DEVICE_LAB
    false_wake = _mutate_first(
        tier,
        lambda item: item.scenario is VoiceDeviceScenario.WAKE_NEGATIVE,
        {"wake_detected": True},
    )
    result = evaluate_voice_device_acceptance(_run(tier, false_wake))
    assert "voice_device_acceptance_wake_false_accept_above_floor" in result.blockers

    for updates, blocker in (
        ({"paid_frontier_calls": 1}, "voice_device_acceptance_paid_frontier_call_detected"),
        ({"raw_audio_leakage": True}, "voice_device_acceptance_content_leakage"),
        ({"biometric_voice_identity_used": True}, "voice_device_acceptance_voice_biometric_identity_forbidden"),
        ({"trusted_identity_valid": False}, "voice_device_acceptance_untrusted_identity_command"),
    ):
        cases = _mutate_first(tier, lambda item: item.command_expected, updates)
        blocked = evaluate_voice_device_acceptance(_run(tier, cases))
        assert blocker in blocked.blockers


def test_slow_barge_in_blocks_voice_device_acceptance():
    tier = DeviceEvidenceTier.DEVICE_LAB
    cases = _mutate_first(
        tier,
        lambda item: item.scenario is VoiceDeviceScenario.BARGE_IN,
        {"barge_in_stop_latency_ms": 350},
    )
    result = evaluate_voice_device_acceptance(_run(tier, cases))
    assert "voice_device_acceptance_barge_in_latency_above_floor" in result.blockers
