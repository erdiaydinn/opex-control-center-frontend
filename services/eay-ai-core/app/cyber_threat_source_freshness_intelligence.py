"""Source-release freshness attestation for EAY Jarvis threat intelligence.

Polling a URL recently is not the same thing as proving the upstream dataset is on
the current authoritative release. This contract binds an ingested source release
to an independently observed authoritative release and fails closed when the
release is behind, unknown, or based on future-known evidence.

The first use is MITRE ATT&CK agile releases. The contract deliberately stays
non-authoritative for company risk: source freshness proves only that the global
knowledge source is current enough to use as global defensive context.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

THREAT_SOURCE_FRESHNESS_CONTRACT = "eay-cyber-threat-source-freshness-v1"

_RELEASE = re.compile(r"^(?:ATT&CK-v)?(?P<major>\d+)\.(?P<minor>\d+)$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class ThreatSourceFreshnessStatus(str, Enum):
    CURRENT = "current"
    BEHIND = "behind"
    AHEAD_UNVERIFIED = "ahead_unverified"
    UNKNOWN = "unknown"


class AuthoritativeReleaseObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = THREAT_SOURCE_FRESHNESS_CONTRACT
    source_family: Literal["mitre_attack"] = "mitre_attack"
    release_ref: str = Field(min_length=1)
    release_observed_at: datetime
    recorded_at: datetime
    evidence_ref: str = Field(min_length=1)
    authoritative_release_claim: bool = True
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_authoritative_source_metadata(
        self,
    ) -> AuthoritativeReleaseObservation:
        _release_tuple(self.release_ref, "threat_source_freshness_invalid_release")
        _aware(self.release_observed_at, "threat_source_freshness_observed_at_requires_timezone")
        _aware(self.recorded_at, "threat_source_freshness_recorded_at_requires_timezone")
        if self.recorded_at < self.release_observed_at:
            raise ValueError("threat_source_freshness_recorded_at_predates_observation")
        if not self.authoritative_release_claim:
            raise ValueError("threat_source_freshness_release_observation_must_be_authoritative")
        if self.company_truth_authority_granted:
            raise ValueError("threat_source_freshness_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("threat_source_freshness_never_grants_execution_authority")
        _safe_ref(self.evidence_ref, "threat_source_freshness_unsafe_reference_forbidden")
        _verify(self, "threat_source_freshness_release_observation_fingerprint_mismatch")
        return self


class ThreatSourceFreshnessReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = THREAT_SOURCE_FRESHNESS_CONTRACT
    receipt_id: str = Field(min_length=1)
    source_family: Literal["mitre_attack"] = "mitre_attack"
    source_endpoint_ref: str = Field(min_length=1)
    source_content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingested_release_ref: str | None = None
    authoritative_release_ref: str = Field(min_length=1)
    authoritative_release_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of: datetime
    status: ThreatSourceFreshnessStatus
    freshness_confirmed: bool = False
    reason_codes: tuple[str, ...] = Field(min_length=1)
    global_threat_use_allowed: bool = False
    company_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_fail_closed(self) -> ThreatSourceFreshnessReceipt:
        _aware(self.as_of, "threat_source_freshness_as_of_requires_timezone")
        _release_tuple(
            self.authoritative_release_ref,
            "threat_source_freshness_invalid_authoritative_release",
        )
        if self.ingested_release_ref is not None:
            _release_tuple(
                self.ingested_release_ref,
                "threat_source_freshness_invalid_ingested_release",
            )
        expected_confirmed = self.status is ThreatSourceFreshnessStatus.CURRENT
        if self.freshness_confirmed != expected_confirmed:
            raise ValueError("threat_source_freshness_confirmed_flag_mismatch")
        if self.global_threat_use_allowed != expected_confirmed:
            raise ValueError("threat_source_freshness_global_use_requires_current_release")
        if self.company_truth_authority_granted:
            raise ValueError("threat_source_freshness_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("threat_source_freshness_never_confirms_incident")
        if self.execution_authority_granted:
            raise ValueError("threat_source_freshness_never_grants_execution_authority")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("threat_source_freshness_reason_codes_must_be_unique")
        for ref in (
            self.receipt_id,
            self.source_endpoint_ref,
            self.ingested_release_ref,
            self.authoritative_release_ref,
            *self.reason_codes,
        ):
            if ref is not None:
                _safe_ref(ref, "threat_source_freshness_unsafe_reference_forbidden")
        _verify(self, "threat_source_freshness_receipt_fingerprint_mismatch")
        return self


def build_authoritative_attack_release_observation(
    *,
    release_ref: str,
    release_observed_at: datetime,
    recorded_at: datetime,
    evidence_ref: str,
) -> AuthoritativeReleaseObservation:
    draft = {
        "contract": THREAT_SOURCE_FRESHNESS_CONTRACT,
        "source_family": "mitre_attack",
        "release_ref": release_ref,
        "release_observed_at": _iso(release_observed_at),
        "recorded_at": _iso(recorded_at),
        "evidence_ref": evidence_ref,
        "authoritative_release_claim": True,
        "company_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return AuthoritativeReleaseObservation.model_validate(_sealed(draft))


def attest_attack_source_freshness(
    *,
    source_endpoint_ref: str,
    source_content_fingerprint: str,
    ingested_release_ref: str | None,
    authoritative_release: AuthoritativeReleaseObservation,
    as_of: datetime,
) -> ThreatSourceFreshnessReceipt:
    authoritative_release = AuthoritativeReleaseObservation.model_validate(
        authoritative_release.model_dump(mode="json")
    )
    _aware(as_of, "threat_source_freshness_as_of_requires_timezone")
    if not re.fullmatch(r"[0-9a-f]{64}", source_content_fingerprint):
        raise ValueError("threat_source_freshness_content_fingerprint_invalid")
    if (
        authoritative_release.release_observed_at > as_of
        or authoritative_release.recorded_at > as_of
    ):
        raise ValueError("threat_source_freshness_future_authoritative_release_forbidden")

    authoritative_version = _release_tuple(
        authoritative_release.release_ref,
        "threat_source_freshness_invalid_authoritative_release",
    )
    if ingested_release_ref is None:
        status = ThreatSourceFreshnessStatus.UNKNOWN
        reasons = ("ingested_release_unknown",)
    else:
        ingested_version = _release_tuple(
            ingested_release_ref,
            "threat_source_freshness_invalid_ingested_release",
        )
        if ingested_version == authoritative_version:
            status = ThreatSourceFreshnessStatus.CURRENT
            reasons = ("ingested_release_matches_authoritative_current",)
        elif ingested_version < authoritative_version:
            status = ThreatSourceFreshnessStatus.BEHIND
            reasons = ("ingested_release_behind_authoritative_current",)
        else:
            status = ThreatSourceFreshnessStatus.AHEAD_UNVERIFIED
            reasons = ("ingested_release_ahead_of_authoritative_observation",)

    confirmed = status is ThreatSourceFreshnessStatus.CURRENT
    seed = {
        "source_endpoint_ref": source_endpoint_ref,
        "source_content_fingerprint": source_content_fingerprint,
        "ingested_release_ref": ingested_release_ref,
        "authoritative_release_fingerprint": authoritative_release.fingerprint,
        "as_of": _iso(as_of),
    }
    receipt_id = f"threat-source-freshness:{_fingerprint(seed)[:24]}"
    draft = {
        "contract": THREAT_SOURCE_FRESHNESS_CONTRACT,
        "receipt_id": receipt_id,
        "source_family": "mitre_attack",
        "source_endpoint_ref": source_endpoint_ref,
        "source_content_fingerprint": source_content_fingerprint,
        "ingested_release_ref": ingested_release_ref,
        "authoritative_release_ref": authoritative_release.release_ref,
        "authoritative_release_fingerprint": authoritative_release.fingerprint,
        "as_of": _iso(as_of),
        "status": status.value,
        "freshness_confirmed": confirmed,
        "reason_codes": list(reasons),
        "global_threat_use_allowed": confirmed,
        "company_truth_authority_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    return ThreatSourceFreshnessReceipt.model_validate(_sealed(draft))


def verify_threat_source_freshness_receipt(
    *,
    receipt: ThreatSourceFreshnessReceipt,
) -> None:
    ThreatSourceFreshnessReceipt.model_validate(receipt.model_dump(mode="json"))


def _release_tuple(value: str, error: str) -> tuple[int, int]:
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
    _aware(value, "threat_source_freshness_datetime_requires_timezone")
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
