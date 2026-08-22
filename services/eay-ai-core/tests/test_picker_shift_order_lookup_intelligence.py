from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.company_source_adapter_execution import (
    CompanySourceRuntimeBinding,
    execute_registered_company_read,
)
from app.company_source_adapter_registry import (
    AdapterAcceptance,
    CompanySourceAdapterRegistry,
    CompanySourceProtocol,
)
from app.company_source_protocol_collectors import ProtocolBoundCompanySourceAdapter
from app.live_company_reality import LiveSourceBindingPolicy, LiveSourceKind
from app.picker_shift_order_lookup import (
    PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS,
    PICKER_SHIFT_ORDER_LOOKUP_BINDING_ID,
    PICKER_SHIFT_ORDER_LOOKUP_OPERATION_REF,
    PICKER_SHIFT_ORDER_LOOKUP_QUERY_FINGERPRINT,
    PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT,
    PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION,
    PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF,
    PICKER_SHIFT_ORDER_LOOKUP_SQL,
    GoogleBigQueryPickerShiftOrderLookupRunner,
    PickerShiftOrderLookupExecution,
    PickerShiftOrderLookupPreparedExecutor,
    PickerShiftOrderLookupRequest,
    PickerShiftOrderLookupRow,
    build_picker_shift_order_lookup_descriptor,
    build_picker_shift_order_lookup_plan,
)
from app.world_model import TruthClass

NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
PRINCIPAL_EMAIL = "corp-bigquery-readonly@fulfillment-dwh-production.iam.gserviceaccount.com"
IDENTITY = f"google-principal://{PRINCIPAL_EMAIL}"
ENVIRONMENT = "production"


class FakeRunner:
    def __init__(self, execution: PickerShiftOrderLookupExecution) -> None:
        self.execution = execution
        self.calls = 0

    def run(self, request: PickerShiftOrderLookupRequest) -> PickerShiftOrderLookupExecution:
        self.calls += 1
        assert request.tenant_id == "YS_TR"
        return self.execution


def _request(order_ids=("MLRN-2627-BMXL", "h962-2630-bxqj")):
    return PickerShiftOrderLookupRequest(
        order_ids=order_ids,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )


def _execution(
    *,
    observed_identity: str = IDENTITY,
) -> PickerShiftOrderLookupExecution:
    return PickerShiftOrderLookupExecution(
        rows=(
            PickerShiftOrderLookupRow(
                order_id="mlrn-2627-bmxl",
                rooster_employee_id="employee-1",
                user_id="user-1",
                rooster_rider_id=None,
                shopper_id="shopper-1",
                warehouse_id="warehouse-fulya",
                order_created_at_lt=datetime(
                    2026, 7, 8, 13, 15, tzinfo=timezone(timedelta(hours=3))
                ),
            ),
            PickerShiftOrderLookupRow(
                order_id="h962-2630-bxqj",
                rooster_employee_id="employee-2",
                user_id="user-2",
                rooster_rider_id="rider-2",
                shopper_id=None,
                warehouse_id="warehouse-uskudar",
                order_created_at_lt=datetime(
                    2026, 7, 20, 18, 45, tzinfo=timezone(timedelta(hours=3))
                ),
            ),
        ),
        job_id="job-picker-lookup-001",
        project_ref="fulfillment-dwh-production",
        location="EU",
        observed_execution_identity_ref=observed_identity,
        statement_type="SELECT",
        started_at=NOW + timedelta(seconds=1),
        completed_at=NOW + timedelta(seconds=3),
        total_bytes_processed=123456789,
        total_bytes_billed=123456789,
        schema_fingerprint="a" * 64,
    )


def _policy() -> LiveSourceBindingPolicy:
    return LiveSourceBindingPolicy(
        binding_id=PICKER_SHIFT_ORDER_LOOKUP_BINDING_ID,
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.WORKFORCE,
        source_ref=PICKER_SHIFT_ORDER_LOOKUP_SOURCE_REF,
        schema_contract=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_CONTRACT,
        schema_version=PICKER_SHIFT_ORDER_LOOKUP_SCHEMA_VERSION,
        environment_ref=ENVIRONMENT,
        execution_identity_ref=IDENTITY,
        verifier_ref="verifier://corp/bigquery-live-attestation",
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        max_observation_age_seconds=3600,
        max_attestation_age_seconds=3600,
        allowed_fields=PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS,
    )


def test_picker_lookup_request_normalizes_large_order_batch_and_static_sql_is_parameterized():
    order_ids = tuple(f"TEST-{index:04d}" for index in range(300)) + (
        "test-0001",
        "order_id",
    )
    request = _request(order_ids)
    assert len(request.order_ids) == 300
    assert request.order_ids[0] == "test-0000"
    assert request.order_ids[-1] == "test-0299"
    for parameter in ("@order_ids", "@global_entity_id", "@start_date", "@end_date"):
        assert parameter in PICKER_SHIFT_ORDER_LOOKUP_SQL
    assert "qc_picker_shift_orders" in PICKER_SHIFT_ORDER_LOOKUP_SQL
    upper = " " + " ".join(PICKER_SHIFT_ORDER_LOOKUP_SQL.upper().split()) + " "
    for token in (" INSERT ", " UPDATE ", " DELETE ", " MERGE ", " CREATE ", " DROP "):
        assert token not in upper
    assert len(PICKER_SHIFT_ORDER_LOOKUP_QUERY_FINGERPRINT) == 64


def test_picker_lookup_refuses_cross_tenant_unreviewed_window_and_opaque_identity():
    with pytest.raises(ValueError, match="picker_shift_lookup_only_ys_tr_reviewed"):
        PickerShiftOrderLookupRequest(
            tenant_id="DE_DE",
            global_entity_id="DE_DE",
            order_ids=("x-1",),
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
    with pytest.raises(ValueError, match="picker_shift_lookup_window_too_large"):
        PickerShiftOrderLookupRequest(
            order_ids=("x-1",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 7, 31),
        )
    with pytest.raises(
        ValueError,
        match="picker_shift_lookup_execution_identity_must_be_observable_google_principal",
    ):
        build_picker_shift_order_lookup_plan(
            environment_ref=ENVIRONMENT,
            execution_identity_ref="workload-identity://opaque-alias",
            requested_at=NOW,
        )


def test_prepared_lookup_emits_principal_bound_secret_safe_job_receipt():
    receipts = []
    runner = FakeRunner(_execution())
    executor = PickerShiftOrderLookupPreparedExecutor(
        request=_request(),
        runner=runner,
        execution_identity_ref=IDENTITY,
        receipt_recorder=receipts.append,
    )
    plan = build_picker_shift_order_lookup_plan(
        environment_ref=ENVIRONMENT,
        execution_identity_ref=IDENTITY,
        requested_at=NOW,
    )
    result = executor.execute(plan)

    assert runner.calls == 1
    assert result.proof.statement_type == "SELECT"
    assert result.proof.destination_write_detected is False
    assert len(result.fields) == 2 * len(PICKER_SHIFT_ORDER_LOOKUP_ALLOWED_FIELDS)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.success is True
    assert receipt.execution_identity_ref == IDENTITY
    assert receipt.row_count == 2
    assert receipt.total_bytes_processed == 123456789
    assert receipt.query_fingerprint == PICKER_SHIFT_ORDER_LOOKUP_QUERY_FINGERPRINT
    assert receipt.job_ref.endswith("/job-picker-lookup-001")
    assert receipt.truth_authority_granted is False
    assert receipt.execution_authority_granted is False
    receipt_json = receipt.model_dump_json()
    for sensitive_value in (
        "mlrn-2627-bmxl",
        "h962-2630-bxqj",
        "employee-1",
        "employee-2",
        "shopper-1",
        "warehouse-fulya",
    ):
        assert sensitive_value not in receipt_json


def test_prepared_lookup_rejects_job_executed_by_different_principal_before_receipt():
    receipts = []
    wrong_identity = "google-principal://unexpected-user@example.com"
    runner = FakeRunner(_execution(observed_identity=wrong_identity))
    executor = PickerShiftOrderLookupPreparedExecutor(
        request=_request(),
        runner=runner,
        execution_identity_ref=IDENTITY,
        receipt_recorder=receipts.append,
    )
    plan = build_picker_shift_order_lookup_plan(
        environment_ref=ENVIRONMENT,
        execution_identity_ref=IDENTITY,
        requested_at=NOW,
    )

    with pytest.raises(
        ValueError,
        match="picker_shift_lookup_observed_execution_identity_mismatch",
    ):
        executor.execute(plan)
    assert runner.calls == 1
    assert receipts == []


def test_lookup_composes_with_existing_registry_protocol_and_collection_runtime():
    receipts = []
    runner = FakeRunner(_execution())
    prepared = PickerShiftOrderLookupPreparedExecutor(
        request=_request(),
        runner=runner,
        execution_identity_ref=IDENTITY,
        receipt_recorder=receipts.append,
    )
    adapter_ref = "company-source://workforce/picker-shift-order-lookup/v1"
    registry = CompanySourceAdapterRegistry(
        tenant_id="YS_TR",
        adapters=(
            build_picker_shift_order_lookup_descriptor(
                environment_ref=ENVIRONMENT,
                execution_identity_ref=IDENTITY,
                acceptance=AdapterAcceptance.CONTROLLED,
            ),
        ),
    )
    plan = build_picker_shift_order_lookup_plan(
        environment_ref=ENVIRONMENT,
        execution_identity_ref=IDENTITY,
        requested_at=NOW,
    )
    result = execute_registered_company_read(
        registry=registry,
        plan=plan,
        policy=_policy(),
        adapter_ref=adapter_ref,
        runtime_bindings={
            adapter_ref: CompanySourceRuntimeBinding(
                adapter_ref=adapter_ref,
                protocol=CompanySourceProtocol.BIGQUERY,
                collector=ProtocolBoundCompanySourceAdapter(
                    protocol=CompanySourceProtocol.BIGQUERY,
                    executor=prepared,
                ),
            )
        },
    )

    assert result.route.acceptance is AdapterAcceptance.CONTROLLED
    assert result.route.field_production_verified is False
    assert result.truth_promoted is False
    assert result.execution_authority_granted is False
    assert result.collection.truth_promoted is False
    assert len(receipts) == 1


def test_descriptor_cannot_self_promote_to_field_proven():
    descriptor = build_picker_shift_order_lookup_descriptor(
        environment_ref=ENVIRONMENT,
        execution_identity_ref=IDENTITY,
    )
    assert descriptor.acceptance is AdapterAcceptance.REPOSITORY_ONLY
    assert descriptor.field_production_verified is False
    with pytest.raises(
        ValueError,
        match="picker_shift_lookup_field_proven_requires_external_attestation",
    ):
        build_picker_shift_order_lookup_descriptor(
            environment_ref=ENVIRONMENT,
            execution_identity_ref=IDENTITY,
            acceptance=AdapterAcceptance.FIELD_PROVEN,
        )


class _FakeArrayQueryParameter:
    def __init__(self, name, field_type, values):
        self.name = name
        self.field_type = field_type
        self.values = values


class _FakeScalarQueryParameter:
    def __init__(self, name, field_type, value):
        self.name = name
        self.field_type = field_type
        self.value = value


class _FakeQueryJobConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.destination = None


class _FakeBigQuery:
    QueryJobConfig = _FakeQueryJobConfig
    ArrayQueryParameter = _FakeArrayQueryParameter
    ScalarQueryParameter = _FakeScalarQueryParameter


class _SchemaField:
    def __init__(self, name, field_type, mode="NULLABLE"):
        self.name = name
        self.field_type = field_type
        self.mode = mode


class _FakeJob:
    job_id = "real-runner-job-1"
    project = "fulfillment-dwh-production"
    location = "EU"
    user_email = PRINCIPAL_EMAIL
    statement_type = "SELECT"
    error_result = None
    started = NOW + timedelta(seconds=1)
    ended = NOW + timedelta(seconds=2)
    total_bytes_processed = 42
    total_bytes_billed = 42
    schema = (
        _SchemaField("order_id", "STRING"),
        _SchemaField("rooster_employee_id", "STRING"),
        _SchemaField("user_id", "STRING"),
        _SchemaField("rooster_rider_id", "STRING"),
        _SchemaField("shopper_id", "STRING"),
        _SchemaField("warehouse_id", "STRING"),
        _SchemaField("order_created_at_lt", "DATETIME"),
    )

    def result(self):
        return (
            {
                "order_id": "mlrn-2627-bmxl",
                "rooster_employee_id": "employee-1",
                "user_id": "user-1",
                "rooster_rider_id": None,
                "shopper_id": "shopper-1",
                "warehouse_id": "warehouse-fulya",
                "order_created_at_lt": datetime(2026, 7, 8, 13, 15),
            },
        )


class _FakeBigQueryClient:
    def __init__(self):
        self.calls = []

    def query(self, query, *, job_config, location):
        self.calls.append((query, job_config, location))
        return _FakeJob()


def test_real_sdk_runner_shape_submits_only_static_query_with_typed_parameters(monkeypatch):
    client = _FakeBigQueryClient()
    runner = GoogleBigQueryPickerShiftOrderLookupRunner(
        project_id="fulfillment-dwh-production",
        location="EU",
        client=client,
    )
    monkeypatch.setattr(runner, "_bigquery", lambda: _FakeBigQuery)
    execution = runner.run(_request())

    assert execution.statement_type == "SELECT"
    assert execution.observed_execution_identity_ref == IDENTITY
    assert execution.rows[0].order_id == "mlrn-2627-bmxl"
    assert execution.rows[0].order_created_at_lt.utcoffset() == timedelta(hours=3)
    assert len(client.calls) == 1
    query, config, location = client.calls[0]
    assert query == PICKER_SHIFT_ORDER_LOOKUP_SQL
    assert location == "EU"
    assert config.maximum_bytes_billed == 50_000_000_000
    parameter_names = [item.name for item in config.query_parameters]
    assert parameter_names == ["order_ids", "global_entity_id", "start_date", "end_date"]
    assert config.query_parameters[0].values == ["mlrn-2627-bmxl", "h962-2630-bxqj"]
