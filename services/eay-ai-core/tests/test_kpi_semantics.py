import sqlite3

import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.kpi_registry import get_kpi_definition
from app.kpi_semantics import get_semantic_contract, verify_semantic_contract
from app.tool_execution import TemplateToolExecutionRequest, execute_with_adapter


class OrdersAdapter:
    def __init__(self):
        self.dry_run_called = False

    def table_schema(self, table_id):
        assert table_id == "curated_data_shared_coredata_business.orders"
        return {
            "order_id": "STRING",
            "partition_date_local": "DATE",
            "vendor_name": "STRING",
            "unrelated_new_column": "STRING",
        }

    def dry_run(self, sql, parameters, *, timeout_ms):
        self.dry_run_called = True
        return 100

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        return [{"date": "2026-08-10", "vendor_name": "Fulya", "orders": 5}]


def test_orders_semantic_contract_is_reviewed_and_fingerprinted():
    definition = get_kpi_definition("orders")
    result = verify_semantic_contract(
        metric="orders", contract_id=definition.semantic_contract_id
    )
    assert result["reviewed"] is True
    assert len(result["fingerprint"]) == 64
    assert result["contract_id"] == "ops.orders.semantic.v1"


def test_nsfr_contract_pins_precedence_and_semantics_but_schema_stays_separate():
    definition = get_kpi_definition("nsfr")
    contract = get_semantic_contract(definition.semantic_contract_id)
    assert contract.precedence == (
        "PFR overrides Refund",
        "Refund overrides Compensation",
    )
    assert contract.denominator == "successful_orders"
    assert contract.review_state == "reviewed"
    result = verify_semantic_contract(metric="nsfr", contract_id=definition.semantic_contract_id)
    assert result["reviewed"] is True
    assert definition.executable is False
    assert definition.schema_contract_id is None


@pytest.mark.parametrize("metric", ["pfr", "refund"])
def test_nsfr_component_semantics_are_reviewed_without_enabling_execution(metric):
    definition = get_kpi_definition(metric)
    result = verify_semantic_contract(metric=metric, contract_id=definition.semantic_contract_id)
    assert result["reviewed"] is True
    assert definition.executable is False
    assert definition.schema_contract_id is None


def test_semantic_contract_rejects_metric_binding_mismatch():
    with pytest.raises(ValueError, match="kpi_semantic_contract_metric_mismatch"):
        verify_semantic_contract(metric="refund", contract_id="ops.orders.semantic.v1")


def test_orders_execution_returns_and_audits_both_contract_fingerprints(tmp_path):
    db = tmp_path / "eay.db"
    payload = TemplateToolExecutionRequest(
        tool="ops_kpi_query",
        arguments={
            "metric": "orders",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
            "stores": ["Fulya"],
            "limit": 20,
        },
        granted_scopes=["ops:read"],
        reason="review orders",
        execute=False,
    )
    adapter = OrdersAdapter()
    result = execute_with_adapter(
        payload,
        adapter=adapter,
        audit_store=ExecutionAuditStore(db),
    )
    assert result.semantic_verification["reviewed"] is True
    assert len(result.semantic_verification["fingerprint"]) == 64
    assert result.schema_verification["verified"] is True
    assert len(result.schema_verification["expected_fingerprint"]) == 64
    assert adapter.dry_run_called is True

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """
            SELECT semantic_contract_id, semantic_fingerprint,
                   schema_contract_id, schema_fingerprint
            FROM bigquery_execution_audit
            WHERE id = ?
            """,
            (result.execution.execution_id,),
        ).fetchone()
    assert row[0] == "ops.orders.semantic.v1"
    assert row[1] == result.semantic_verification["fingerprint"]
    assert row[2] == "ops.orders.v1"
    assert row[3] == result.schema_verification["observed_fingerprint"]
