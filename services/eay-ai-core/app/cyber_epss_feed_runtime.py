"""Read-only FIRST EPSS lookup runtime for EAY Jarvis cyber defense.

EPSS is an exploitation-likelihood enrichment, not vulnerability truth and never
company risk. This adapter therefore emits EpssObservation objects instead of
forcing EPSS into the canonical ThreatKnowledgeRecord source enum.

The runtime is intentionally narrow:
- exact reviewed FIRST endpoint and GET-only lookup;
- bounded CVE batches using the API's query-length constraint;
- no raw payload, credentials or headers retained;
- unexpected/duplicate CVEs fail closed;
- missing requested CVEs remain explicit;
- no exploitation confirmation, company truth or execution authority is granted.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_threat_enrichment_intelligence import (
    EpssObservation,
    build_epss_observation,
)

CYBER_EPSS_FEED_RUNTIME_CONTRACT = "eay-cyber-epss-feed-runtime-v1"
FIRST_EPSS_API_ENDPOINT = "https://api.first.org/data/v1/epss"
FIRST_EPSS_MAX_CVE_QUERY_CHARS = 2000

_CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class EpssFeedBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_EPSS_FEED_RUNTIME_CONTRACT
    feed_id: str = "global-threat-feed:first-epss"
    endpoint_ref: str = FIRST_EPSS_API_ENDPOINT
    method: str = "GET"
    lookup_only: bool = True
    bulk_mirror_allowed: bool = False
    raw_payload_retention_allowed: bool = False
    credential_material_retention_allowed: bool = False
    exploitation_confirmation_granted: bool = False
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_exact_read_only_lookup(self) -> EpssFeedBinding:
        if self.endpoint_ref != FIRST_EPSS_API_ENDPOINT:
            raise ValueError("cyber_epss_feed_endpoint_not_reviewed")
        if self.method != "GET":
            raise ValueError("cyber_epss_feed_must_use_get")
        if not self.lookup_only:
            raise ValueError("cyber_epss_feed_must_remain_lookup_only")
        if self.bulk_mirror_allowed:
            raise ValueError("cyber_epss_feed_bulk_mirror_forbidden")
        if self.raw_payload_retention_allowed:
            raise ValueError("cyber_epss_feed_raw_payload_retention_forbidden")
        if self.credential_material_retention_allowed:
            raise ValueError("cyber_epss_feed_credential_retention_forbidden")
        if self.exploitation_confirmation_granted:
            raise ValueError("cyber_epss_feed_never_confirms_exploitation")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_epss_feed_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("cyber_epss_feed_never_grants_execution_authority")
        for ref in (self.feed_id, self.endpoint_ref):
            _safe_ref(ref, "cyber_epss_feed_unsafe_reference_forbidden")
        _verify(self, "cyber_epss_feed_binding_fingerprint_mismatch")
        return self


class EpssFeedObservationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_EPSS_FEED_RUNTIME_CONTRACT
    observation_id: str = Field(min_length=1)
    feed_id: str = Field(min_length=1)
    binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    requested_cve_ids: tuple[str, ...] = Field(min_length=1)
    returned_cve_ids: tuple[str, ...]
    missing_cve_ids: tuple[str, ...]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    api_version_ref: str | None = None
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    exploitation_confirmation_granted: bool = False
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_bounded_and_non_authoritative(self) -> EpssFeedObservationReceipt:
        _aware(self.observed_at, "cyber_epss_feed_observed_at_requires_timezone")
        _unique(self.requested_cve_ids, "cyber_epss_feed_requested_cves_must_be_unique")
        _unique(self.returned_cve_ids, "cyber_epss_feed_returned_cves_must_be_unique")
        _unique(self.missing_cve_ids, "cyber_epss_feed_missing_cves_must_be_unique")
        requested = set(self.requested_cve_ids)
        returned = set(self.returned_cve_ids)
        missing = set(self.missing_cve_ids)
        if returned - requested:
            raise ValueError("cyber_epss_feed_returned_unrequested_cve")
        if missing != requested - returned:
            raise ValueError("cyber_epss_feed_missing_set_mismatch")
        if self.raw_payload_retained:
            raise ValueError("cyber_epss_feed_observation_raw_payload_forbidden")
        if self.credential_material_retained:
            raise ValueError("cyber_epss_feed_observation_credential_material_forbidden")
        if self.exploitation_confirmation_granted:
            raise ValueError("cyber_epss_feed_observation_never_confirms_exploitation")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_epss_feed_observation_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("cyber_epss_feed_observation_never_grants_execution_authority")
        for cve_id in (*self.requested_cve_ids, *self.returned_cve_ids):
            _cve(cve_id, "cyber_epss_feed_invalid_cve_id")
        for ref in (self.observation_id, self.feed_id, self.api_version_ref):
            if ref is not None:
                _safe_ref(ref, "cyber_epss_feed_observation_unsafe_reference_forbidden")
        _verify(self, "cyber_epss_feed_observation_fingerprint_mismatch")
        return self


class EpssFeedIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_EPSS_FEED_RUNTIME_CONTRACT
    receipt: EpssFeedObservationReceipt
    observations: tuple[EpssObservation, ...]
    raw_payload_retained: bool = False
    company_truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_contains_only_normalized_likelihood_observations(
        self,
    ) -> EpssFeedIngestionResult:
        receipt = EpssFeedObservationReceipt.model_validate(
            self.receipt.model_dump(mode="json")
        )
        observed_ids = tuple(item.cve_id for item in self.observations)
        if tuple(sorted(observed_ids)) != tuple(sorted(receipt.returned_cve_ids)):
            raise ValueError("cyber_epss_feed_observation_set_mismatch")
        for item in self.observations:
            EpssObservation.model_validate(item.model_dump(mode="json"))
        if self.raw_payload_retained:
            raise ValueError("cyber_epss_feed_result_raw_payload_forbidden")
        if self.company_truth_authority_granted:
            raise ValueError("cyber_epss_feed_result_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("cyber_epss_feed_result_never_grants_execution_authority")
        return self


def default_epss_feed_binding() -> EpssFeedBinding:
    draft = {
        "contract": CYBER_EPSS_FEED_RUNTIME_CONTRACT,
        "feed_id": "global-threat-feed:first-epss",
        "endpoint_ref": FIRST_EPSS_API_ENDPOINT,
        "method": "GET",
        "lookup_only": True,
        "bulk_mirror_allowed": False,
        "raw_payload_retention_allowed": False,
        "credential_material_retention_allowed": False,
        "exploitation_confirmation_granted": False,
        "company_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    return EpssFeedBinding.model_validate(_sealed(draft))


def build_epss_lookup_params(
    *,
    cve_ids: tuple[str, ...],
    score_date: date | None = None,
) -> dict[str, str]:
    if not cve_ids:
        raise ValueError("cyber_epss_feed_requires_cve_ids")
    _unique(cve_ids, "cyber_epss_feed_requested_cves_must_be_unique")
    for cve_id in cve_ids:
        _cve(cve_id, "cyber_epss_feed_invalid_cve_id")
    joined = ",".join(cve_ids)
    if len(joined) > FIRST_EPSS_MAX_CVE_QUERY_CHARS:
        raise ValueError("cyber_epss_feed_cve_query_exceeds_first_limit")
    params = {"cve": joined}
    if score_date is not None:
        params["date"] = score_date.isoformat()
    return params


def ingest_epss_api_payload(
    *,
    binding: EpssFeedBinding,
    requested_cve_ids: tuple[str, ...],
    payload: dict[str, Any],
    observed_at: datetime,
    http_status: int = 200,
) -> EpssFeedIngestionResult:
    binding = EpssFeedBinding.model_validate(binding.model_dump(mode="json"))
    _aware(observed_at, "cyber_epss_feed_observed_at_requires_timezone")
    build_epss_lookup_params(cve_ids=requested_cve_ids)
    if http_status < 200 or http_status >= 300:
        raise ValueError("cyber_epss_feed_http_status_not_success")
    if payload.get("status") != "OK":
        raise ValueError("cyber_epss_feed_upstream_status_not_ok")
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        raise TypeError("cyber_epss_feed_data_list_required")

    requested = set(requested_cve_ids)
    observations: list[EpssObservation] = []
    seen: set[str] = set()
    for raw in raw_data:
        if not isinstance(raw, dict):
            raise TypeError("cyber_epss_feed_data_item_must_be_object")
        cve_id = str(raw.get("cve", "")).upper()
        _cve(cve_id, "cyber_epss_feed_invalid_cve_id")
        if cve_id not in requested:
            raise ValueError("cyber_epss_feed_returned_unrequested_cve")
        if cve_id in seen:
            raise ValueError("cyber_epss_feed_duplicate_cve")
        seen.add(cve_id)
        score_date = _score_date(raw)
        try:
            score = float(raw["epss"])
            percentile = float(raw["percentile"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("cyber_epss_feed_invalid_probability_fields") from exc
        source_ref = f"first-epss:{cve_id}:{score_date.isoformat()}"
        observations.append(
            build_epss_observation(
                cve_id=cve_id,
                score=score,
                percentile=percentile,
                score_date=score_date,
                observed_at=observed_at,
                recorded_at=observed_at,
                source_evidence_ref=source_ref,
            )
        )

    returned_ids = tuple(sorted(seen))
    missing_ids = tuple(sorted(requested - seen))
    content_digest = _fingerprint(payload)
    version = payload.get("version")
    api_version_ref = (
        f"first-epss-api:v{version}" if isinstance(version, str) and version else None
    )
    receipt_seed = {
        "feed": binding.fingerprint,
        "observed_at": _iso(observed_at),
        "requested_cves": sorted(requested_cve_ids),
        "content_sha256": content_digest,
    }
    observation_id = f"epss-feed-observation:{_fingerprint(receipt_seed)[:24]}"
    draft = {
        "contract": CYBER_EPSS_FEED_RUNTIME_CONTRACT,
        "observation_id": observation_id,
        "feed_id": binding.feed_id,
        "binding_fingerprint": binding.fingerprint,
        "observed_at": _iso(observed_at),
        "requested_cve_ids": list(requested_cve_ids),
        "returned_cve_ids": list(returned_ids),
        "missing_cve_ids": list(missing_ids),
        "content_sha256": content_digest,
        "api_version_ref": api_version_ref,
        "raw_payload_retained": False,
        "credential_material_retained": False,
        "exploitation_confirmation_granted": False,
        "company_truth_authority_granted": False,
        "execution_authority_granted": False,
    }
    receipt = EpssFeedObservationReceipt.model_validate(_sealed(draft))
    return EpssFeedIngestionResult(
        receipt=receipt,
        observations=tuple(observations),
        raw_payload_retained=False,
        company_truth_authority_granted=False,
        execution_authority_granted=False,
    )


def _score_date(raw: dict[str, Any]) -> date:
    value = raw.get("date")
    if value is None:
        value = raw.get("created")
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("cyber_epss_feed_score_date_required")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError("cyber_epss_feed_score_date_invalid") from exc


def _cve(value: str, error: str) -> None:
    if not _CVE_ID.fullmatch(value):
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_epss_feed_datetime_requires_timezone")
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
