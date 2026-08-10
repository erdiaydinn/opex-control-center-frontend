from app.bigquery_safe_executor import ExecuteRequest, ExecutionAuditStore, SafeBigQueryExecutor, mask_sensitive_rows


class FakeAdapter:
    def __init__(self, dry_bytes=100, rows=None):
        self.dry_bytes = dry_bytes
        self.rows = rows or []
        self.executed = False

    def dry_run(self, sql, parameters, *, timeout_ms):
        assert "LIMIT" in sql
        return self.dry_bytes

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        self.executed = True
        return self.rows


def payload(**kwargs):
    data = dict(
        tool="ops_kpi_query",
        sql="SELECT * FROM `project.curated_data_shared.orders`",
        parameters={},
        requested_by="test",
        reason="unit test",
        max_rows=10,
        maximum_bytes_billed=1000,
        timeout_ms=5000,
    )
    data.update(kwargs)
    return ExecuteRequest(**data)


def test_rejects_query_above_dry_run_budget(tmp_path):
    adapter = FakeAdapter(dry_bytes=5000)
    executor = SafeBigQueryExecutor(adapter, ExecutionAuditStore(tmp_path / "audit.db"))
    result = executor.run(payload(maximum_bytes_billed=1000), execute=True)
    assert result.status == "rejected_cost"
    assert adapter.executed is False


def test_dry_run_does_not_execute(tmp_path):
    adapter = FakeAdapter(dry_bytes=50)
    executor = SafeBigQueryExecutor(adapter, ExecutionAuditStore(tmp_path / "audit.db"))
    result = executor.run(payload(), execute=False)
    assert result.status == "dry_run_ok"
    assert adapter.executed is False


def test_execution_masks_sensitive_columns(tmp_path):
    adapter = FakeAdapter(dry_bytes=50, rows=[{"email": "person@example.com", "warehouse": "Fulya", "tc": "12345678901"}])
    executor = SafeBigQueryExecutor(adapter, ExecutionAuditStore(tmp_path / "audit.db"))
    result = executor.run(payload(), execute=True)
    assert result.status == "executed"
    assert result.rows[0]["warehouse"] == "Fulya"
    assert result.rows[0]["email"] != "person@example.com"
    assert result.rows[0]["tc"] != "12345678901"


def test_masking_handles_short_values():
    assert mask_sensitive_rows([{"phone": "123"}])[0]["phone"] == "***"
