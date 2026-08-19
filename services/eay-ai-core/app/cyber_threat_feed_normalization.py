"""Pure, non-network cyber threat-feed normalization for EAY Jarvis.

Trusted collectors may fetch reviewed public feeds and pass decoded JSON here.
This layer retains only fingerprints and normalized threat records: no raw feed
payload, company truth, incident confirmation, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.cyber_defense_intelligence import (
    ThreatIntelligenceSource,
    ThreatKnowledgeRecord,
    build_threat_record,
)

CYBER_THREAT_FEED_NORMALIZATION_CONTRACT = "eay-cyber-threat-feed-normalization-v1"

_CVE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_CWE = re.compile(r"^CWE-\d+$", re.IGNORECASE)
_ATTACK = re.compile(r"^T\d{4}(?:\.\d{3})?$", re.IGNORECASE)
_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature)"
)


class ThreatFeedNormalizationReceipt(BaseModel):
    contract: str = CYBER_THREAT_FEED_NORMALIZATION_CONTRACT
    source: ThreatIntelligenceSource
    feed_ref: str = Field(min_length=1)
    observed_at: datetime
    payload_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    record_fingerprints: tuple[str, ...]
    ignored_object_count: int = Field(ge=0)
    raw_payload_retained: bool = False
    network_io_performed: bool = False
    company_truth_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_non_authoritative(self) -> ThreatFeedNormalizationReceipt:
        _aware(self.observed_at, "cyber_feed_observed_at_requires_timezone")
        _safe_ref(self.feed_ref)
        if len(self.record_fingerprints) != len(set(self.record_fingerprints)):
            raise ValueError("cyber_feed_record_fingerprints_must_be_unique")
        if self.raw_payload_retained:
            raise ValueError("cyber_feed_raw_payload_retention_forbidden")
        if self.network_io_performed:
            raise ValueError("cyber_feed_normalizer_network_io_forbidden")
        if self.company_truth_granted:
            raise ValueError("cyber_feed_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_feed_never_confirms_company_incident")
        if self.execution_authority_granted:
            raise ValueError("cyber_feed_never_grants_execution_authority")
        if self.fingerprint != _fingerprint(_model_payload(self)):
            raise ValueError("cyber_feed_receipt_fingerprint_mismatch")
        return self


class NormalizedThreatFeed(BaseModel):
    contract: str = CYBER_THREAT_FEED_NORMALIZATION_CONTRACT
    receipt: ThreatFeedNormalizationReceipt
    records: tuple[ThreatKnowledgeRecord, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def feed_is_integral(self) -> NormalizedThreatFeed:
        receipt = ThreatFeedNormalizationReceipt.model_validate(
            self.receipt.model_dump(mode="json")
        )
        records = tuple(
            ThreatKnowledgeRecord.model_validate(record.model_dump(mode="json"))
            for record in self.records
        )
        if any(record.source is not receipt.source for record in records):
            raise ValueError("cyber_feed_source_record_mismatch")
        if tuple(record.fingerprint for record in records) != receipt.record_fingerprints:
            raise ValueError("cyber_feed_record_receipt_mismatch")
        if len({record.record_id for record in records}) != len(records):
            raise ValueError("cyber_feed_duplicate_record_id")
        if self.fingerprint != _fingerprint(_model_payload(self)):
            raise ValueError("cyber_feed_fingerprint_mismatch")
        return self


def normalize_cisa_kev_payload(
    *, payload: dict[str, Any], feed_ref: str, observed_at: datetime
) -> NormalizedThreatFeed:
    """Normalize CISA KEV JSON without retaining descriptions/actions."""

    _validate_observation(feed_ref=feed_ref, observed_at=observed_at)
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise TypeError("cyber_cisa_kev_vulnerabilities_required")
    declared_count = payload.get("count")
    if declared_count is not None and declared_count != len(vulnerabilities):
        raise ValueError("cyber_cisa_kev_count_mismatch")

    records: list[ThreatKnowledgeRecord] = []
    for item in vulnerabilities:
        if not isinstance(item, dict):
            raise TypeError("cyber_cisa_kev_entry_invalid")
        cve_id = _required_cve(item.get("cveID"))
        date_added = _parse_date(item.get("dateAdded"), "cyber_cisa_kev_date_added_invalid")
        product_ref = _product_hash(item.get("vendorProject"), item.get("product"))
        records.append(
            build_threat_record(
                record_id=f"cisa-kev:{cve_id.lower()}",
                source=ThreatIntelligenceSource.CISA_KEV,
                source_record_id=cve_id,
                published_at=date_added,
                recorded_at=observed_at,
                source_evidence_ref=f"{feed_ref}#{cve_id}",
                product_refs=(product_ref,) if product_ref else (),
                cve_ids=(cve_id,),
                cwe_ids=_identifier_list(item.get("cwes", ()), _CWE),
                known_exploited_in_wild=True,
            )
        )
    return _build_feed(
        source=ThreatIntelligenceSource.CISA_KEV,
        payload=payload,
        feed_ref=feed_ref,
        observed_at=observed_at,
        records=tuple(records),
        ignored_object_count=0,
    )


def normalize_nvd_cve_payload(
    *, payload: dict[str, Any], feed_ref: str, observed_at: datetime
) -> NormalizedThreatFeed:
    """Normalize NVD CVE API 2.0; CISA remains KEV authority."""

    _validate_observation(feed_ref=feed_ref, observed_at=observed_at)
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        raise TypeError("cyber_nvd_vulnerabilities_required")

    records: list[ThreatKnowledgeRecord] = []
    for wrapper in vulnerabilities:
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("cve"), dict):
            raise TypeError("cyber_nvd_cve_entry_invalid")
        cve = wrapper["cve"]
        cve_id = _required_cve(cve.get("id"))
        # NVD API 2.0 commonly serializes UTC timestamps without an explicit
        # offset. Only this reviewed source gets the UTC-default treatment.
        published = _parse_datetime(
            cve.get("published"), "cyber_nvd_published_invalid", assume_utc=True
        )
        records.append(
            build_threat_record(
                record_id=f"nvd:{cve_id.lower()}",
                source=ThreatIntelligenceSource.NVD,
                source_record_id=cve_id,
                published_at=published,
                recorded_at=observed_at,
                source_evidence_ref=f"{feed_ref}#{cve_id}",
                cve_ids=(cve_id,),
                cwe_ids=_nvd_cwes(cve),
                severity_score=_nvd_max_cvss(cve),
                known_exploited_in_wild=False,
            )
        )
    return _build_feed(
        source=ThreatIntelligenceSource.NVD,
        payload=payload,
        feed_ref=feed_ref,
        observed_at=observed_at,
        records=tuple(records),
        ignored_object_count=0,
    )


def normalize_mitre_attack_stix_payload(
    *, payload: dict[str, Any], feed_ref: str, observed_at: datetime
) -> NormalizedThreatFeed:
    """Normalize active MITRE ATT&CK STIX attack-pattern objects only."""

    _validate_observation(feed_ref=feed_ref, observed_at=observed_at)
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise TypeError("cyber_attack_stix_objects_required")

    records: list[ThreatKnowledgeRecord] = []
    ignored = 0
    for item in objects:
        if not isinstance(item, dict):
            raise TypeError("cyber_attack_stix_object_invalid")
        if (
            item.get("type") != "attack-pattern"
            or item.get("revoked") is True
            or item.get("x_mitre_deprecated") is True
        ):
            ignored += 1
            continue
        technique_id = _attack_external_id(item)
        if technique_id is None:
            ignored += 1
            continue
        modified = _parse_datetime(
            item.get("modified") or item.get("created"),
            "cyber_attack_modified_invalid",
        )
        records.append(
            build_threat_record(
                record_id=f"mitre-attack:{technique_id.lower()}",
                source=ThreatIntelligenceSource.MITRE_ATTACK,
                source_record_id=technique_id,
                published_at=modified,
                recorded_at=observed_at,
                source_evidence_ref=f"{feed_ref}#{technique_id}",
                attack_technique_ids=(technique_id,),
            )
        )
    return _build_feed(
        source=ThreatIntelligenceSource.MITRE_ATTACK,
        payload=payload,
        feed_ref=feed_ref,
        observed_at=observed_at,
        records=tuple(records),
        ignored_object_count=ignored,
    )


def _build_feed(
    *,
    source: ThreatIntelligenceSource,
    payload: dict[str, Any],
    feed_ref: str,
    observed_at: datetime,
    records: tuple[ThreatKnowledgeRecord, ...],
    ignored_object_count: int,
) -> NormalizedThreatFeed:
    receipt_payload = {
        "contract": CYBER_THREAT_FEED_NORMALIZATION_CONTRACT,
        "source": source.value,
        "feed_ref": feed_ref,
        "observed_at": _iso(observed_at),
        "payload_fingerprint": _fingerprint(payload),
        "record_fingerprints": [record.fingerprint for record in records],
        "ignored_object_count": ignored_object_count,
        "raw_payload_retained": False,
        "network_io_performed": False,
        "company_truth_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    receipt = ThreatFeedNormalizationReceipt.model_validate(
        {**receipt_payload, "fingerprint": _fingerprint(receipt_payload)}
    )
    feed_payload = {
        "contract": CYBER_THREAT_FEED_NORMALIZATION_CONTRACT,
        "receipt": receipt.model_dump(mode="json"),
        "records": [record.model_dump(mode="json") for record in records],
    }
    return NormalizedThreatFeed.model_validate(
        {**feed_payload, "fingerprint": _fingerprint(feed_payload)}
    )


def _validate_observation(*, feed_ref: str, observed_at: datetime) -> None:
    _safe_ref(feed_ref)
    _aware(observed_at, "cyber_feed_observed_at_requires_timezone")


def _required_cve(value: Any) -> str:
    if not isinstance(value, str) or not _CVE.fullmatch(value):
        raise ValueError("cyber_feed_cve_id_invalid")
    return value.upper()


def _identifier_list(value: Any, pattern: re.Pattern[str]) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise TypeError("cyber_feed_identifier_list_invalid")
    return tuple(
        sorted(
            {
                item.upper()
                for item in value
                if isinstance(item, str) and pattern.fullmatch(item)
            }
        )
    )


def _nvd_cwes(cve: dict[str, Any]) -> tuple[str, ...]:
    cwes: set[str] = set()
    for weakness in cve.get("weaknesses", ()):
        if not isinstance(weakness, dict):
            continue
        for description in weakness.get("description", ()):
            if not isinstance(description, dict):
                continue
            value = description.get("value")
            if isinstance(value, str) and _CWE.fullmatch(value):
                cwes.add(value.upper())
    return tuple(sorted(cwes))


def _nvd_max_cvss(cve: dict[str, Any]) -> float | None:
    metrics = cve.get("metrics", {})
    if not isinstance(metrics, dict):
        return None
    scores: list[float] = []
    for entries in metrics.values():
        if not isinstance(entries, list):
            continue
        for metric in entries:
            if not isinstance(metric, dict) or not isinstance(metric.get("cvssData"), dict):
                continue
            score = metric["cvssData"].get("baseScore")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                numeric = float(score)
                if 0 <= numeric <= 10:
                    scores.append(numeric)
    return max(scores) if scores else None


def _attack_external_id(item: dict[str, Any]) -> str | None:
    for reference in item.get("external_references", ()):
        if not isinstance(reference, dict) or reference.get("source_name") != "mitre-attack":
            continue
        external_id = reference.get("external_id")
        if isinstance(external_id, str) and _ATTACK.fullmatch(external_id):
            return external_id.upper()
    return None


def _product_hash(vendor: Any, product: Any) -> str | None:
    if not isinstance(vendor, str) or not isinstance(product, str):
        return None
    digest = hashlib.sha256(
        f"{vendor.strip()}|{product.strip()}".encode()
    ).hexdigest()
    return f"product:sha256:{digest}"


def _parse_date(value: Any, error: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(error)
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(error) from exc


def _parse_datetime(value: Any, error: str, *, assume_utc: bool = False) -> datetime:
    if not isinstance(value, str):
        raise TypeError(error)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(error) from exc
    if parsed.tzinfo is None and assume_utc:
        parsed = parsed.replace(tzinfo=UTC)
    _aware(parsed, error)
    return parsed


def _safe_ref(value: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError("cyber_feed_unsafe_reference_forbidden")


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_feed_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _model_payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
