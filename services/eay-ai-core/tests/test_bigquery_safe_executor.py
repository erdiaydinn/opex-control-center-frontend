import sqlite3

from app.bigquery_safe_executor import ExecuteRequest, ExecutionAuditStore, SafeBigQueryExecutor, mask_sensitive_rows
from app.kpi_aggregation_contracts import WeightedAverageContract
from app.kpi_unit_contracts import DurationContract, RateContract


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


def test_unit_contract_fingerprints_are_deterministic_and_semantic():
    minutes = DurationContract(metric="picking", source_unit="minutes")
    seconds = DurationContract(metric="picking", source_unit="seconds")
    fraction = RateContract(metric="late_prep", source_scale="fraction")
    percent = RateContract(metric="late_prep", source_scale="percent")

    assert len(minutes.fingerprint) == 64
    assert minutes.fingerprint == DurationContract(metric="picking", source_unit="minutes").fingerprint
    assert minutes.fingerprint != seconds.fingerprint
    assert fraction.fingerprint != percent.fingerprint


def test_execution_audit_persists_unit_and_aggregation_contract_fingerprints(tmp_path):
    db = tmp_path / "audit.db"
    unit_contract = DurationContract(metric="picking", source_unit="minutes")
    aggregation_contract = WeightedAverageContract(
        metric="picking",
        source_grain="picker_day",
        value_field="picking_time_min",
        weight_field="eligible_orders",
        output_unit="seconds_per_order",
    )
    executor = SafeBigQueryExecutor(FakeAdapter(dry_bytes=50), ExecutionAuditStore(db))
    result = executor.run(
        payload(
            unit_contract_fingerprint=unit_contract.fingerprint,
            aggregation_contract_fingerprint=aggregation_contract.fingerprint,
        ),
        execute=False,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """
            SELECT unit_contract_fingerprint, aggregation_contract_fingerprint
            FROM bigquery_execution_audit
            WHERE id = ?
            """,
            (result.execution_id,),
        ).fetchone()

    assert row == (unit_contract.fingerprint, aggregation_contract.fingerprint)


def test_execution_audit_persists_combined_activation_provenance(tmp_path):
    db = tmp_path / "audit.db"
    fingerprint = "a" * 64
    executor = SafeBigQueryExecutor(FakeAdapter(dry_bytes=50), ExecutionAuditStore(db))
    result = executor.run(
        payload(activation_provenance_fingerprint=fingerprint),
        execute=False,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT activation_provenance_fingerprint FROM bigquery_execution_audit WHERE id = ?",
            (result.execution_id,),
        ).fetchone()

    assert row == (fingerprint,)


def test_execution_audit_persists_policy_and_formula_contract_fingerprints(tmp_path):
    db = tmp_path / "audit.db"
    policy = "b" * 64
    formula = "c" * 64
    executor = SafeBigQueryExecutor(FakeAdapter(dry_bytes=50), ExecutionAuditStore(db))
    result = executor.run(
        payload(
            policy_contract_fingerprint=policy,
            formula_contract_fingerprint=formula,
        ),
        execute=False,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """
            SELECT policy_contract_fingerprint, formula_contract_fingerprint
            FROM bigquery_execution_audit WHERE id = ?
            """,
            (result.execution_id,),
        ).fetchone()

    assert row == (policy, formula)


def test_execution_audit_persists_result_contract_fingerprint(tmp_path):
    db = tmp_path / "audit.db"
    result_contract = "d" * 64
    executor = SafeBigQueryExecutor(FakeAdapter(dry_bytes=50), ExecutionAuditStore(db))
    result = executor.run(
        payload(result_contract_fingerprint=result_contract),
        execute=False,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT result_contract_fingerprint FROM bigquery_execution_audit WHERE id = ?",
            (result.execution_id,),
        ).fetchone()

    assert row == (result_contract,)
