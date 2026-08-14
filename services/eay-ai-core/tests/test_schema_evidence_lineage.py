import sqlite3

import pytest

from app.bigquery_safe_executor import ExecuteRequest, ExecutionAuditStore
from app.kpi_schema_evidence import KpiSchemaEvidence
from app.schema_contracts import (
    schema_contract_from_reviewed_evidence,
    verify_table_schema,
)
from app.tool_execution import _attach_contract_audit


TABLE = "report_dmart_ops_nsfr_global_overview"
REQUIRED = (
    "successful_orders",
    "pfr_orders",
    "refund_orders",
    "compensation_orders",
    "nsfr_orders",
)


def _evidence(table_id=TABLE):
    return KpiSchemaEvidence(
        table_id=table_id,
        observed_columns={name: "INT64" for name in REQUIRED},
        captured_at="2026-08-10T20:00:00+00:00",
        source="BigQuery INFORMATION_SCHEMA.COLUMNS export",
        reviewer="human-reviewer",
        reviewed=True,
    )


def test_contract_derived_from_reviewed_evidence_preserves_lineage():
    evidence = _evidence()
    contract = schema_contract_from_reviewed_evidence(
        contract_id="ops.nsfr.v1",
        expected_table=TABLE,
        evidence=evidence,
        required_columns=REQUIRED,
    )

    assert contract.table_id == TABLE
    assert contract.evidence_fingerprint == evidence.fingerprint
    assert {column.name: column.field_type for column in contract.required_columns} == {
        name: "INT64" for name in REQUIRED
    }

    verified = verify_table_schema(contract, {name: "INT64" for name in REQUIRED})
    assert verified["verified"] is True
    assert verified["evidence_fingerprint"] == evidence.fingerprint


def test_contract_derivation_rejects_evidence_from_another_table():
    with pytest.raises(ValueError, match="kpi_schema_evidence_table_mismatch"):
        schema_contract_from_reviewed_evidence(
            contract_id="ops.nsfr.v1",
            expected_table=TABLE,
            evidence=_evidence("wrong_table"),
            required_columns=REQUIRED,
        )


def test_contract_audit_persists_schema_evidence_fingerprint(tmp_path):
    request = ExecuteRequest(
        tool="ops_kpi_query",
        sql="SELECT 1",
        parameters={},
        reason="lineage test",
        max_rows=1,
    )
    evidence_fp = "a" * 64
    request = _attach_contract_audit(
        request,
        semantic_verification={
            "contract_id": "ops.nsfr.semantic.v1",
            "fingerprint": "b" * 64,
        },
        schema_verification={
            "contract_id": "ops.nsfr.v1",
            "observed_fingerprint": "c" * 64,
            "evidence_fingerprint": evidence_fp,
        },
    )

    store = ExecutionAuditStore(tmp_path / "eay.db")
    execution_id = store.save(payload=request, dry_run_bytes=0, status="dry_run_ok")

    with sqlite3.connect(tmp_path / "eay.db") as conn:
        row = conn.execute(
            """
            SELECT schema_contract_id, schema_fingerprint, schema_evidence_fingerprint
            FROM bigquery_execution_audit WHERE id = ?
            """,
            (execution_id,),
        ).fetchone()

    assert row == ("ops.nsfr.v1", "c" * 64, evidence_fp)
