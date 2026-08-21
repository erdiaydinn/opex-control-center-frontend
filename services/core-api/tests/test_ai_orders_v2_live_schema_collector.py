from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest
from google.cloud import bigquery
from pydantic import ValidationError

from app.core.ai_orders_v2_live_schema_collector import (
    EAY_BQ_LOCATION_ENV,
    EAY_BQ_PROJECT_ENV,
    SCHEMA_COLLECTOR_TIMEOUT_SECONDS,
    OrdersV2CollectedSchemaObservation,
    OrdersV2LiveSchemaCollectorConfig,
    OrdersV2LiveSchemaCollectorConfigError,
    OrdersV2LiveSchemaCollectorResultError,
    collect_orders_v2_schema_observation,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_evidence import (
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY,
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256,
)
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


class FakeJob:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.timeouts: list[float | None] = []
        self.error: Exception | None = None

    def result(self, *, timeout: float | None = None):
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        return list(self.rows)


class FakeClient:
    def __init__(
        self,
        *,
        project: str = "example-project",
        location: str | None = "EU",
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.project = project
        self.location = location
        actual_rows = [metadata_row(project=project)] if rows is None else rows
        self.job = FakeJob(actual_rows)
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def query(
        self,
        query: str,
        *,
        job_config: Any,
        location: str | None = None,
    ) -> FakeJob:
        self.calls.append(
            {
                "query": query,
                "job_config": job_config,
                "location": location,
            }
        )
        if self.error is not None:
            raise self.error
        return self.job


def metadata_row(*, project: str = "example-project") -> dict[str, str]:
    return {
        "table_catalog": project,
        "table_schema": "curated_data_shared_coredata_business",
        "table_name": "orders",
        "column_name": "entity",
        "field_path": "entity.id",
        "data_type": "STRING",
    }


def config() -> OrdersV2LiveSchemaCollectorConfig:
    return OrdersV2LiveSchemaCollectorConfig(
        project="example-project",
        location="EU",
    )


def test_config_reuses_frozen_eay_bigquery_environment_names() -> None:
    assert EAY_BQ_PROJECT_ENV == "EAY_BQ_PROJECT"
    assert EAY_BQ_LOCATION_ENV == "EAY_BQ_LOCATION"

    parsed = OrdersV2LiveSchemaCollectorConfig.from_environment(
        {
            "EAY_BQ_PROJECT": "  example-project  ",
            "EAY_BQ_LOCATION": "  EU  ",
        }
    )
    assert parsed == config()

    for environ in (
        {},
        {"EAY_BQ_PROJECT": ""},
        {"EAY_BQ_PROJECT": "example project"},
        {"EAY_BQ_PROJECT": "example-project;DROP"},
    ):
        with pytest.raises(OrdersV2LiveSchemaCollectorConfigError):
            OrdersV2LiveSchemaCollectorConfig.from_environment(environ)


def test_public_collector_api_exposes_no_query_shape_override() -> None:
    parameters = inspect.signature(
        collect_orders_v2_schema_observation
    ).parameters
    assert tuple(parameters) == ("client", "config", "observed_at")

    for forbidden in (
        "sql",
        "query",
        "table_name",
        "field_path",
        "data_type",
        "query_parameters",
        "parameter_types",
    ):
        assert forbidden not in parameters


def test_collector_submits_one_exact_read_only_metadata_query() -> None:
    client = FakeClient()
    timestamp = datetime(2026, 8, 13, 5, 30, tzinfo=UTC)
    observation = collect_orders_v2_schema_observation(
        client=client,
        config=config(),
        observed_at=timestamp,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["query"] == ORDERS_V2_SCHEMA_EVIDENCE_QUERY
    assert call["location"] == "EU"

    job_config = call["job_config"]
    assert isinstance(job_config, bigquery.QueryJobConfig)
    assert job_config.use_legacy_sql is False
    assert [
        parameter.to_api_repr()
        for parameter in job_config.query_parameters
    ] == [
        {
            "name": "table_name",
            "parameterType": {"type": "STRING"},
            "parameterValue": {"value": "orders"},
        },
        {
            "name": "field_path",
            "parameterType": {"type": "STRING"},
            "parameterValue": {"value": "entity.id"},
        },
    ]
    assert client.job.timeouts == [SCHEMA_COLLECTOR_TIMEOUT_SECONDS]
    assert observation.provenance_kind == "collector_observation_unattested"
    assert observation.attested_live_run is False
    assert observation.metadata_row_count == 1
    assert observation.evidence.table_catalog == "example-project"
    assert observation.evidence.collector_query_sha256 == (
        ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256
    )
    assert observation.evidence.observed_at == timestamp


def test_collector_requires_exactly_one_metadata_row() -> None:
    for rows in ([], [metadata_row(), metadata_row()]):
        with pytest.raises(
            OrdersV2LiveSchemaCollectorResultError,
            match="exactly one row",
        ):
            collect_orders_v2_schema_observation(
                client=FakeClient(rows=rows),
                config=config(),
            )


def test_collector_binds_client_metadata_project_and_location() -> None:
    with pytest.raises(OrdersV2LiveSchemaCollectorConfigError):
        collect_orders_v2_schema_observation(
            client=FakeClient(project="other-project"),
            config=config(),
        )

    with pytest.raises(OrdersV2LiveSchemaCollectorConfigError):
        collect_orders_v2_schema_observation(
            client=FakeClient(location="US"),
            config=config(),
        )

    with pytest.raises(
        OrdersV2LiveSchemaCollectorResultError,
        match="table_catalog",
    ):
        collect_orders_v2_schema_observation(
            client=FakeClient(
                rows=[metadata_row(project="other-project")]
            ),
            config=config(),
        )


def test_query_or_result_errors_fail_closed() -> None:
    query_failure = FakeClient()
    query_failure.error = RuntimeError("permission denied")
    with pytest.raises(OrdersV2LiveSchemaCollectorResultError):
        collect_orders_v2_schema_observation(
            client=query_failure,
            config=config(),
        )

    result_failure = FakeClient()
    result_failure.job.error = RuntimeError("job failed")
    with pytest.raises(OrdersV2LiveSchemaCollectorResultError):
        collect_orders_v2_schema_observation(
            client=result_failure,
            config=config(),
        )


def test_malformed_metadata_never_becomes_observation() -> None:
    for field, value in (
        ("field_path", "tenant.id"),
        ("data_type", "INT64"),
        ("column_name", "tenant"),
    ):
        row = metadata_row()
        row[field] = value
        with pytest.raises((ValidationError, ValueError)):
            collect_orders_v2_schema_observation(
                client=FakeClient(rows=[row]),
                config=config(),
            )


def test_unattested_observation_cannot_self_promote() -> None:
    observation = collect_orders_v2_schema_observation(
        client=FakeClient(),
        config=config(),
        observed_at=datetime(2026, 8, 13, 5, 30, tzinfo=UTC),
    )

    for field, value in (
        ("attested_live_run", True),
        ("production_blocker", ""),
    ):
        payload = observation.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2CollectedSchemaObservation.model_validate(payload)

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False
    assert ORDERS_V2_CANDIDATE.schema_evidence_fingerprint is None
