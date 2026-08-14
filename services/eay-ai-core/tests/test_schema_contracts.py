import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.schema_contracts import get_schema_contract, verify_table_schema
from app.tool_execution import TemplateToolExecutionRequest, execute_with_adapter


class OpsAdapter:
    def __init__(self, schema):
        self.schema = schema
        self.last_sql = None

    def table_schema(self, table_id):
        assert table_id == "curated_data_shared_coredata_business.orders"
        return self.schema

    def dry_run(self, sql, parameters, *, timeout_ms):
        self.last_sql = sql
        return 100

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        self.last_sql = sql
        return [{"date": "2026-08-10", "vendor_name": "Fulya", "orders": 42}]


def _payload(execute=False):
    return TemplateToolExecutionRequest(
        tool="ops_kpi_query",
        arguments={
            "metric": "orders",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "stores": ["Fulya"],
            "limit": 20,
        },
        granted_scopes=["ops:read"],
        reason="orders review",
        execute=execute,
        maximum_bytes_billed=1000,
    )


def test_orders_contract_fingerprint_is_deterministic_and_ignores_extra_columns():
    contract = get_schema_contract("ops.orders.v1")
    base = {
        "order_id": "STRING",
        "partition_date_local": "DATE",
        "vendor_name": "STRING",
    }
    with_extra = {**base, "unrelated_new_column": "FLOAT64"}
    first = verify_table_schema(contract, base)
    second = verify_table_schema(contract, with_extra)
    assert first["expected_fingerprint"] == first["observed_fingerprint"]
    assert second["observed_fingerprint"] == first["observed_fingerprint"]


def test_schema_gate_rejects_missing_required_column():
    contract = get_schema_contract("ops.orders.v1")
    with pytest.raises(ValueError, match="schema_contract_mismatch"):
        verify_table_schema(
            contract,
            {"order_id": "STRING", "partition_date_local": "DATE"},
        )


def test_schema_gate_rejects_required_column_type_drift():
    contract = get_schema_contract("ops.orders.v1")
    with pytest.raises(ValueError, match="type_mismatches"):
        verify_table_schema(
            contract,
            {
                "order_id": "INT64",
                "partition_date_local": "DATE",
                "vendor_name": "STRING",
            },
        )


def test_ops_execution_verifies_schema_before_dry_run(tmp_path):
    adapter = OpsAdapter(
        {
            "order_id": "STRING",
            "partition_date_local": "DATE",
            "vendor_name": "STRING",
            "extra": "BOOL",
        }
    )
    result = execute_with_adapter(
        _payload(),
        adapter=adapter,
        audit_store=ExecutionAuditStore(tmp_path / "eay.db"),
    )
    assert result.execution.status == "dry_run_ok"
    assert result.schema_verification["verified"] is True
    assert result.schema_verification["contract_id"] == "ops.orders.v1"


def test_ops_execution_fails_closed_before_query_when_schema_drifts(tmp_path):
    adapter = OpsAdapter(
        {
            "order_id": "STRING",
            "partition_date_local": "TIMESTAMP",
            "vendor_name": "STRING",
        }
    )
    with pytest.raises(ValueError, match="schema_contract_mismatch"):
        execute_with_adapter(
            _payload(),
            adapter=adapter,
            audit_store=ExecutionAuditStore(tmp_path / "eay.db"),
        )
    assert adapter.last_sql is None


def test_ops_execution_requires_schema_introspection(tmp_path):
    class NoSchemaAdapter:
        def dry_run(self, sql, parameters, *, timeout_ms):
            raise AssertionError("dry run must not happen")

        def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
            raise AssertionError("execute must not happen")

    with pytest.raises(ValueError, match="schema_introspection_not_supported"):
        execute_with_adapter(
            _payload(),
            adapter=NoSchemaAdapter(),
            audit_store=ExecutionAuditStore(tmp_path / "eay.db"),
        )
