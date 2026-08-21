from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_live_schema_collector import (
    OrdersV2LiveSchemaCollectorConfig,
    OrdersV2LiveSchemaCollectorResultError,
)
from app.core.ai_orders_v2_source_comparison import (
    CANDIDATE_SOURCE,
    DIRECTIVE_SOURCE,
    REQUIRED_FIELD_PATHS,
    SOURCE_COMPARISON_QUERY,
    SOURCE_COMPARISON_TIMEOUT_SECONDS,
    OrdersV2SourceComparisonObservation,
    collect_orders_v2_source_comparison,
)


class FakeJob:
    def __init__(self, rows):
        self.rows = rows
        self.timeouts = []

    def result(self, *, timeout=None):
        self.timeouts.append(timeout)
        return list(self.rows)


class FakeClient:
    project = "example-project"
    location = "EU"

    def __init__(self, rows):
        self.job = FakeJob(rows)
        self.calls: list[dict[str, Any]] = []

    def query(self, query, *, job_config, location=None):
        self.calls.append(
            {"query": query, "job_config": job_config, "location": location}
        )
        return self.job


def matrix_rows(*, missing=None):
    rows = []
    for source in (CANDIDATE_SOURCE, DIRECTIVE_SOURCE):
        for field in REQUIRED_FIELD_PATHS:
            is_missing = missing == (source, field)
            rows.append(
                {
                    "source_table": source,
                    "field_path": field,
                    "data_type": None if is_missing else "STRING",
                    "present": not is_missing,
                }
            )
    return rows


def config():
    return OrdersV2LiveSchemaCollectorConfig(
        project="example-project",
        location="EU",
    )


def test_source_comparison_query_uses_valid_bigquery_backtick_identifiers() -> None:
    assert (
        "`curated_data_shared_coredata_business.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`"
        in SOURCE_COMPARISON_QUERY
    )
    assert (
        "`curated_data_shared.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`"
        in SOURCE_COMPARISON_QUERY
    )
    assert "\\`" not in SOURCE_COMPARISON_QUERY


def test_source_comparison_is_fixed_bounded_and_non_promoting() -> None:
    client = FakeClient(matrix_rows())
    artifact = collect_orders_v2_source_comparison(
        client=client,
        config=config(),
        observed_at=datetime(2026, 8, 14, 0, 0, tzinfo=UTC),
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["query"] == SOURCE_COMPARISON_QUERY
    assert call["location"] == "EU"
    assert call["job_config"].use_legacy_sql is False
    assert call["job_config"].use_query_cache is False
    assert call["job_config"].maximum_bytes_billed == 100_000_000
    assert client.job.timeouts == [SOURCE_COMPARISON_TIMEOUT_SECONDS]
    assert len(artifact.fields) == 10
    assert artifact.source_authority_decided is False
    assert artifact.candidate_mutation_permitted is False
    assert artifact.promotion_eligible is False
    assert artifact.production_ready is False
    assert len(artifact.observation_fingerprint) == 64


def test_source_comparison_records_missing_field_without_selecting_source() -> None:
    missing = (DIRECTIVE_SOURCE, "partition_date_local")
    artifact = collect_orders_v2_source_comparison(
        client=FakeClient(matrix_rows(missing=missing)),
        config=config(),
    )

    item = next(
        field
        for field in artifact.fields
        if (field.source_table, field.field_path) == missing
    )
    assert item.present is False
    assert item.data_type is None
    assert artifact.source_authority_decided is False


def test_source_comparison_rejects_incomplete_or_duplicate_matrix() -> None:
    for rows in (matrix_rows()[:-1], matrix_rows() + matrix_rows()[:1]):
        with pytest.raises(
            OrdersV2LiveSchemaCollectorResultError,
            match="matrix",
        ):
            collect_orders_v2_source_comparison(
                client=FakeClient(rows),
                config=config(),
            )


def test_source_comparison_rejects_presence_type_disagreement() -> None:
    rows = matrix_rows()
    rows[0]["present"] = False
    with pytest.raises(ValidationError, match="presence"):
        collect_orders_v2_source_comparison(
            client=FakeClient(rows),
            config=config(),
        )


def test_source_comparison_artifact_cannot_self_promote() -> None:
    artifact = collect_orders_v2_source_comparison(
        client=FakeClient(matrix_rows()),
        config=config(),
    )
    for field, value in (
        ("source_authority_decided", True),
        ("candidate_mutation_permitted", True),
        ("promotion_eligible", True),
        ("production_ready", True),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2SourceComparisonObservation.model_validate(payload)
