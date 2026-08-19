"""Read-only continuous cyber-threat feed runtime for EAY Jarvis.

This layer keeps global defensive knowledge current without confusing public
threat intelligence with company exposure or incident truth. CISA KEV, NVD CVE
and MITRE ATT&CK inputs are normalized into the existing ThreatKnowledgeRecord
contract and can then enter the canonical append-only threat ledger.

The contract deliberately stores only normalized records and observation
receipts. Raw upstream payloads, credentials and request headers are never part
of the durable model. Feed refresh never grants company truth, incident
confirmation, response authority or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.cyber_defense_intelligence import (
    ThreatIntelligenceSource,
    ThreatKnowledgeRecord,
    build_threat_record,
)

CYBER_THREAT_FEED_RUNTIME_CONTRACT = "eay-cyber-threat-feed-runtime-v1"

CISA_KEV_JSON_ENDPOINT = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)
NVD_CVE_API_ENDPOINT = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MITRE_ATTACK_STIX_ENDPOINT = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack.json"
)

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|password|passwd|secret(?:[-_: ]|$)|"
    r"session(?:id)?(?:[-_: ]|$)|cookie(?:[-_: ]|$)|signed[_-]?url|"
    r"x-goog-signature|x-amz-signature|exploit[_-]?payload|reverse[_-]?shell|"
    r"credential[_-]?dump|shellcode)"
)
_CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_CWE_ID = re.compile(r"^CWE-\d+$", re.IGNORECASE)
_ATTACK_ID = re.compile(r"^T\d{4}(?:\.\d{3})?$", re.IGNORECASE)


class ThreatFeedKind(str, Enum):
    CISA_KEV_JSON = "cisa_kev_json"
    NVD_CVE_API = "nvd_cve_api"
    MITRE_ATTACK_STIX = "mitre_attack_stix"


class ThreatFeedObservationStatus(str, Enum):
    SUCCESS = "success"
    NOT_MODIFIED = "not_modified"


class ThreatFeedBinding(BaseModel):
    contract: str = CYBER_THREAT_FEED_RUNTIME_CONTRACT
    feed_id: str = Field(min_length=1)
    kind: ThreatFeedKind
    source: ThreatIntelligenceSource
    endpoint_ref: str = Field(min_length=1)
    poll_interval_seconds: int = Field(gt=0)
    method: str = "GET"
    read_only: bool = True
    raw_payload_retention_allowed: bool = False
    credential_material_retention_allowed: bool = False
    company_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_fixed_read_only_and_non_authoritative(self) -> ThreatFeedBinding:
        expected_source = {
            ThreatFeedKind.CISA_KEV_JSON: ThreatIntelligenceSource.CISA_KEV,
            ThreatFeedKind.NVD_CVE_API: ThreatIntelligenceSource.NVD,
            ThreatFeedKind.MITRE_ATTACK_STIX: ThreatIntelligenceSource.MITRE_ATTACK,
        }[self.kind]
        expected_endpoint = {
            ThreatFeedKind.CISA_KEV_JSON: CISA_KEV_JSON_ENDPOINT,
            ThreatFeedKind.NVD_CVE_API: NVD_CVE_API_ENDPOINT,
            ThreatFeedKind.MITRE_ATTACK_STIX: MITRE_ATTACK_STIX_ENDPOINT,
        }[self.kind]
        if self.source is not expected_source:
            raise ValueError("cyber_feed_source_kind_mismatch")
        if self.endpoint_ref != expected_endpoint:
            raise ValueError("cyber_feed_endpoint_not_reviewed")
        if self.method != "GET" or not self.read_only:
            raise ValueError("cyber_feed_must_be_read_only_get")
        if self.raw_payload_retention_allowed:
            raise ValueError("cyber_feed_raw_payload_retention_forbidden")
        if self.credential_material_retention_allowed:
            raise ValueError("cyber_feed_credential_retention_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_feed_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_feed_never_confirms_company_incident")
        if self.execution_authority_granted:
            raise ValueError("cyber_feed_never_grants_execution_authority")
        for ref in (self.feed_id, self.endpoint_ref):
            _safe_ref(ref, "cyber_feed_unsafe_reference_forbidden")
        _verify(self, "cyber_feed_binding_fingerprint_mismatch")
        return self


class ThreatFeedObservation(BaseModel):
    contract: str = CYBER_THREAT_FEED_RUNTIME_CONTRACT
    observation_id: str = Field(min_length=1)
    feed_id: str = Field(min_length=1)
    binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: ThreatIntelligenceSource
    observed_at: datetime
    status: ThreatFeedObservationStatus
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    normalized_record_count: int = Field(ge=0)
    source_version_ref: str | None = None
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    mutation_detected: bool = False
    company_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_secret_safe_and_non_authoritative(self) -> ThreatFeedObservation:
        _aware(self.observed_at, "cyber_feed_observed_at_requires_timezone")
        if self.status is ThreatFeedObservationStatus.SUCCESS and self.content_sha256 is None:
            raise ValueError("cyber_feed_success_requires_content_digest")
        if self.raw_payload_retained:
            raise ValueError("cyber_feed_observation_raw_payload_forbidden")
        if self.credential_material_retained:
            raise ValueError("cyber_feed_observation_credential_material_forbidden")
        if self.mutation_detected:
            raise ValueError("cyber_feed_observation_mutation_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_feed_observation_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_feed_observation_never_confirms_company_incident")
        if self.execution_authority_granted:
            raise ValueError("cyber_feed_observation_never_grants_execution_authority")
        for ref in (self.observation_id, self.feed_id, self.source_version_ref):
            if ref is not None:
                _safe_ref(ref, "cyber_feed_observation_unsafe_reference_forbidden")
        _verify(self, "cyber_feed_observation_fingerprint_mismatch")
        return self


class ThreatFeedIngestionResult(BaseModel):
    contract: str = CYBER_THREAT_FEED_RUNTIME_CONTRACT
    observation: ThreatFeedObservation
    records: tuple[ThreatKnowledgeRecord, ...]
    raw_payload_retained: bool = False
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_is_normalized_only(self) -> ThreatFeedIngestionResult:
        observation = ThreatFeedObservation.model_validate(
            self.observation.model_dump(mode="json")
        )
        if observation.normalized_record_count != len(self.records):
            raise ValueError("cyber_feed_observation_record_count_mismatch")
        seen: set[str] = set()
        for record in self.records:
            record = ThreatKnowledgeRecord.model_validate(record.model_dump(mode="json"))
            if record.source is not observation.source:
                raise ValueError("cyber_feed_record_source_mismatch")
            if record.record_id in seen:
                raise ValueError("cyber_feed_duplicate_normalized_record_id")
            seen.add(record.record_id)
        if self.raw_payload_retained:
            raise ValueError("cyber_feed_result_raw_payload_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_feed_result_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("cyber_feed_result_never_grants_execution_authority")
        return self


class ThreatFeedRefreshCandidate(BaseModel):
    feed_id: str
    binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    due: bool
    reason: str


class ThreatFeedRefreshPlan(BaseModel):
    contract: str = CYBER_THREAT_FEED_RUNTIME_CONTRACT
    as_of: datetime
    candidates: tuple[ThreatFeedRefreshCandidate, ...]
    due_feed_ids: tuple[str, ...]
    may_run_in_parallel: bool = True
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def plan_is_parallel_but_non_authoritative(self) -> ThreatFeedRefreshPlan:
        _aware(self.as_of, "cyber_feed_refresh_as_of_requires_timezone")
        if not self.may_run_in_parallel:
            raise ValueError("cyber_feed_refresh_is_parallel_by_design")
        if self.execution_authority_granted:
            raise ValueError("cyber_feed_refresh_plan_never_grants_execution_authority")
        expected = tuple(item.feed_id for item in self.candidates if item.due)
        if self.due_feed_ids != expected:
            raise ValueError("cyber_feed_refresh_due_set_mismatch")
        return self


def default_threat_feed_bindings() -> tuple[ThreatFeedBinding, ...]:
    specs = (
        (
            "global-threat-feed:cisa-kev",
            ThreatFeedKind.CISA_KEV_JSON,
            ThreatIntelligenceSource.CISA_KEV,
            CISA_KEV_JSON_ENDPOINT,
            3600,
        ),
        (
            "global-threat-feed:nvd-cve",
            ThreatFeedKind.NVD_CVE_API,
            ThreatIntelligenceSource.NVD,
            NVD_CVE_API_ENDPOINT,
            3600,
        ),
        (
            "global-threat-feed:mitre-attack-enterprise",
            ThreatFeedKind.MITRE_ATTACK_STIX,
            ThreatIntelligenceSource.MITRE_ATTACK,
            MITRE_ATTACK_STIX_ENDPOINT,
            21600,
        ),
    )
    bindings: list[ThreatFeedBinding] = []
    for feed_id, kind, source, endpoint, interval in specs:
        draft = {
            "contract": CYBER_THREAT_FEED_RUNTIME_CONTRACT,
            "feed_id": feed_id,
            "kind": kind.value,
            "source": source.value,
            "endpoint_ref": endpoint,
            "poll_interval_seconds": interval,
            "method": "GET",
            "read_only": True,
            "raw_payload_retention_allowed": False,
            "credential_material_retention_allowed": False,
            "company_truth_authority_granted": False,
            "incident_confirmation_granted": False,
            "execution_authority_granted": False,
        }
        bindings.append(ThreatFeedBinding.model_validate(_sealed(draft)))
    return tuple(bindings)


def build_parallel_threat_feed_refresh_plan(
    *,
    bindings: tuple[ThreatFeedBinding, ...],
    last_success_by_feed: dict[str, datetime],
    as_of: datetime,
) -> ThreatFeedRefreshPlan:
    _aware(as_of, "cyber_feed_refresh_as_of_requires_timezone")
    candidates: list[ThreatFeedRefreshCandidate] = []
    for raw in bindings:
        binding = ThreatFeedBinding.model_validate(raw.model_dump(mode="json"))
        last = last_success_by_feed.get(binding.feed_id)
        if last is None:
            due, reason = True, "never_observed"
        else:
            _aware(last, "cyber_feed_last_success_requires_timezone")
            if last > as_of:
                raise ValueError("cyber_feed_last_success_future_known_forbidden")
            due = (as_of - last).total_seconds() >= binding.poll_interval_seconds
            reason = "poll_interval_elapsed" if due else "fresh_enough"
        candidates.append(
            ThreatFeedRefreshCandidate(
                feed_id=binding.feed_id,
                binding_fingerprint=binding.fingerprint,
                due=due,
                reason=reason,
            )
        )
    return ThreatFeedRefreshPlan(
        as_of=as_of,
        candidates=tuple(candidates),
        due_feed_ids=tuple(item.feed_id for item in candidates if item.due),
        may_run_in_parallel=True,
        execution_authority_granted=False,
    )


def build_nvd_incremental_params(
    *,
    start_at: datetime,
    end_at: datetime,
    start_index: int = 0,
    results_per_page: int = 2000,
) -> dict[str, str | int]:
    _aware(start_at, "cyber_feed_nvd_start_requires_timezone")
    _aware(end_at, "cyber_feed_nvd_end_requires_timezone")
    if end_at < start_at:
        raise ValueError("cyber_feed_nvd_window_reversed")
    if end_at - start_at > timedelta(days=120):
        raise ValueError("cyber_feed_nvd_window_exceeds_120_days")
    if start_index < 0:
        raise ValueError("cyber_feed_nvd_start_index_negative")
    if not 1 <= results_per_page <= 2000:
        raise ValueError("cyber_feed_nvd_results_per_page_out_of_range")
    return {
        "lastModStartDate": _iso(start_at),
        "lastModEndDate": _iso(end_at),
        "startIndex": start_index,
        "resultsPerPage": results_per_page,
    }


def ingest_threat_feed_payload(
    *,
    binding: ThreatFeedBinding,
    payload: dict[str, Any],
    observed_at: datetime,
    http_status: int = 200,
    source_version_ref: str | None = None,
) -> ThreatFeedIngestionResult:
    binding = ThreatFeedBinding.model_validate(binding.model_dump(mode="json"))
    _aware(observed_at, "cyber_feed_observed_at_requires_timezone")
    if http_status != 200:
        raise ValueError("cyber_feed_http_status_not_success")
    if source_version_ref is not None:
        _safe_ref(source_version_ref, "cyber_feed_source_version_unsafe")

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    evidence_ref = f"threat-feed-observation:{binding.feed_id}:{digest[:24]}"

    if binding.kind is ThreatFeedKind.CISA_KEV_JSON:
        records = _normalize_cisa_kev(
            payload=payload,
            observed_at=observed_at,
            evidence_ref=evidence_ref,
        )
        inferred_version = payload.get("catalogVersion")
    elif binding.kind is ThreatFeedKind.NVD_CVE_API:
        records = _normalize_nvd(
            payload=payload,
            observed_at=observed_at,
            evidence_ref=evidence_ref,
        )
        inferred_version = payload.get("version") or payload.get("timestamp")
    else:
        records = _normalize_mitre_attack(
            payload=payload,
            observed_at=observed_at,
            evidence_ref=evidence_ref,
        )
        inferred_version = _mitre_bundle_version(payload)

    version = source_version_ref or (
        f"source-version:{_slug(str(inferred_version))}" if inferred_version else None
    )
    observation_id = f"threat-feed:{binding.kind.value}:{digest[:24]}"
    draft = {
        "contract": CYBER_THREAT_FEED_RUNTIME_CONTRACT,
        "observation_id": observation_id,
        "feed_id": binding.feed_id,
        "binding_fingerprint": binding.fingerprint,
        "source": binding.source.value,
        "observed_at": _iso(observed_at),
        "status": ThreatFeedObservationStatus.SUCCESS.value,
        "content_sha256": digest,
        "normalized_record_count": len(records),
        "source_version_ref": version,
        "raw_payload_retained": False,
        "credential_material_retained": False,
        "mutation_detected": False,
        "company_truth_authority_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    observation = ThreatFeedObservation.model_validate(_sealed(draft))
    return ThreatFeedIngestionResult(observation=observation, records=records)


def _normalize_cisa_kev(
    *, payload: dict[str, Any], observed_at: datetime, evidence_ref: str
) -> tuple[ThreatKnowledgeRecord, ...]:
    raw_items = payload.get("vulnerabilities")
    if not isinstance(raw_items, list):
        raise TypeError("cyber_feed_cisa_vulnerabilities_missing")
    records: list[ThreatKnowledgeRecord] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise TypeError("cyber_feed_cisa_item_invalid")
        cve = _required_cve(item.get("cveID"))
        published_at = _date_to_datetime(item.get("dateAdded"))
        vendor = _slug(str(item.get("vendorProject") or "unknown-vendor"))
        product = _slug(str(item.get("product") or "unknown-product"))
        cwes = _normalized_cwes(item.get("cwes") or ())
        records.append(
            build_threat_record(
                record_id=f"cisa-kev:{cve}",
                source=ThreatIntelligenceSource.CISA_KEV,
                source_record_id=cve,
                published_at=published_at,
                recorded_at=observed_at,
                source_evidence_ref=evidence_ref,
                product_refs=(f"product:{vendor}:{product}",),
                cve_ids=(cve,),
                cwe_ids=cwes,
                known_exploited_in_wild=True,
                inference_only=False,
            )
        )
    return _unique_records(records)


def _normalize_nvd(
    *, payload: dict[str, Any], observed_at: datetime, evidence_ref: str
) -> tuple[ThreatKnowledgeRecord, ...]:
    raw_items = payload.get("vulnerabilities")
    if not isinstance(raw_items, list):
        raise TypeError("cyber_feed_nvd_vulnerabilities_missing")
    records: list[ThreatKnowledgeRecord] = []
    for wrapper in raw_items:
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("cve"), dict):
            raise TypeError("cyber_feed_nvd_item_invalid")
        cve_obj = wrapper["cve"]
        cve = _required_cve(cve_obj.get("id"))
        published_at = _parse_datetime(cve_obj.get("published"))
        records.append(
            build_threat_record(
                record_id=f"nvd:{cve}",
                source=ThreatIntelligenceSource.NVD,
                source_record_id=cve,
                published_at=published_at,
                recorded_at=observed_at,
                source_evidence_ref=evidence_ref,
                cve_ids=(cve,),
                cwe_ids=_extract_nvd_cwes(cve_obj),
                severity_score=_extract_nvd_severity(cve_obj),
                known_exploited_in_wild=False,
                inference_only=False,
            )
        )
    return _unique_records(records)


def _normalize_mitre_attack(
    *, payload: dict[str, Any], observed_at: datetime, evidence_ref: str
) -> tuple[ThreatKnowledgeRecord, ...]:
    raw_items = payload.get("objects")
    if not isinstance(raw_items, list):
        raise TypeError("cyber_feed_mitre_objects_missing")
    records: list[ThreatKnowledgeRecord] = []
    for item in raw_items:
        if not isinstance(item, dict) or item.get("type") != "attack-pattern":
            continue
        if item.get("revoked") is True or item.get("x_mitre_deprecated") is True:
            continue
        technique_id = _mitre_external_id(item)
        if technique_id is None:
            continue
        source_id = str(item.get("id") or technique_id)
        created = _parse_datetime(item.get("created"))
        platforms = tuple(
            f"platform:{_slug(str(value))}"
            for value in item.get("x_mitre_platforms", ())
            if str(value).strip()
        )
        records.append(
            build_threat_record(
                record_id=f"mitre-attack:{technique_id}",
                source=ThreatIntelligenceSource.MITRE_ATTACK,
                source_record_id=source_id,
                published_at=created,
                recorded_at=observed_at,
                source_evidence_ref=evidence_ref,
                product_refs=tuple(dict.fromkeys(platforms)),
                attack_technique_ids=(technique_id,),
                known_exploited_in_wild=False,
                inference_only=False,
            )
        )
    return _unique_records(records)


def _extract_nvd_severity(cve_obj: dict[str, Any]) -> float | None:
    metrics = cve_obj.get("metrics")
    if not isinstance(metrics, dict):
        return None
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(key)
        if not isinstance(values, list):
            continue
        for metric in values:
            if not isinstance(metric, dict):
                continue
            data = metric.get("cvssData")
            if isinstance(data, dict) and isinstance(data.get("baseScore"), (int, float)):
                return float(data["baseScore"])
    return None


def _extract_nvd_cwes(cve_obj: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    weaknesses = cve_obj.get("weaknesses")
    if not isinstance(weaknesses, list):
        return ()
    for weakness in weaknesses:
        if not isinstance(weakness, dict):
            continue
        descriptions = weakness.get("description")
        if not isinstance(descriptions, list):
            continue
        for description in descriptions:
            if not isinstance(description, dict):
                continue
            value = str(description.get("value") or "").upper()
            if _CWE_ID.match(value):
                values.append(value)
    return tuple(dict.fromkeys(values))


def _mitre_external_id(item: dict[str, Any]) -> str | None:
    refs = item.get("external_references")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if not isinstance(ref, dict) or ref.get("source_name") != "mitre-attack":
            continue
        value = str(ref.get("external_id") or "").upper()
        if _ATTACK_ID.match(value):
            return value
    return None


def _mitre_bundle_version(payload: dict[str, Any]) -> str | None:
    value = payload.get("x_mitre_version") or payload.get("spec_version")
    if value:
        return str(value)
    return None


def _required_cve(value: Any) -> str:
    normalized = str(value or "").upper()
    if not _CVE_ID.match(normalized):
        raise ValueError("cyber_feed_invalid_cve_id")
    return normalized


def _normalized_cwes(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    normalized = [str(value).upper() for value in values]
    return tuple(dict.fromkeys(value for value in normalized if _CWE_ID.match(value)))


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cyber_feed_datetime_missing")
    candidate = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _date_to_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("cyber_feed_date_missing")
    parsed = date.fromisoformat(value)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _unique_records(records: list[ThreatKnowledgeRecord]) -> tuple[ThreatKnowledgeRecord, ...]:
    seen: set[str] = set()
    output: list[ThreatKnowledgeRecord] = []
    for record in records:
        if record.record_id in seen:
            raise ValueError("cyber_feed_duplicate_normalized_record_id")
        seen.add(record.record_id)
        output.append(record)
    return tuple(output)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    return result or "unknown"


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_feed_datetime_requires_timezone")
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
