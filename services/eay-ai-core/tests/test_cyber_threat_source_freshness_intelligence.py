from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.cyber_threat_source_freshness_intelligence import (
    AuthoritativeReleaseObservation,
    ThreatSourceFreshnessReceipt,
    ThreatSourceFreshnessStatus,
    attest_attack_source_freshness,
    build_authoritative_attack_release_observation,
    verify_threat_source_freshness_receipt,
)

NOW = datetime(2026, 8, 19, 19, 40, tzinfo=UTC)
SOURCE_ENDPOINT = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)
CONTENT = "a" * 64


def _authoritative(release: str = "ATT&CK-v19.2"):
    return build_authoritative_attack_release_observation(
        release_ref=release,
        release_observed_at=NOW - timedelta(minutes=30),
        recorded_at=NOW - timedelta(minutes=20),
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )


def test_exact_release_match_is_current_and_usable_for_global_threat_context():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref="ATT&CK-v19.2",
        authoritative_release=_authoritative(),
        as_of=NOW,
    )

    assert receipt.status is ThreatSourceFreshnessStatus.CURRENT
    assert receipt.freshness_confirmed is True
    assert receipt.global_threat_use_allowed is True
    assert receipt.company_truth_authority_granted is False
    assert receipt.incident_confirmation_granted is False
    assert receipt.execution_authority_granted is False


def test_older_ingested_attack_release_is_explicitly_behind_and_not_globally_usable():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref="ATT&CK-v19.1",
        authoritative_release=_authoritative(),
        as_of=NOW,
    )

    assert receipt.status is ThreatSourceFreshnessStatus.BEHIND
    assert receipt.freshness_confirmed is False
    assert receipt.global_threat_use_allowed is False
    assert receipt.reason_codes == ("ingested_release_behind_authoritative_current",)


def test_unknown_ingested_release_fails_closed_instead_of_claiming_current():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref=None,
        authoritative_release=_authoritative(),
        as_of=NOW,
    )

    assert receipt.status is ThreatSourceFreshnessStatus.UNKNOWN
    assert receipt.freshness_confirmed is False
    assert receipt.global_threat_use_allowed is False


def test_release_ahead_of_authoritative_observation_is_not_silently_trusted():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref="ATT&CK-v19.3",
        authoritative_release=_authoritative(),
        as_of=NOW,
    )

    assert receipt.status is ThreatSourceFreshnessStatus.AHEAD_UNVERIFIED
    assert receipt.freshness_confirmed is False
    assert receipt.global_threat_use_allowed is False


def test_future_known_authoritative_release_cannot_leak_into_historical_reasoning():
    authoritative = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.2",
        release_observed_at=NOW,
        recorded_at=NOW,
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )
    with pytest.raises(
        ValueError,
        match="threat_source_freshness_future_authoritative_release_forbidden",
    ):
        attest_attack_source_freshness(
            source_endpoint_ref=SOURCE_ENDPOINT,
            source_content_fingerprint=CONTENT,
            ingested_release_ref="ATT&CK-v19.2",
            authoritative_release=authoritative,
            as_of=NOW - timedelta(hours=1),
        )


@pytest.mark.parametrize("release", ["v19", "19", "ATT&CK-v19", "19.x", "19.2.1"])
def test_release_tokens_must_be_exact_major_minor(release: str):
    with pytest.raises(ValidationError):
        build_authoritative_attack_release_observation(
            release_ref=release,
            release_observed_at=NOW,
            recorded_at=NOW,
            evidence_ref="mitre-attack:release-evidence",
        )


def test_authoritative_release_observation_never_grants_company_or_execution_truth():
    observation = _authoritative()
    payload = observation.model_dump(mode="json")
    payload["company_truth_authority_granted"] = True
    with pytest.raises(ValidationError, match="threat_source_freshness_never_grants_company_truth"):
        AuthoritativeReleaseObservation.model_validate(payload)


def test_freshness_receipt_tamper_cannot_turn_behind_into_current():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref="ATT&CK-v19.1",
        authoritative_release=_authoritative(),
        as_of=NOW,
    )
    tampered = receipt.model_copy(
        update={
            "status": ThreatSourceFreshnessStatus.CURRENT,
            "freshness_confirmed": True,
            "global_threat_use_allowed": True,
        }
    )

    with pytest.raises(ValidationError, match="threat_source_freshness_receipt_fingerprint_mismatch"):
        verify_threat_source_freshness_receipt(receipt=tampered)


def test_current_flag_and_global_use_cannot_disagree():
    receipt = attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint=CONTENT,
        ingested_release_ref="ATT&CK-v19.2",
        authoritative_release=_authoritative(),
        as_of=NOW,
    )
    payload = receipt.model_dump(mode="json")
    payload["global_threat_use_allowed"] = False

    with pytest.raises(
        ValidationError,
        match="threat_source_freshness_global_use_requires_current_release",
    ):
        ThreatSourceFreshnessReceipt.model_validate(payload)
