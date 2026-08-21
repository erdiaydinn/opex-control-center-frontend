"""Compare both fixed Orders schemas without selecting or promoting either."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.ai_orders_v2_live_schema_collector import (
    OrdersV2LiveSchemaCollectorConfig,
    OrdersV2LiveSchemaCollectorConfigError,
    OrdersV2LiveSchemaCollectorResultError,
)

CANDIDATE_SOURCE = "curated_data_shared_coredata_business.orders"
DIRECTIVE_SOURCE = "curated_data_shared.orders"
REQUIRED_FIELD_PATHS = (
    "entity.id",
    "partition_date_local",
    "vendor_name",
    "order_id",
    "vertical",
)
SOURCE_AUTHORITY_REVIEW_BLOCKER = "orders_v2_source_authority_review_required"
SOURCE_COMPARISON_TIMEOUT_SECONDS = 30
SOURCE_COMPARISON_QUERY = """
WITH expected AS (
  SELECT field_path
  FROM UNNEST([
    'entity.id', 'partition_date_local', 'vendor_name', 'order_id', 'vertical'
  ]) AS field_path
),
candidate AS (
  SELECT field_path, data_type
  FROM `curated_data_shared_coredata_business.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
  WHERE table_name = 'orders'
),
directive AS (
  SELECT field_path, data_type
  FROM `curated_data_shared.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
  WHERE table_name = 'orders'
)
SELECT
  'curated_data_shared_coredata_business.orders' AS source_table,
  expected.field_path,
  candidate.data_type,
  candidate.field_path IS NOT NULL AS present
FROM expected
LEFT JOIN candidate USING (field_path)
UNION ALL
SELECT
  'curated_data_shared.orders' AS source_table,
  expected.field_path,
  directive.data_type,
  directive.field_path IS NOT NULL AS present
FROM expected
LEFT JOIN directive USING (field_path)
ORDER BY source_table, field_path
""".strip()
SOURCE_COMPARISON_QUERY_SHA256 = hashlib.sha256(
    SOURCE_COMPARISON_QUERY.encode("utf-8")
).hexdigest()
SHA256_PATTERN = r"^[0-9a-f]{64}$"


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


class OrdersV2SourceFieldObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_table: Literal[
        "curated_data_shared_coredata_business.orders",
        "curated_data_shared.orders",
    ]
    field_path: Literal[
        "entity.id",
        "partition_date_local",
        "vendor_name",
        "order_id",
        "vertical",
    ]
    data_type: str | None = Field(default=None, max_length=256)
    present: bool

    @model_validator(mode="after")
    def validate_presence(self) -> OrdersV2SourceFieldObservation:
        if self.present != (self.data_type is not None):
            raise ValueError("field presence and data type disagree")
        return self


class OrdersV2SourceComparisonObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["live_bigquery_orders_source_comparison_candidate"]
    project: str = Field(min_length=1, max_length=256)
    location: str | None = Field(default=None, max_length=128)
    observed_at: datetime
    collector_query_sha256: str = Field(pattern=SHA256_PATTERN)
    fields: tuple[OrdersV2SourceFieldObservation, ...]
    candidate_source: Literal[
        "curated_data_shared_coredata_business.orders"
    ]
    directive_source: Literal["curated_data_shared.orders"]
    live_bigquery_run_claimed: Literal[True]
    source_authority_decided: Literal[False]
    candidate_mutation_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal[
        "orders_v2_source_authority_review_required"
    ]

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_matrix(self) -> OrdersV2SourceComparisonObservation:
        expected = {
            (source, field)
            for source in (CANDIDATE_SOURCE, DIRECTIVE_SOURCE)
            for field in REQUIRED_FIELD_PATHS
        }
        actual = {(item.source_table, item.field_path) for item in self.fields}
        if actual != expected or len(self.fields) != len(expected):
            raise ValueError("source comparison matrix is incomplete")
        if self.collector_query_sha256 != SOURCE_COMPARISON_QUERY_SHA256:
            raise ValueError("source comparison query fingerprint mismatch")
        return self

    @property
    def observation_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _load_bigquery_module() -> Any:
    try:
        from google.cloud import bigquery  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "google-cloud-bigquery optional dependency is unavailable"
        ) from exc
    return bigquery


def collect_orders_v2_source_comparison(
    *,
    client: _BigQueryClient,
    config: OrdersV2LiveSchemaCollectorConfig,
    observed_at: datetime | None = None,
) -> OrdersV2SourceComparisonObservation:
    """Observe both fixed Orders sources without selecting either one."""

    if client.project != config.project:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "BigQuery client project does not match EAY_BQ_PROJECT"
        )
    if client.location != config.location:
        raise OrdersV2LiveSchemaCollectorConfigError(
            "BigQuery client location does not match EAY_BQ_LOCATION"
        )

    bigquery = _load_bigquery_module()
    job_config = bigquery.QueryJobConfig(use_legacy_sql=False)
    job_config.maximum_bytes_billed = 100_000_000
    job_config.use_query_cache = False
    try:
        job = client.query(
            SOURCE_COMPARISON_QUERY,
            job_config=job_config,
            location=config.location,
        )
        rows = tuple(
            job.result(timeout=SOURCE_COMPARISON_TIMEOUT_SECONDS)
        )
    except Exception as exc:
        raise OrdersV2LiveSchemaCollectorResultError(
            "BigQuery Orders source comparison failed"
        ) from exc

    fields: list[OrdersV2SourceFieldObservation] = []
    for row in rows:
        values = dict(row.items()) if hasattr(row, "items") else dict(row)
        if set(values) != {"source_table", "field_path", "data_type", "present"}:
            raise OrdersV2LiveSchemaCollectorResultError(
                "source comparison row has unexpected columns"
            )
        fields.append(OrdersV2SourceFieldObservation.model_validate(values))

    try:
        return OrdersV2SourceComparisonObservation(
            version=1,
            kind="live_bigquery_orders_source_comparison_candidate",
            project=config.project,
            location=config.location,
            observed_at=observed_at or datetime.now(UTC),
            collector_query_sha256=SOURCE_COMPARISON_QUERY_SHA256,
            fields=tuple(fields),
            candidate_source=CANDIDATE_SOURCE,
            directive_source=DIRECTIVE_SOURCE,
            live_bigquery_run_claimed=True,
            source_authority_decided=False,
            candidate_mutation_permitted=False,
            promotion_eligible=False,
            production_ready=False,
            production_blocker=SOURCE_AUTHORITY_REVIEW_BLOCKER,
        )
    except ValueError as exc:
        raise OrdersV2LiveSchemaCollectorResultError(
            "source comparison matrix is invalid"
        ) from exc
