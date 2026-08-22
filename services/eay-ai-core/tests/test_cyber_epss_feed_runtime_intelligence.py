from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.cyber_epss_feed_runtime import (
    FIRST_EPSS_API_ENDPOINT,
    FIRST_EPSS_MAX_CVE_QUERY_CHARS,
    EpssFeedBinding,
    EpssFeedObservationReceipt,
    build_epss_lookup_params,
    default_epss_feed_binding,
    ingest_epss_api_payload,
)

NOW = datetime(2026, 8, 19, 19, 0, tzinfo=UTC)


def _payload():
    return {
        "status": "OK",
        "status-code": 200,
        "version": "1.0",
        "total": 2,
        "data": [
            {
                "cve": "CVE-2026-9001",
                "epss": "0.912340000",
                "percentile": "0.990000000",
                "date": "2026-08-19",
            },
            {
                "cve": "CVE-2026-9002",
                "epss": "0.031000000",
                "percentile": "0.420000000",
                "created": "2026-08-19T00:00:00+00:00",
            },
        ],
    }


def test_default_epss_binding_is_exact_read_only_lookup():
    binding = default_epss_feed_binding()
    assert binding.endpoint_ref == FIRST_EPSS_API_ENDPOINT
    assert binding.method == "GET"
    assert binding.lookup_only is True
    assert binding.bulk_mirror_allowed is False
    assert binding.raw_payload_retention_allowed is False
    assert binding.credential_material_retention_allowed is False
    assert binding.exploitation_confirmation_granted is False
    assert binding.company_truth_authority_granted is False
    assert binding.execution_authority_granted is False


def test_epss_endpoint_cannot_be_model_swapped():
    binding = default_epss_feed_binding()
    tampered = binding.model_copy(update={"endpoint_ref": "https://example.invalid/epss"})
    with pytest.raises(ValidationError, match="cyber_epss_feed_endpoint_not_reviewed"):
        EpssFeedBinding.model_validate(tampered.model_dump(mode="json"))


def test_lookup_params_are_exact_bounded_cve_queries():
    params = build_epss_lookup_params(
        cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
        score_date=date(2026, 8, 19),
    )
    assert params == {
        "cve": "CVE-2026-9001,CVE-2026-9002",
        "date": "2026-08-19",
    }


def test_lookup_params_reject_duplicates_invalid_ids_and_overlong_query():
    with pytest.raises(ValueError, match="cyber_epss_feed_requested_cves_must_be_unique"):
        build_epss_lookup_params(cve_ids=("CVE-2026-9001", "CVE-2026-9001"))
    with pytest.raises(ValueError, match="cyber_epss_feed_invalid_cve_id"):
        build_epss_lookup_params(cve_ids=("not-a-cve",))
    many = tuple(f"CVE-2026-{10000 + index}" for index in range(200))
    assert len(",".join(many)) > FIRST_EPSS_MAX_CVE_QUERY_CHARS
    with pytest.raises(ValueError, match="cyber_epss_feed_cve_query_exceeds_first_limit"):
        build_epss_lookup_params(cve_ids=many)


def test_epss_payload_normalizes_probability_observations_without_company_truth():
    result = ingest_epss_api_payload(
        binding=default_epss_feed_binding(),
        requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
        payload=_payload(),
        observed_at=NOW,
    )
    assert len(result.observations) == 2
    first = next(item for item in result.observations if item.cve_id == "CVE-2026-9001")
    assert first.score == pytest.approx(0.91234)
    assert first.percentile == pytest.approx(0.99)
    assert first.score_date == date(2026, 8, 19)
    assert first.exploitation_confirmed is False
    assert first.company_truth_granted is False
    assert result.receipt.returned_cve_ids == ("CVE-2026-9001", "CVE-2026-9002")
    assert result.receipt.missing_cve_ids == ()
    assert result.receipt.raw_payload_retained is False
    assert result.execution_authority_granted is False


def test_missing_requested_cve_is_explicit_not_silently_filled():
    payload = _payload()
    payload["data"] = payload["data"][:1]
    result = ingest_epss_api_payload(
        binding=default_epss_feed_binding(),
        requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
        payload=payload,
        observed_at=NOW,
    )
    assert result.receipt.returned_cve_ids == ("CVE-2026-9001",)
    assert result.receipt.missing_cve_ids == ("CVE-2026-9002",)


def test_unrequested_or_duplicate_cve_fails_closed():
    payload = _payload()
    with pytest.raises(ValueError, match="cyber_epss_feed_returned_unrequested_cve"):
        ingest_epss_api_payload(
            binding=default_epss_feed_binding(),
            requested_cve_ids=("CVE-2026-9001",),
            payload=payload,
            observed_at=NOW,
        )
    duplicate = _payload()
    duplicate["data"].append(dict(duplicate["data"][0]))
    with pytest.raises(ValueError, match="cyber_epss_feed_duplicate_cve"):
        ingest_epss_api_payload(
            binding=default_epss_feed_binding(),
            requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
            payload=duplicate,
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    ("http_status", "upstream_status", "expected"),
    [
        (500, "OK", "cyber_epss_feed_http_status_not_success"),
        (200, "ERROR", "cyber_epss_feed_upstream_status_not_ok"),
    ],
)
def test_failed_upstream_observation_is_not_ingested(
    http_status: int,
    upstream_status: str,
    expected: str,
):
    payload = _payload()
    payload["status"] = upstream_status
    with pytest.raises(ValueError, match=expected):
        ingest_epss_api_payload(
            binding=default_epss_feed_binding(),
            requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
            payload=payload,
            observed_at=NOW,
            http_status=http_status,
        )


def test_future_score_date_fails_closed():
    payload = _payload()
    payload["data"][0]["date"] = "2026-08-20"
    with pytest.raises(ValidationError, match="cyber_epss_score_date_after_observation"):
        ingest_epss_api_payload(
            binding=default_epss_feed_binding(),
            requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
            payload=payload,
            observed_at=NOW,
        )


def test_receipt_tamper_cannot_hide_missing_cve():
    payload = _payload()
    payload["data"] = payload["data"][:1]
    result = ingest_epss_api_payload(
        binding=default_epss_feed_binding(),
        requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
        payload=payload,
        observed_at=NOW,
    )
    tampered = result.receipt.model_copy(update={"missing_cve_ids": ()})
    with pytest.raises(ValidationError):
        EpssFeedObservationReceipt.model_validate(tampered.model_dump(mode="json"))


def test_epss_adapter_does_not_accept_raw_payload_or_execution_authority_fields():
    result = ingest_epss_api_payload(
        binding=default_epss_feed_binding(),
        requested_cve_ids=("CVE-2026-9001", "CVE-2026-9002"),
        payload=_payload(),
        observed_at=NOW,
    )
    payload = result.receipt.model_dump(mode="json")
    payload["raw_payload_retained"] = True
    with pytest.raises(
        ValidationError,
        match="cyber_epss_feed_observation_raw_payload_forbidden",
    ):
        EpssFeedObservationReceipt.model_validate(payload)
