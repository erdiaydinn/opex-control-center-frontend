"""Governed prepared BigQuery lookup for picker/shift order attribution.

This is a deliberately narrow company-read capability for the reviewed
``qc_picker_shift_orders`` source. Jarvis cannot supply arbitrary SQL, table names or
mutation semantics. Runtime inputs are typed parameters only; the SQL text is static and
fingerprinted in code.

A successful BigQuery job emits a secret-safe execution receipt and then normalizes rows
into the existing ``CompanyReadProtocolProof`` / ``ReadOnlySourceBatch`` path. The
collection is still not Company World truth. Independent live-source attestation remains
required before promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from .company_source_adapter_registry import (
    AdapterAcceptance,
    CompanySourceAdapterDescriptor,
    CompanySourceOperation,
    CompanySourceProtocol,
)
from .company_source_protocol_collectors import (
    CompanyReadProtocolProof,
    NormalizedCompanyReadResult,
)
from .live_company_reality import LiveSourceKind
from .live_company_source_runtime import ReadOnlySourceField, ReadOnlySourcePlan

PICKER_SHIFT_ORDER_LOOKUP_CONTRACT = "eay-picker-shift-order-lookup-v1"
PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF = "ops.bigquery.picker_shift_order_lookup.v1"
PICKER_SHIFT_ORDER_LOOKUP_BINDING_ID = "live.workforce.picker_shift_order_lookup.v1"
PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF = (
    "bigquery://fulfillment-dwh-production/curated_data_shared_dmart/"
    "qc_picker_shift_orders"
)
PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT = "dmart.qc_picker_shift_orders.picker_lookup"
PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION = "v1"
PICKER_SHIFT_ORDER_LOOKUP_PROJECT = "fulfillment-dwh-production"
PICKER_SHIFT_ORDER_LOOKUP_TABLE = (
    "fulfillment-dwh-production.curated_data_shared_dmart.qc_picker_shift_orders"
)
PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS = (
    "order_id",
    "rooster_employee_id",
    "user_id",
    "rooster_rider_id",
    "shopper_id",
    "warehouse_id",
    "order_created_at_lt",
)
PICKER_SHIFT_ORDER_LOOKUP_PARAMETER_NAMES = (
    "order_ids",
    "global_entity_id",
    "start_date",
    "end_date",
)

PICKER_SHIFT_ORDER_LOOKUP_SQL = """WITH target_orders AS (
  SELECT DISTINCT LOWER(TRIM(order_id)) AS order_id
  FROM UNNEST(@order_ids) AS order_id
  WHERE TRIM(order_id) != ''
)

SELECT
  oe.order_id,
  COALESCE(oe.rooster_employee_id, q.rooster_employee_id) AS rooster_employee_id,
  q.user_id,
  oe.rooster_rider_id,
  oe.shopper_id,
  oe.warehouse_id,
  DATETIME(oe.order_created_at_utc, 'Europe/Istanbul') AS order_created_at_lt
FROM `fulfillment-dwh-production.curated_data_shared_dmart.qc_picker_shift_orders` q
CROSS JOIN UNNEST(q.shifts) AS s
CROSS JOIN UNNEST(s.order_events) AS oe
JOIN target_orders t
  ON LOWER(TRIM(oe.order_id)) = t.order_id
WHERE q.global_entity_id = @global_entity_id
  AND q.shift_start_date_utc BETWEEN @start_date AND @end_date
  AND oe.order_created_date_utc BETWEEN @start_date AND @end_date
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY oe.order_id
  ORDER BY oe.order_created_at_utc DESC
) = 1
ORDER BY oe.order_id
"""

PICKER_SHIFT_ORDER_LOOKUP_QUERY_FINGERPRINT = hashlib.sha256(
    PICKER_SHIFT_ORDER_LOOKUP_SQL.encode("utf-8")
).hexdigest()

_ISTANBUL = ZoneInfo("Europe/Istanbul")
_GOOGLE_PRINCIPAL_PREFIX = "google-principal://"
_FORBIDDEN_SQL_TOKENS = (
    " INSERT ",
    " UPDATE ",
    " DELETE ",
    " MERGE ",
    " CREATE ",
    " DROP ",
    " ALTER ",
    " TRUNCATE ",
    " EXPORT DATA ",
    " LOAD DATA ",
    " CALL ",
)


class PickerShiftOrderLookupRequest(BaseModel):
    contract: str = PICKER_SHIFT_ORDER_LOOKUP_CONTRACT
    tenant_id: str = "YS_TR"
    global_entity_id: str = "YS_TR"
    order_ids: tuple[str, ...] = Field(min_length=1, max_length=1000)
    start_date: date
    end_date: date
    maximum_bytes_billed: int = Field(
        default=50_000_000_000,
        ge=1_000_000,
        le=1_000_000_000_000,
    )

    @field_validator("order_ids", mode="before")
    @classmethod
    def normalize_order_ids(cls, value):
        normalized: list[str] = []
        for raw in value or ():
            item = str(raw).strip().lower()
            if not item or item == "order_id":
                continue
            if len(item) > 80 or any(
                not (char.isalnum() or char in {"-", "_"}) for char in item
            ):
                raise ValueError("picker_shift_lookup_invalid_order_id")
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("picker_shift_lookup_requires_order_id")
        return tuple(normalized)

    @model_validator(mode="after")
    def request_is_tenant_and_window_bound(self) -> "PickerShiftOrderLookupRequest":
        if self.tenant_id != "YS_TR" or self.global_entity_id != "YS_TR":
            raise ValueError("picker_shift_lookup_only_ys_tr_reviewed")
        if self.end_date < self.start_date:
            raise ValueError("picker_shift_lookup_end_date_before_start")
        if (self.end_date - self.start_date).days > 62:
            raise ValueError("picker_shift_lookup_window_too_large")
        return self


class PickerShiftOrderLookupRow(BaseModel):
    order_id: str = Field(min_length=1)
    rooster_employee_id: str | None = None
    user_id: str | None = None
    rooster_rider_id: str | None = None
    shopper_id: str | None = None
    warehouse_id: str | None = None
    order_created_at_lt: datetime

    @model_validator(mode="after")
    def local_datetime_is_bound(self) -> "PickerShiftOrderLookupRow":
        _require_aware(
            self.order_created_at_lt,
            "picker_shift_lookup_order_time_requires_timezone",
        )
        return self


class PickerShiftOrderLookupExecution(BaseModel):
    contract: str = PICKER_SHIFT_ORDER_LOOKUP_CONTRACT
    rows: tuple[PickerShiftOrderLookupRow, ...]
    job_id: str = Field(min_length=1)
    project_ref: str = Field(min_length=1)
    location: str = Field(min_length=1)
    observed_execution_identity_ref: str = Field(min_length=1)
    statement_type: str
    started_at: datetime
    completed_at: datetime
    total_bytes_processed: int = Field(ge=0)
    total_bytes_billed: int = Field(ge=0)
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    destination_write_detected: bool = False
    raw_query_retained: bool = False
    raw_result_retained: bool = False
    credential_material_retained: bool = False

    @model_validator(mode="after")
    def execution_is_read_only_and_secret_safe(self) -> "PickerShiftOrderLookupExecution":
        _require_aware(self.started_at, "picker_shift_lookup_started_at_requires_timezone")
        _require_aware(self.completed_at, "picker_shift_lookup_completed_at_requires_timezone")
        _require_google_principal_ref(self.observed_execution_identity_ref)
        if self.completed_at < self.started_at:
            raise ValueError("picker_shift_lookup_completed_before_started")
        if self.statement_type.upper() != "SELECT":
            raise ValueError("picker_shift_lookup_requires_select_statement")
        if self.destination_write_detected:
            raise ValueError("picker_shift_lookup_destination_write_forbidden")
        if self.raw_query_retained or self.raw_result_retained or self.credential_material_retained:
            raise ValueError("picker_shift_lookup_sensitive_retention_forbidden")
        return self


class PickerShiftOrderLookupReceipt(BaseModel):
    contract: str = PICKER_SHIFT_ORDER_LOOKUP_CONTRACT
    operation_ref: str = PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF
    tenant_id: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    job_ref: str = Field(min_length=1)
    project_ref: str = Field(min_length=1)
    location: str = Field(min_length=1)
    query_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    row_count: int = Field(ge=0)
    total_bytes_processed: int = Field(ge=0)
    total_bytes_billed: int = Field(ge=0)
    success: bool
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_integral_and_non_authoritative(self) -> "PickerShiftOrderLookupReceipt":
        _require_aware(
            self.started_at,
            "picker_shift_lookup_receipt_started_at_requires_timezone",
        )
        _require_aware(
            self.completed_at,
            "picker_shift_lookup_receipt_completed_at_requires_timezone",
        )
        _require_google_principal_ref(self.execution_identity_ref)
        if self.truth_authority_granted:
            raise ValueError("picker_shift_lookup_receipt_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("picker_shift_lookup_receipt_never_grants_execution_authority")
        expected = _receipt_fingerprint(
            _receipt_payload_values(
                contract=self.contract,
                operation_ref=self.operation_ref,
                tenant_id=self.tenant_id,
                execution_identity_ref=self.execution_identity_ref,
                job_ref=self.job_ref,
                project_ref=self.project_ref,
                location=self.location,
                query_fingerprint=self.query_fingerprint,
                schema_fingerprint=self.schema_fingerprint,
                started_at=self.started_at,
                completed_at=self.completed_at,
                row_count=self.row_count,
                total_bytes_processed=self.total_bytes_processed,
                total_bytes_billed=self.total_bytes_billed,
                success=self.success,
                truth_authority_granted=self.truth_authority_granted,
                execution_authority_granted=self.execution_authority_granted,
            )
        )
        if self.fingerprint != expected:
            raise ValueError("picker_shift_lookup_receipt_fingerprint_mismatch")
        return self


class PickerShiftOrderLookupRunner(Protocol):
    def run(
        self,
        request: PickerShiftOrderLookupRequest,
    ) -> PickerShiftOrderLookupExecution: ...


ReceiptRecorder = Callable[[PickerShiftOrderLookupReceipt], None]


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _require_google_principal_ref(value: str) -> None:
    if not value.startswith(_GOOGLE_PRINCIPAL_PREFIX):
        raise ValueError("picker_shift_lookup_execution_identity_must_be_observable_google_principal")
    principal = value.removeprefix(_GOOGLE_PRINCIPAL_PREFIX).strip().lower()
    if not principal or "@" not in principal or any(char.isspace() for char in principal):
        raise ValueError("picker_shift_lookup_execution_identity_invalid_google_principal")


def _principal_ref_from_job(job) -> str:
    user_email = str(getattr(job, "user_email", "") or "").strip().lower()
    if not user_email:
        raise RuntimeError("picker_shift_lookup_bigquery_job_principal_missing")
    principal_ref = f"{_GOOGLE_PRINCIPAL_PREFIX}{user_email}"
    _require_google_principal_ref(principal_ref)
    return principal_ref


def _canonical_utc(value: datetime) -> str:
    _require_aware(value, "picker_shift_lookup_fingerprint_datetime_requires_timezone")
    return value.astimezone(timezone.utc).isoformat()


def _receipt_payload_values(
    *,
    contract: str,
    operation_ref: str,
    tenant_id: str,
    execution_identity_ref: str,
    job_ref: str,
    project_ref: str,
    location: str,
    query_fingerprint: str,
    schema_fingerprint: str,
    started_at: datetime,
    completed_at: datetime,
    row_count: int,
    total_bytes_processed: int,
    total_bytes_billed: int,
    success: bool,
    truth_authority_granted: bool,
    execution_authority_granted: bool,
) -> dict[str, Any]:
    """Canonical receipt payload shared by construction and integrity validation."""

    return {
        "contract": str(contract),
        "operation_ref": str(operation_ref),
        "tenant_id": str(tenant_id),
        "execution_identity_ref": str(execution_identity_ref),
        "job_ref": str(job_ref),
        "project_ref": str(project_ref),
        "location": str(location),
        "query_fingerprint": str(query_fingerprint),
        "schema_fingerprint": str(schema_fingerprint),
        "started_at": _canonical_utc(started_at),
        "completed_at": _canonical_utc(completed_at),
        "row_count": int(row_count),
        "total_bytes_processed": int(total_bytes_processed),
        "total_bytes_billed": int(total_bytes_billed),
        "success": bool(success),
        "truth_authority_granted": bool(truth_authority_granted),
        "execution_authority_granted": bool(execution_authority_granted),
    }


def _receipt_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _schema_fingerprint(schema) -> str:
    normalized = [
        {
            "name": str(getattr(field, "name", "")),
            "field_type": str(getattr(field, "field_type", "")),
            "mode": str(getattr(field, "mode", "")),
        }
        for field in (schema or ())
    ]
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _local_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError("picker_shift_lookup_order_time_not_datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_ISTANBUL)
    return value.astimezone(_ISTANBUL)


def _assert_static_query_is_read_only() -> None:
    normalized = " " + " ".join(PICKER_SHIFT_ORDER_LOOKUP_SQL.upper().split()) + " "
    if any(token in normalized for token in _FORBIDDEN_SQL_TOKENS):
        raise RuntimeError("picker_shift_lookup_static_query_contains_mutation")
    if f"`{PICKER_SHIFT_ORDER_LOOKUP_TABLE}`" not in PICKER_SHIFT_ORDER_LOOKUP_SQL:
        raise RuntimeError("picker_shift_lookup_static_query_table_drift")
    for parameter in ("@order_ids", "@global_entity_id", "@start_date", "@end_date"):
        if parameter not in PICKER_SHIFT_ORDER_LOOKUP_SQL:
            raise RuntimeError("picker_shift_lookup_static_query_parameter_missing")


class GoogleBigQueryPickerShiftOrderLookupRunner:
    """Real BigQuery SDK runner. Credentials resolve only through Google ADC."""

    def __init__(
        self,
        *,
        project_id: str = PICKER_SHIFT_ORDER_LOOKUP_PROJECT,
        location: str | None = None,
        client=None,
    ) -> None:
        _assert_static_query_is_read_only()
        if project_id != PICKER_SHIFT_ORDER_LOOKUP_PROJECT:
            raise ValueError("picker_shift_lookup_project_not_reviewed")
        self.project_id = project_id
        self.location = location
        self._client = client

    def _bigquery(self):
        try:
            from google.cloud import bigquery
        except ImportError as exc:  # pragma: no cover - environment specific
            raise RuntimeError("picker_shift_lookup_bigquery_sdk_unavailable") from exc
        return bigquery

    def _client_or_default(self):
        if self._client is not None:
            return self._client
        bigquery = self._bigquery()
        return bigquery.Client(project=self.project_id)

    def run(self, request: PickerShiftOrderLookupRequest) -> PickerShiftOrderLookupExecution:
        _assert_static_query_is_read_only()
        bigquery = self._bigquery()
        client = self._client_or_default()
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
            maximum_bytes_billed=request.maximum_bytes_billed,
            labels={"eay_operation": "picker_shift_lookup"},
            query_parameters=[
                bigquery.ArrayQueryParameter("order_ids", "STRING", list(request.order_ids)),
                bigquery.ScalarQueryParameter(
                    "global_entity_id",
                    "STRING",
                    request.global_entity_id,
                ),
                bigquery.ScalarQueryParameter("start_date", "DATE", request.start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", request.end_date),
            ],
        )
        if getattr(job_config, "destination", None) is not None:
            raise RuntimeError("picker_shift_lookup_explicit_destination_forbidden")

        job = client.query(
            PICKER_SHIFT_ORDER_LOOKUP_SQL,
            job_config=job_config,
            location=self.location,
        )
        rows = tuple(job.result())
        statement_type = str(getattr(job, "statement_type", "") or "")
        if statement_type.upper() != "SELECT":
            raise RuntimeError("picker_shift_lookup_runtime_statement_not_select")
        if getattr(job, "error_result", None):
            raise RuntimeError("picker_shift_lookup_bigquery_job_failed")

        normalized_rows = tuple(
            PickerShiftOrderLookupRow(
                order_id=str(row["order_id"]).strip().lower(),
                rooster_employee_id=(
                    None
                    if row["rooster_employee_id"] is None
                    else str(row["rooster_employee_id"])
                ),
                user_id=None if row["user_id"] is None else str(row["user_id"]),
                rooster_rider_id=(
                    None
                    if row["rooster_rider_id"] is None
                    else str(row["rooster_rider_id"])
                ),
                shopper_id=(
                    None if row["shopper_id"] is None else str(row["shopper_id"])
                ),
                warehouse_id=(
                    None if row["warehouse_id"] is None else str(row["warehouse_id"])
                ),
                order_created_at_lt=_local_datetime(row["order_created_at_lt"]),
            )
            for row in rows
        )
        return PickerShiftOrderLookupExecution(
            rows=normalized_rows,
            job_id=str(getattr(job, "job_id", "") or "unknown-job"),
            project_ref=str(getattr(job, "project", "") or self.project_id),
            location=str(getattr(job, "location", "") or self.location or "unspecified"),
            observed_execution_identity_ref=_principal_ref_from_job(job),
            statement_type=statement_type,
            started_at=_aware_utc(getattr(job, "started", None)),
            completed_at=_aware_utc(getattr(job, "ended", None)),
            total_bytes_processed=int(getattr(job, "total_bytes_processed", 0) or 0),
            total_bytes_billed=int(getattr(job, "total_bytes_billed", 0) or 0),
            schema_fingerprint=_schema_fingerprint(getattr(job, "schema", ())),
        )


@dataclass(frozen=True)
class PickerShiftOrderLookupPreparedExecutor:
    """Bind one reviewed request to the generic prepared-company-read protocol."""

    request: PickerShiftOrderLookupRequest
    runner: PickerShiftOrderLookupRunner
    execution_identity_ref: str
    receipt_recorder: ReceiptRecorder

    def execute(self, plan: ReadOnlySourcePlan) -> NormalizedCompanyReadResult:
        _require_google_principal_ref(self.execution_identity_ref)
        if plan.tenant_id != self.request.tenant_id:
            raise ValueError("picker_shift_lookup_plan_tenant_mismatch")
        if plan.binding_id != PICKER_SHIFT_ORDER_LOOKUP_BINDING_ID:
            raise ValueError("picker_shift_lookup_plan_binding_mismatch")
        if plan.source_kind is not LiveSourceKind.WORKFORCE:
            raise ValueError("picker_shift_lookup_plan_source_kind_mismatch")
        if plan.source_ref != PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF:
            raise ValueError("picker_shift_lookup_plan_source_ref_mismatch")
        if plan.schema_contract != PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT:
            raise ValueError("picker_shift_lookup_plan_schema_contract_mismatch")
        if plan.schema_version != PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION:
            raise ValueError("picker_shift_lookup_plan_schema_version_mismatch")
        if plan.operation_ref != PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF:
            raise ValueError("picker_shift_lookup_plan_operation_mismatch")
        if plan.execution_identity_ref != self.execution_identity_ref:
            raise ValueError("picker_shift_lookup_execution_identity_mismatch")
        if any(
            field not in PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS
            for field in plan.requested_fields
        ):
            raise ValueError("picker_shift_lookup_requested_field_not_allowed")

        execution = self.runner.run(self.request)
        if execution.completed_at < plan.requested_at:
            raise ValueError("picker_shift_lookup_execution_predates_plan")
        if execution.project_ref != PICKER_SHIFT_ORDER_LOOKUP_PROJECT:
            raise ValueError("picker_shift_lookup_execution_project_drift")
        if execution.observed_execution_identity_ref != self.execution_identity_ref:
            raise ValueError("picker_shift_lookup_observed_execution_identity_mismatch")

        job_ref = f"bigquery-job://{execution.project_ref}/{execution.location}/{execution.job_id}"
        receipt_payload = _receipt_payload_values(
            contract=PICKER_SHIFT_ORDER_LOOKUP_CONTRACT,
            operation_ref=PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
            tenant_id=self.request.tenant_id,
            execution_identity_ref=execution.observed_execution_identity_ref,
            job_ref=job_ref,
            project_ref=execution.project_ref,
            location=execution.location,
            query_fingerprint=PICKER_SHIFT_ORDER_LOOKUP_QUERY_FINGERPRINT,
            schema_fingerprint=execution.schema_fingerprint,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            row_count=len(execution.rows),
            total_bytes_processed=execution.total_bytes_processed,
            total_bytes_billed=execution.total_bytes_billed,
            success=True,
            truth_authority_granted=False,
            execution_authority_granted=False,
        )
        receipt = PickerShiftOrderLookupReceipt.model_validate(
            {
                **receipt_payload,
                "fingerprint": _receipt_fingerprint(receipt_payload),
            }
        )
        self.receipt_recorder(receipt)

        requested = set(plan.requested_fields)
        fields: list[ReadOnlySourceField] = []
        for row in execution.rows:
            values = row.model_dump()
            entity_id = f"order:{row.order_id}"
            for field_name in PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS:
                if field_name not in requested:
                    continue
                fields.append(
                    ReadOnlySourceField(
                        entity_id=entity_id,
                        field_name=field_name,
                        value=values[field_name],
                        valid_from=row.order_created_at_lt,
                        confidence=1.0,
                    )
                )

        evidence_ref = f"bigquery-execution://{receipt.fingerprint}"
        return NormalizedCompanyReadResult(
            operation_ref=PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
            observed_at=execution.completed_at,
            source_receipt_ref=job_ref,
            evidence_ref=evidence_ref,
            fields=tuple(fields),
            proof=CompanyReadProtocolProof(
                protocol=CompanySourceProtocol.BIGQUERY,
                operation_ref=PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
                executed_at=execution.completed_at,
                evidence_ref=evidence_ref,
                statement_type="SELECT",
                destination_write_detected=False,
            ),
        )


def build_picker_shift_order_lookup_descriptor(
    *,
    environment_ref: str,
    execution_identity_ref: str,
    acceptance: AdapterAcceptance = AdapterAcceptance.REPOSITORY_ONLY,
) -> CompanySourceAdapterDescriptor:
    """Build the reviewed adapter descriptor; FIELD_PROVEN is never automatic."""

    _require_google_principal_ref(execution_identity_ref)
    if acceptance is AdapterAcceptance.FIELD_PROVEN:
        raise ValueError("picker_shift_lookup_field_proven_requires_external_attestation")
    return CompanySourceAdapterDescriptor(
        adapter_ref="company-source://workforce/picker-shift-order-lookup/v1",
        source_kind=LiveSourceKind.WORKFORCE,
        protocol=CompanySourceProtocol.BIGQUERY,
        source_ref=PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF,
        schema_contract=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT,
        schema_version=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION,
        environment_ref=environment_ref,
        execution_identity_ref=execution_identity_ref,
        operations=(
            CompanySourceOperation(
                operation_ref=PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
                contract_ref=PICKER_SHIFT_ORDER_LOOKUP_CONTRACT,
                allowed_fields=PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS,
                parameter_names=PICKER_SHIFT_ORDER_LOOKUP_PARAMETER_NAMES,
            ),
        ),
        acceptance=acceptance,
        field_production_verified=False,
    )


def build_picker_shift_order_lookup_plan(
    *,
    environment_ref: str,
    execution_identity_ref: str,
    requested_at: datetime,
    requested_fields: tuple[str, ...] = PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS,
) -> ReadOnlySourcePlan:
    _require_google_principal_ref(execution_identity_ref)
    return ReadOnlySourcePlan(
        binding_id=PICKER_SHIFT_ORDER_LOOKUP_BINDING_ID,
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.WORKFORCE,
        source_ref=PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF,
        schema_contract=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT,
        schema_version=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION,
        environment_ref=environment_ref,
        execution_identity_ref=execution_identity_ref,
        operation_ref=PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
        requested_fields=requested_fields,
        requested_at=requested_at,
    )
