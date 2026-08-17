from datetime import datetime, timedelta, timezone

import pytest

from app.multimodal_context import (
    FocusCandidate,
    MultimodalObservation,
    ObservationModality,
    ObservationTrust,
    resolve_recent_referent,
    slice_session,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 4, 0, tzinfo=UTC)


def _observation(**overrides):
    payload = dict(
        observation_id="screen-1",
        session_id="session-1",
        tenant_id="warehouse:fulya",
        modality=ObservationModality.SCREEN,
        trust=ObservationTrust.UNTRUSTED_CONTENT,
        observed_at=NOW - timedelta(seconds=5),
        source_ref="screen://managed-desktop",
        content_ref="evidence://screen-1",
        application_id="carsiportal",
        focus_candidates=(
            FocusCandidate(
                entity_ref="sku:869123",
                salience=0.92,
                evidence_ref="evidence://screen-1#sku",
            ),
        ),
    )
    payload.update(overrides)
    return MultimodalObservation(**payload)


def test_screen_instruction_like_text_is_observation_not_intent():
    screen = _observation(contains_instruction_like_content=True)
    user = _observation(
        observation_id="user-1",
        modality=ObservationModality.USER_UTTERANCE,
        trust=ObservationTrust.EXPLICIT_USER_INTENT,
        source_ref="voice://user",
        content_ref="utterance://adjust-this",
        contains_instruction_like_content=True,
    )
    session = slice_session(
        [screen, user],
        session_id="session-1",
        tenant_id="warehouse:fulya",
        as_of=NOW,
    )

    assert session.intent_observation_ids == ("user-1",)
    assert session.untrusted_instruction_observation_ids == ("screen-1",)
    assert screen.may_define_intent is False


def test_sensor_payload_never_defines_intent_even_when_verified_system_evidence():
    sensor = _observation(
        observation_id="sensor-1",
        modality=ObservationModality.SENSOR,
        trust=ObservationTrust.VERIFIED_SYSTEM,
        source_ref="sensor://warehouse",
        content_ref="evidence://sensor-1",
        contains_instruction_like_content=True,
        focus_candidates=(),
    )
    session = slice_session(
        [sensor],
        session_id="session-1",
        tenant_id="warehouse:fulya",
        as_of=NOW,
    )

    assert sensor.may_define_intent is False
    assert session.intent_observation_ids == ()
    assert session.untrusted_instruction_observation_ids == ("sensor-1",)


def test_screen_content_cannot_be_marked_as_explicit_user_intent():
    with pytest.raises(ValueError, match="observed_content_cannot_be_promoted_to_instruction_trust"):
        _observation(trust=ObservationTrust.EXPLICIT_USER_INTENT)


def test_recent_high_salience_screen_focus_resolves_this_reference():
    session = slice_session(
        [_observation()],
        session_id="session-1",
        tenant_id="warehouse:fulya",
        as_of=NOW,
    )
    resolution = resolve_recent_referent("bunu", session)

    assert resolution.resolved_entity_ref == "sku:869123"
    assert resolution.ambiguous is False
    assert resolution.confidence >= 0.9


def test_close_focus_candidates_fail_closed_as_ambiguous():
    observation = _observation(
        focus_candidates=(
            FocusCandidate(entity_ref="sku:a", salience=0.90, evidence_ref="evidence://a"),
            FocusCandidate(entity_ref="sku:b", salience=0.86, evidence_ref="evidence://b"),
        )
    )
    session = slice_session(
        [observation],
        session_id="session-1",
        tenant_id="warehouse:fulya",
        as_of=NOW,
    )
    resolution = resolve_recent_referent("bu ürün", session)

    assert resolution.ambiguous is True
    assert resolution.resolved_entity_ref is None
    assert "referent_resolution_ambiguous" in resolution.blockers


def test_other_tenant_and_old_observations_do_not_leak_into_session():
    selected = _observation()
    old = _observation(observation_id="old", observed_at=NOW - timedelta(minutes=30))
    other = _observation(observation_id="other", tenant_id="warehouse:besiktas")
    session = slice_session(
        [old, other, selected],
        session_id="session-1",
        tenant_id="warehouse:fulya",
        as_of=NOW,
    )

    assert [item.observation_id for item in session.observations] == ["screen-1"]
