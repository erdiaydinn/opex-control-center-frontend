from pathlib import Path

import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.tool_execution import TemplateToolExecutionRequest, execute_with_adapter, prepare_execution


class FakeAdapter:
    def __init__(self, *, dry_bytes=100, rows=None):
        self.dry_bytes = dry_bytes
        self.rows = rows or [{"vendor_name": "Test", "orders": 5}]
        self.last_sql = None
        self.last_parameters = None

    def dry_run(self, sql, parameters, *, timeout_ms):
        self.last_sql = sql
        self.last_parameters = parameters
        return self.dry_bytes

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        self.last_sql = sql
        self.last_parameters = parameters
        return self.rows


def test_template_execution_rejects_missing_scope(tmp_path):
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "milk", "field": "product", "limit": 10},
        granted_scopes=[],
        reason="catalog lookup",
    )
    with pytest.raises(PermissionError, match="catalog:read"):
        prepare_execution(payload)


def test_template_execution_never_accepts_model_sql(tmp_path):
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "milk", "field": "product", "limit": 10},
        granted_scopes=["catalog:read"],
        reason="catalog lookup",
    )
    request, query_id, scopes = prepare_execution(payload)
    assert query_id == "catalog.lookup.v1"
    assert scopes == ["catalog:read"]
    assert "pandora__vendor_products_qcomm_catalog_details" in request.sql
    assert "milk" not in request.sql
    assert request.parameters["query"] == "milk"


def test_template_execution_runs_bounded_query_and_audits(tmp_path):
    db = tmp_path / "eay.db"
    payload = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={"query": "egg", "field": "product", "limit": 10},
        granted_scopes=["catalog:read"],
        requested_by="test-user",
        reason="impact review",
        execute=True,
        max_rows=2,
        maximum_bytes_billed=1000,
    )
    adapter = FakeAdapter(rows=[{"product_name": "Egg", "email": "user@example.com"}])
    result = execute_with_adapter(payload, adapter=adapter, audit_store=ExecutionAuditStore(db))
    assert result.query_id == "catalog.lookup.v1"
    assert result.model_authored_sql_allowed is False
    assert result.execution.status == "executed"
    assert "LIMIT 2" in adapter.last_sql
    assert result.execution.rows[0]["email"] != "user@example.com"
