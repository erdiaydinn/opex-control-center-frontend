"""Read-only BigQuery schema collector for the blocked orders v2 candidate.

The collector is intentionally not exposed as an HTTP route and cannot promote
the query contract. It executes one fixed INFORMATION_SCHEMA query, requires
exactly one metadata row, binds the returned project to the configured client
project and emits an explicitly *unattested* collector observation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orders_v2_schema_evidence import (
    ORDERS_TABLE,
    ORDERS_TENANT_FIELD_PATH,
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY,
    OrdersV2InformationSchemaEvidence,
    build_orders_v2_information_schema_evidence,
    validate_orders_v2_schema_evidence,
)

EAY_BQ_PROJECT_ENV = "EAY_BQ_PROJECT"
EAY_BQ_LOCATION_ENV = "EAY_BQ_LOCATION"
SCHEMA_COLLECTOR_TIMEOUT_SECONDS = 30
UNATTESTED_COLLECTOR_BLOCKER = "live_schema_collection_attestation_missing"


class OrdersV2LiveSchemaCollectorError(RuntimeError):
    """Base fail-closed live metadata collector error."""


class OrdersV2LiveSchemaCollectorConfigError(OrdersV2LiveSchemaCollectorError):
    """Canonical BigQuery collector configuration is unavailable or unsafe."""


class OrdersV2LiveSchemaCollectorResultError(OrdersV2LiveSchemaCollectorError):
    """The metadata query did not return one trustworthy expected row."""


class _QueryJob(Protocol):
    def result(self, *, timeout: float | None = None) -> Any: ...


class _BigQueryClient(Protocol):
    project: str
    location: str | None

    def query(
        self,
        query: str,
        *,
        job_config: Any,
        location: str | None = None,
    ) -> _QueryJob: ...


@dataclass(frozen=True)
class OrdersV2LiveSchemaCollectorConfig:
    project: str
    location: str | None = None

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> OrdersV2LiveSchemaCollectorConfig:
        source = os.environ if environ is None else environ
        project = source.get(EAY_BQ_PROJECT_ENV, "").strip()
        location = source.get(EAY_BQ_LOCATION_ENV, "").strip() or None

        _validate_project(project)
        if location is not None:
            _validate_location(location)

        return cls(project=project, location=location)


class OrdersV2CollectedSchemaObservation(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    provenance_kind: Literal["collector_observation_unattested"]
    evidence: OrdersV2InformationSchemaEvidence
    client_project: str = Field(min_length=1, max_length=256)
    client_location: str | None = Field(default=None, max_length=128)
    metadata_row_count: Literal[1]
    attested_live_run: Literal[False]
    production_blocker: Literal["live_schema_collection_attestation_missing"]


def _validate_project(value: str) -> None:
    if (
        not value
        or len(value) > 256
        or value != value.strip()
        or any(char.isspace() for char in value)
        or any(char in value for char in ("`", ";", "/", "\\"))
    ):
        raise OrdersV2LiveSchemaCollectorConfigError(
            "EAY_BQ_PROJECT is missing or unsafe"
        )


def _validate_location(value: str) -> None:
    if (
        not value
        or len(value) > 128
        or value != value.strip()
        or any(char.isspace() for char in value)
        or any(char in value for char in ("`", ";", "/", "\\"))
    ):
        raise OrdersV2LiveSchemaCollectorConfigError(
            "EAY_BQ_LOCATION is unsafe"
        )


def _load_bigquery_module() -> Any:
    try:
        from google.cloud import bigquery  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "google-cloud-bigquery optional dependency is unavailable"
        ) from exc
    return bigquery


def _metadata_job_config(bigquery: Any) -> Any:
    """Build the only reviewed metadata QueryJobConfig."""

    return bigquery.QueryJobConfig(
        use_legacy_sql=False,
        query_parameters=[
            bigquery.ScalarQueryParameter(
                "table_name",
                "STRING",
                ORDERS_TABLE,
            ),
            bigquery.ScalarQueryParameter(
                "field_path",
                "STRING",
                ORDERS_TENANT_FIELD_PATH,
            ),
        ],
    )


def build_default_orders_v2_schema_client(
    config: OrdersV2LiveSchemaCollectorConfig,
) -> _BigQueryClient:
    """Construct the canonical SDK client; no query is submitted here."""

    bigquery = _load_bigquery_module()
    return bigquery.Client(
        project=config.project,
        location=config.location,
    )


def _row_to_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)

    items = getattr(row, "items", None)
    if callable(items):
        return dict(items())

    raise OrdersV2LiveSchemaCollectorResultError(
        "BigQuery metadata row is not mapping-compatible"
    )


def _materialize_rows(result: Any) -> tuple[Any, ...]:
    if isinstance(result, (str, bytes, bytearray)):
        raise OrdersV2LiveSchemaCollectorResultError(
            "BigQuery metadata result is not row-iterable"
        )

    if not isinstance(result, Sequence):
        try:
            return tuple(result)
        except TypeError as exc:
            raise OrdersV2LiveSchemaCollectorResultError(
                "BigQuery metadata result is not iterable"
            ) from exc

    return tuple(result)


def collect_orders_v2_schema_observation(
    *,
    client: _BigQueryClient,
    config: OrdersV2LiveSchemaCollectorConfig,
    observed_at: datetime | None = None,
) -> OrdersV2CollectedSchemaObservation:
    """Execute one fixed metadata query and return an unattested observation."""

    _validate_project(config.project)
    if config.location is not None:
        _validate_location(config.location)

    client_project = str(getattr(client, "project", "") or "").strip()
    if client_project != config.project:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "BigQuery client project does not match EAY_BQ_PROJECT"
        )

    client_location_raw = getattr(client, "location", None)
    client_location = (
        str(client_location_raw).strip()
        if client_location_raw is not None
        else None
    )
    if client_location != config.location:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "BigQuery client location does not match EAY_BQ_LOCATION"
        )

    bigquery = _load_bigquery_module()
    job_config = _metadata_job_config(bigquery)

    try:
        job = client.query(
            ORDERS_V2_SCHEMA_EVIDENCE_QUERY,
            job_config=job_config,
            location=config.location,
        )
        rows = _materialize_rows(
            job.result(timeout=SCHEMA_COLLECTOR_TIMEOUT_SECONDS)
        )
    except OrdersV2LiveSchemaCollectorError:
        raise
    except Exception as exc:
        raise OrdersV2LiveSchemaCollectorResultError(
            "BigQuery schema metadata collection failed"
        ) from exc

    if len(rows) != 1:
        raise OrdersV2LiveSchemaCollectorResultError(
            "BigQuery schema metadata must return exactly one row"
        )

    row = _row_to_mapping(rows[0])
    if row.get("table_catalog") != config.project:
        raise OrdersV2LiveSchemaCollectorResultError(
            "BigQuery metadata table_catalog does not match configured project"
        )

    timestamp = observed_at or datetime.now(UTC)
    evidence = build_orders_v2_information_schema_evidence(
        row=row,
        observed_at=timestamp,
    )
    validate_orders_v2_schema_evidence(evidence)

    return OrdersV2CollectedSchemaObservation(
        provenance_kind="collector_observation_unattested",
        evidence=evidence,
        client_project=config.project,
        client_location=config.location,
        metadata_row_count=1,
        attested_live_run=False,
        production_blocker=UNATTESTED_COLLECTOR_BLOCKER,
    )
