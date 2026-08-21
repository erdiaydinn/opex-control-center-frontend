"""Fail-closed schema-evidence contract for `ops.kpi.orders.v2`.

The contract models the exact metadata row a trusted BigQuery collector must
obtain from `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`. Constructing or validating
this model does *not* prove that the row came from BigQuery and therefore does
not promote the query contract by itself.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.ai_orders_v2_query_contract import (
    ORDERS_SOURCE_TABLE,
    ORDERS_V2_CANDIDATE,
    validate_orders_v2_query_candidate,
)

SCHEMA_EVIDENCE_SOURCE_VIEW = "INFORMATION_SCHEMA.COLUMN_FIELD_PATHS"
ORDERS_DATASET = "curated_data_shared_coredata_business"
ORDERS_TABLE = "orders"
ORDERS_TENANT_TOP_LEVEL_COLUMN = "entity"
ORDERS_TENANT_FIELD_PATH = "entity.id"
ORDERS_TENANT_DATA_TYPE = "STRING"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

# The collector must explicitly name metadata columns and bind the table/field
# selectors. No SELECT * and no runtime-selected metadata view are permitted.
ORDERS_V2_SCHEMA_EVIDENCE_QUERY = """
SELECT
  table_catalog,
  table_schema,
  table_name,
  column_name,
  field_path,
  data_type
FROM `curated_data_shared_coredata_business.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
WHERE table_name = @table_name
  AND field_path = @field_path
""".strip()

ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256 = hashlib.sha256(
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY.encode("utf-8")
).hexdigest()


class OrdersV2SchemaEvidenceError(ValueError):
    """The metadata evidence cannot support the candidate discriminator."""


class OrdersV2InformationSchemaEvidence(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    source_view: Literal["INFORMATION_SCHEMA.COLUMN_FIELD_PATHS"]
    table_catalog: str = Field(min_length=1, max_length=256)
    table_schema: Literal["curated_data_shared_coredata_business"]
    table_name: Literal["orders"]
    column_name: Literal["entity"]
    field_path: Literal["entity.id"]
    data_type: Literal["STRING"]
    observed_at: datetime
    collector_query_sha256: str = Field(pattern=SHA256_PATTERN)
    result_row_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("table_catalog")
    @classmethod
    def validate_table_catalog(cls, value: str) -> str:
        normalized = value.strip()
        if (
            normalized != value
            or not normalized
            or any(char.isspace() for char in normalized)
            or "`" in normalized
            or ";" in normalized
        ):
            raise ValueError("table_catalog is unsafe")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_fingerprints(self) -> OrdersV2InformationSchemaEvidence:
        if self.collector_query_sha256 != ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256:
            raise ValueError("collector query fingerprint mismatch")
        if self.result_row_sha256 != orders_v2_schema_result_row_fingerprint(
            self.metadata_row()
        ):
            raise ValueError("metadata result row fingerprint mismatch")
        return self

    def metadata_row(self) -> dict[str, str]:
        return {
            "table_catalog": self.table_catalog,
            "table_schema": self.table_schema,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "field_path": self.field_path,
            "data_type": self.data_type,
        }

    @property
    def evidence_fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def orders_v2_schema_result_row_fingerprint(
    row: Mapping[str, Any],
) -> str:
    expected_keys = {
        "table_catalog",
        "table_schema",
        "table_name",
        "column_name",
        "field_path",
        "data_type",
    }
    if set(row) != expected_keys:
        raise OrdersV2SchemaEvidenceError(
            "metadata row has unexpected columns"
        )

    normalized: dict[str, str] = {}
    for key in sorted(expected_keys):
        value = row[key]
        if not isinstance(value, str):
            raise OrdersV2SchemaEvidenceError(
                "metadata row values must be text"
            )
        normalized[key] = value

    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_information_schema_evidence(
    *,
    row: Mapping[str, Any],
    observed_at: datetime,
) -> OrdersV2InformationSchemaEvidence:
    """Build evidence from one exact trusted-collector metadata row."""

    result_row_sha256 = orders_v2_schema_result_row_fingerprint(row)
    return OrdersV2InformationSchemaEvidence(
        source_view=SCHEMA_EVIDENCE_SOURCE_VIEW,
        table_catalog=row["table_catalog"],
        table_schema=row["table_schema"],
        table_name=row["table_name"],
        column_name=row["column_name"],
        field_path=row["field_path"],
        data_type=row["data_type"],
        observed_at=observed_at,
        collector_query_sha256=(
            ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256
        ),
        result_row_sha256=result_row_sha256,
    )


def validate_orders_v2_schema_evidence(
    evidence: OrdersV2InformationSchemaEvidence,
) -> str:
    """Check evidence semantics against the blocked query candidate.

    This validates consistency only. It deliberately cannot attest provenance;
    a trusted live collector must supply the evidence in a later slice.
    """

    validate_orders_v2_query_candidate()

    expected_source = f"{evidence.table_schema}.{evidence.table_name}"
    if expected_source != ORDERS_SOURCE_TABLE:
        raise OrdersV2SchemaEvidenceError("source table mismatch")
    if evidence.field_path != ORDERS_V2_CANDIDATE.tenant_discriminator_expression:
        raise OrdersV2SchemaEvidenceError(
            "tenant discriminator field path mismatch"
        )
    if evidence.column_name != ORDERS_TENANT_TOP_LEVEL_COLUMN:
        raise OrdersV2SchemaEvidenceError("top-level tenant column mismatch")
    if evidence.data_type != ORDERS_TENANT_DATA_TYPE:
        raise OrdersV2SchemaEvidenceError("tenant discriminator type mismatch")

    return evidence.evidence_fingerprint
