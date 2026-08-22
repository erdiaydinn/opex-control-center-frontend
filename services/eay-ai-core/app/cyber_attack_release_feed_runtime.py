"""Exact-release MITRE ATT&CK feed transport for current Jarvis cyber context.

The legacy ATT&CK feed is preserved for compatibility, but current threat reasoning
must not depend on an unversioned repository mirror whose release may lag MITRE's
announced current version. This transport derives an exact MITRE/CTI tagged bundle
from an independently observed authoritative release, then reuses the canonical
ATT&CK normalizer from ``cyber_threat_feed_runtime``.

This is a transport/provenance adapter, not a second threat truth model:
- output remains the canonical ThreatKnowledgeRecord;
- release tag and payload digest are explicit;
- only the fixed ``mitre/cti`` repository and enterprise ATT&CK path are allowed;
- GET/read-only only; no raw payload or credential retention;
- no company truth, incident confirmation, exploit generation or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_defense_intelligence import ThreatKnowledgeRecord
from app.cyber_threat_feed_runtime import _normalize_mitre_attack
from app.cyber_threat_source_freshness_intelligence import (
    AuthoritativeReleaseObservation,
)

CYBER_ATTACK_RELEASE_FEED_CONTRACT = "eay-cyber-attack-release-feed-v1"
MITRE_CTI_RAW_PREFIX = "https://raw.githubusercontent.com/mitre/cti/"
MITRE_CTI_ENTERPRISE_PATH = "enterprise-attack/enterprise-attack.json"

_RELEASE = re.compile(r"^ATT&CK-v(?P<major>\d+)\.(?P<minor>\d+)$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class AttackReleaseFeedBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_ATTACK_RELEASE_FEED_CONTRACT
    feed_id: str = Field(min_length=1)
    release_ref: str = Field(min_length=1)
    authoritative_release_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    endpoint_ref: str = Field(min_length=1)
    method: str = "GET"
    read_only: bool = True
    raw_payload_retention_allowed: bool = False
    credential_material_retention_allowed: bool = False
    company_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_exact_release_and_non_authoritative(self) -> AttackReleaseFeedBinding:
        _release(self.release_ref, "attack_release_feed_invalid_release")
        expected = build_mitre_cti_release_endpoint(self.release_ref)
        if self.endpoint_ref != expected:
            raise ValueError("attack_release_feed_endpoint_not_exact_release")
        if self.method != "GET" or not self.read_only:
            raise ValueError("attack_release_feed_must_be_read_only_get")
        if self.raw_payload_retention_allowed:
            raise ValueError("attack_release_feed_raw_payload_retention_forbidden")
        if self.credential_material_retention_allowed:
            raise ValueError("attack_release_feed_credential_retention_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("attack_release_feed_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("attack_release_feed_never_confirms_incident")
        if self.exploit_generation_permitted:
            raise ValueError("attack_release_feed_exploit_generation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("attack_release_feed_never_grants_execution_authority")
        for ref in (self.feed_id, self.release_ref, self.endpoint_ref):
            _safe_ref(ref, "attack_release_feed_unsafe_reference_forbidden")
        _verify(self, "attack_release_feed_binding_fingerprint_mismatch")
        return self


class AttackReleaseFeedObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_ATTACK_RELEASE_FEED_CONTRACT
    observation_id: str = Field(min_length=1)
    feed_id: str = Field(min_length=1)
    binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_ref: str = Field(min_length=1)
    endpoint_ref: str = Field(min_length=1)
    observed_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_record_count: int = Field(ge=0)
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    company_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_exact_and_secret_safe(self) -> AttackReleaseFeedObservation:
        _release(self.release_ref, "attack_release_feed_invalid_release")
        _aware(self.observed_at, "attack_release_feed_observed_at_requires_timezone")
        if self.endpoint_ref != build_mitre_cti_release_endpoint(self.release_ref):
            raise ValueError("attack_release_feed_observation_endpoint_mismatch")
        if self.raw_payload_retained:
            raise ValueError("attack_release_feed_observation_raw_payload_forbidden")
        if self.credential_material_retained:
            raise ValueError("attack_release_feed_observation_credential_material_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("attack_release_feed_observation_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("attack_release_feed_observation_never_confirms_incident")
        if self.execution_authority_granted:
            raise ValueError("attack_release_feed_observation_never_grants_execution_authority")
        for ref in (self.observation_id, self.feed_id, self.release_ref, self.endpoint_ref):
            _safe_ref(ref, "attack_release_feed_observation_unsafe_reference_forbidden")
        _verify(self, "attack_release_feed_observation_fingerprint_mismatch")
        return self


class AttackReleaseFeedIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_ATTACK_RELEASE_FEED_CONTRACT
    observation: AttackReleaseFeedObservation
    records: tuple[ThreatKnowledgeRecord, ...]
    raw_payload_retained: bool = False
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_reuses_canonical_threat_records(self) -> AttackReleaseFeedIngestionResult:
        observation = AttackReleaseFeedObservation.model_validate(
            self.observation.model_dump(mode="json")
        )
        if observation.normalized_record_count != len(self.records):
            raise ValueError("attack_release_feed_record_count_mismatch")
        seen: set[str] = set()
        for raw in self.records:
            record = ThreatKnowledgeRecord.model_validate(raw.model_dump(mode="json"))
            if record.record_id in seen:
                raise ValueError("attack_release_feed_duplicate_record_id")
            seen.add(record.record_id)
        if self.raw_payload_retained:
            raise ValueError("attack_release_feed_result_raw_payload_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("attack_release_feed_result_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("attack_release_feed_result_never_grants_execution_authority")
        return self


def build_mitre_cti_release_endpoint(release_ref: str) -> str:
    _release(release_ref, "attack_release_feed_invalid_release")
    encoded_ref = quote(release_ref, safe="-._~")
    return f"{MITRE_CTI_RAW_PREFIX}{encoded_ref}/{MITRE_CTI_ENTERPRISE_PATH}"


def build_attack_release_feed_binding(
    *,
    authoritative_release: AuthoritativeReleaseObservation,
) -> AttackReleaseFeedBinding:
    release = AuthoritativeReleaseObservation.model_validate(
        authoritative_release.model_dump(mode="json")
    )
    endpoint = build_mitre_cti_release_endpoint(release.release_ref)
    draft = {
        "contract": CYBER_ATTACK_RELEASE_FEED_CONTRACT,
        "feed_id": f"global-threat-feed:mitre-attack:{release.release_ref.lower()}",
        "release_ref": release.release_ref,
        "authoritative_release_fingerprint": release.fingerprint,
        "endpoint_ref": endpoint,
        "method": "GET",
        "read_only": True,
        "raw_payload_retention_allowed": False,
        "credential_material_retention_allowed": False,
        "company_truth_authority_granted": False,
        "incident_confirmation_granted": False,
        "exploit_generation_permitted": False,
        "execution_authority_granted": False,
    }
    return AttackReleaseFeedBinding.model_validate(_sealed(draft))


def ingest_attack_release_payload(
    *,
    binding: AttackReleaseFeedBinding,
    authoritative_release: AuthoritativeReleaseObservation,
    payload: dict[str, Any],
    observed_at: datetime,
    http_status: int = 200,
) -> AttackReleaseFeedIngestionResult:
    binding = AttackReleaseFeedBinding.model_validate(binding.model_dump(mode="json"))
    release = AuthoritativeReleaseObservation.model_validate(
        authoritative_release.model_dump(mode="json")
    )
    _aware(observed_at, "attack_release_feed_observed_at_requires_timezone")
    if http_status != 200:
        raise ValueError("attack_release_feed_http_status_not_success")
    if release.fingerprint != binding.authoritative_release_fingerprint:
        raise ValueError("attack_release_feed_authoritative_release_binding_mismatch")
    if release.release_ref != binding.release_ref:
        raise ValueError("attack_release_feed_release_ref_mismatch")
    if release.release_observed_at > observed_at or release.recorded_at > observed_at:
        raise ValueError("attack_release_feed_future_release_observation_forbidden")

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    evidence_ref = f"mitre-cti:{binding.release_ref}:{digest[:24]}"
    records = _normalize_mitre_attack(
        payload=payload,
        observed_at=observed_at,
        evidence_ref=evidence_ref,
    )
    observation_id = f"attack-release-feed:{binding.release_ref}:{digest[:24]}"
    draft = {
        "contract": CYBER_ATTACK_RELEASE_FEED_CONTRACT,
        "observation_id": observation_id,
        "feed_id": binding.feed_id,
        "binding_fingerprint": binding.fingerprint,
        "release_ref": binding.release_ref,
        "endpoint_ref": binding.endpoint_ref,
        "observed_at": _iso(observed_at),
        "content_sha256": digest,
        "normalized_record_count": len(records),
        "raw_payload_retained": False,
        "credential_material_retained": False,
        "company_truth_authority_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    observation = AttackReleaseFeedObservation.model_validate(_sealed(draft))
    return AttackReleaseFeedIngestionResult(
        observation=observation,
        records=records,
        raw_payload_retained=False,
        company_truth_authority_granted=False,
        execution_authority_granted=False,
    )


def _release(value: str, error: str) -> tuple[int, int]:
    match = _RELEASE.fullmatch(value)
    if match is None:
        raise ValueError(error)
    return int(match.group("major")), int(match.group("minor"))


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "attack_release_feed_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
