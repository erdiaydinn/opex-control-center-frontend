from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.cyber_attack_release_feed_runtime import (
    MITRE_CTI_ENTERPRISE_PATH,
    MITRE_CTI_RAW_PREFIX,
    AttackReleaseFeedBinding,
    AttackReleaseFeedObservation,
    build_attack_release_feed_binding,
    build_mitre_cti_release_endpoint,
    ingest_attack_release_payload,
)
from app.cyber_defense_intelligence import ThreatIntelligenceSource
from app.cyber_threat_source_freshness_intelligence import (
    build_authoritative_attack_release_observation,
)

NOW = datetime(2026, 8, 19, 20, 0, tzinfo=UTC)
LEGACY_MIRROR = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack.json"
)


def _release(ref: str = "ATT&CK-v19.2"):
    return build_authoritative_attack_release_observation(
        release_ref=ref,
        release_observed_at=NOW - timedelta(minutes=30),
        recorded_at=NOW - timedelta(minutes=20),
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )


def _payload():
    return {
        "type": "bundle",
        "id": "bundle--11111111-1111-1111-1111-111111111111",
        "objects": [
            {
                "type": "attack-pattern",
                "id": "attack-pattern--11111111-1111-1111-1111-111111111111",
                "created": "2020-01-01T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1059"}
                ],
                "x_mitre_platforms": ["Windows", "Linux"],
                "x_mitre_version": "2.7",
            },
            {
                "type": "malware",
                "id": "malware--22222222-2222-2222-2222-222222222222",
                "created": "2026-08-01T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "S9044"}
                ],
            },
        ],
    }


def test_release_endpoint_is_exact_mitre_cti_tag_not_legacy_mirror():
    endpoint = build_mitre_cti_release_endpoint("ATT&CK-v19.2")
    assert endpoint == (
        f"{MITRE_CTI_RAW_PREFIX}ATT%26CK-v19.2/{MITRE_CTI_ENTERPRISE_PATH}"
    )
    assert endpoint != LEGACY_MIRROR
    assert "mitre/cti" in endpoint
    assert "ATT%26CK-v19.2" in endpoint


def test_binding_is_derived_from_exact_authoritative_release():
    release = _release()
    binding = build_attack_release_feed_binding(authoritative_release=release)

    assert binding.release_ref == "ATT&CK-v19.2"
    assert binding.authoritative_release_fingerprint == release.fingerprint
    assert binding.method == "GET"
    assert binding.read_only is True
    assert binding.raw_payload_retention_allowed is False
    assert binding.company_truth_authority_granted is False
    assert binding.incident_confirmation_granted is False
    assert binding.exploit_generation_permitted is False
    assert binding.execution_authority_granted is False


def test_model_cannot_swap_exact_release_endpoint_back_to_legacy_or_arbitrary_url():
    binding = build_attack_release_feed_binding(authoritative_release=_release())
    for endpoint in (LEGACY_MIRROR, "https://example.invalid/enterprise-attack.json"):
        tampered = binding.model_copy(update={"endpoint_ref": endpoint})
        with pytest.raises(
            ValidationError,
            match="attack_release_feed_endpoint_not_exact_release",
        ):
            AttackReleaseFeedBinding.model_validate(tampered.model_dump(mode="json"))


def test_exact_release_payload_reuses_canonical_attack_normalizer():
    release = _release()
    binding = build_attack_release_feed_binding(authoritative_release=release)
    result = ingest_attack_release_payload(
        binding=binding,
        authoritative_release=release,
        payload=_payload(),
        observed_at=NOW,
    )

    assert result.observation.release_ref == "ATT&CK-v19.2"
    assert result.observation.endpoint_ref == binding.endpoint_ref
    assert result.observation.normalized_record_count == 1
    assert result.observation.raw_payload_retained is False
    assert len(result.records) == 1
    record = result.records[0]
    assert record.source is ThreatIntelligenceSource.MITRE_ATTACK
    assert record.attack_technique_ids == ("T1059",)
    assert set(record.product_refs) == {"platform:windows", "platform:linux"}
    assert record.company_truth_granted is False
    assert record.incident_confirmation_granted is False
    assert record.execution_authority_granted is False


def test_release_binding_must_match_exact_authoritative_observation():
    release_192 = _release("ATT&CK-v19.2")
    release_193 = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.3",
        release_observed_at=NOW - timedelta(minutes=10),
        recorded_at=NOW - timedelta(minutes=5),
        evidence_ref="mitre-attack:update:v19.3",
    )
    binding = build_attack_release_feed_binding(authoritative_release=release_192)

    with pytest.raises(
        ValueError,
        match="attack_release_feed_authoritative_release_binding_mismatch",
    ):
        ingest_attack_release_payload(
            binding=binding,
            authoritative_release=release_193,
            payload=_payload(),
            observed_at=NOW,
        )


def test_future_release_observation_cannot_be_used_for_historical_ingestion():
    release = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.2",
        release_observed_at=NOW,
        recorded_at=NOW,
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )
    binding = build_attack_release_feed_binding(authoritative_release=release)
    with pytest.raises(
        ValueError,
        match="attack_release_feed_future_release_observation_forbidden",
    ):
        ingest_attack_release_payload(
            binding=binding,
            authoritative_release=release,
            payload=_payload(),
            observed_at=NOW - timedelta(hours=1),
        )


def test_non_success_http_result_is_not_ingested():
    release = _release()
    binding = build_attack_release_feed_binding(authoritative_release=release)
    with pytest.raises(ValueError, match="attack_release_feed_http_status_not_success"):
        ingest_attack_release_payload(
            binding=binding,
            authoritative_release=release,
            payload=_payload(),
            observed_at=NOW,
            http_status=503,
        )


def test_release_token_must_be_exact_attack_tag_shape():
    for value in ("19.2", "ATTACK-v19.2", "ATT&CK-v19", "ATT&CK-v19.2.1"):
        with pytest.raises(ValueError, match="attack_release_feed_invalid_release"):
            build_mitre_cti_release_endpoint(value)


def test_observation_tamper_cannot_relabel_release_or_endpoint():
    release = _release()
    binding = build_attack_release_feed_binding(authoritative_release=release)
    observation = ingest_attack_release_payload(
        binding=binding,
        authoritative_release=release,
        payload=_payload(),
        observed_at=NOW,
    ).observation
    tampered = observation.model_copy(update={"release_ref": "ATT&CK-v19.3"})

    with pytest.raises(ValidationError):
        AttackReleaseFeedObservation.model_validate(tampered.model_dump(mode="json"))


def test_observation_cannot_be_modified_to_retain_credentials_or_grant_execution():
    release = _release()
    binding = build_attack_release_feed_binding(authoritative_release=release)
    observation = ingest_attack_release_payload(
        binding=binding,
        authoritative_release=release,
        payload=_payload(),
        observed_at=NOW,
    ).observation
    payload = observation.model_dump(mode="json")
    payload["execution_authority_granted"] = True

    with pytest.raises(
        ValidationError,
        match="attack_release_feed_observation_never_grants_execution_authority",
    ):
        AttackReleaseFeedObservation.model_validate(payload)
