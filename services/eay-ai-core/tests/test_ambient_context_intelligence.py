from datetime import datetime, timedelta, timezone

import pytest

from app.ambient_context_intelligence import (
    AmbientAction,
    AmbientModality,
    AmbientPrivacyPolicy,
    AmbientSemanticSignal,
    AmbientWatchRule,
    evaluate_ambient_watch,
)

NOW = datetime(2026, 8, 18, 18, 45, tzinfo=timezone.utc)


def _rule() -> AmbientWatchRule:
    return AmbientWatchRule(
        rule_ref="ambient://meeting/mentioned-risk",
        modalities=frozenset({AmbientModality.SYSTEM_AUDIO}),
        required_tags=frozenset({"risk-mentioned", "fulya"}),
        application_refs=frozenset({"app://teams"}),
        minimum_confidence=0.85,
        action=AmbientAction.NOTIFY,
        valid_from=NOW - timedelta(minutes=5),
        valid_until=NOW + timedelta(hours=2),
    )


def _signal(**overrides) -> AmbientSemanticSignal:
    payload = dict(
        signal_ref="ambient-signal://1",
        modality=AmbientModality.SYSTEM_AUDIO,
        observed_at=NOW,
        application_ref="app://teams",
        semantic_tags=frozenset({"risk-mentioned", "fulya"}),
        confidence=0.94,
        observation_seconds=8.0,
        local_processing=True,
    )
    payload.update(overrides)
    return AmbientSemanticSignal(**payload)


def test_raw_media_retention_is_forbidden() -> None:
    with pytest.raises(ValueError, match="ambient_raw_media_retention_forbidden"):
        AmbientPrivacyPolicy(
            enabled_modalities=frozenset({AmbientModality.SYSTEM_AUDIO}),
            raw_media_retention_allowed=True,
        )


def test_observation_cannot_be_reclassified_as_instruction() -> None:
    with pytest.raises(ValueError, match="ambient_observation_is_data_not_instruction"):
        _signal(instruction_from_observation=True)


def test_opt_in_local_system_audio_can_trigger_notification_only() -> None:
    policy = AmbientPrivacyPolicy(
        enabled_modalities=frozenset({AmbientModality.SYSTEM_AUDIO}),
        allowed_application_refs=frozenset({"app://teams"}),
        maximum_observation_seconds=15,
    )
    decision = evaluate_ambient_watch(signal=_signal(), rule=_rule(), policy=policy, now=NOW)
    assert decision.matched
    assert decision.notification_eligible
    assert decision.external_write_eligible is False
    assert decision.execution_authority_granted is False


def test_blocked_application_fails_closed() -> None:
    policy = AmbientPrivacyPolicy(
        enabled_modalities=frozenset({AmbientModality.SYSTEM_AUDIO}),
        blocked_application_refs=frozenset({"app://teams"}),
    )
    decision = evaluate_ambient_watch(signal=_signal(), rule=_rule(), policy=policy, now=NOW)
    assert not decision.matched
    assert "ambient_application_blocked" in decision.blockers


def test_cloud_processed_ambient_signal_is_rejected_when_local_required() -> None:
    policy = AmbientPrivacyPolicy(
        enabled_modalities=frozenset({AmbientModality.SYSTEM_AUDIO}),
        allowed_application_refs=frozenset({"app://teams"}),
        local_processing_required=True,
    )
    decision = evaluate_ambient_watch(
        signal=_signal(local_processing=False),
        rule=_rule(),
        policy=policy,
        now=NOW,
    )
    assert not decision.matched
    assert "ambient_local_processing_required" in decision.blockers
