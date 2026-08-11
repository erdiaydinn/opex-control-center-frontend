import pytest

from app.kpi_schema_evidence import KpiSchemaEvidence
from app.kpi_schema_manifest import (
    KpiSchemaManifestApproval,
    build_schema_evidence_manifest,
    verify_schema_manifest_approval,
)


def _evidence(**overrides):
    payload = {
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "observed_columns": {
            "orders_ok": "INT64",
            "partial_cnt": "INT64",
            "refund_cnt": "INT64",
        },
        "captured_at": "2026-08-11T06:00:00Z",
        "source": "BigQuery INFORMATION_SCHEMA.COLUMNS export",
        "reviewer": "schema-reviewer",
        "reviewed": True,
    }
    payload.update(overrides)
    return KpiSchemaEvidence(**payload)


def _approval(manifest, **overrides):
    payload = {
        "manifest_fingerprint": manifest.fingerprint,
        "approval_ref": "KPI-SCHEMA-2026-001",
        "reviewer": "metric-owner",
        "approved_at": "2026-08-11T06:10:00Z",
    }
    payload.update(overrides)
    return KpiSchemaManifestApproval(**payload)


def test_schema_manifest_binds_exact_reviewed_evidence_and_approval():
    evidence = _evidence()
    manifest = build_schema_evidence_manifest(manifest_id="nsfr-schema-2026-08-11", evidence=evidence)
    result = verify_schema_manifest_approval(manifest, _approval(manifest))

    assert manifest.evidence_fingerprint == evidence.fingerprint
    assert len(manifest.fingerprint) == 64
    assert result["verified"] is True
    assert result["evidence_fingerprint"] == evidence.fingerprint
    assert len(str(result["approval_fingerprint"])) == 64


def test_schema_manifest_changes_when_observed_type_changes():
    baseline = build_schema_evidence_manifest(manifest_id="nsfr-schema-1", evidence=_evidence())
    changed = _evidence(observed_columns={"orders_ok": "INT64", "partial_cnt": "NUMERIC", "refund_cnt": "INT64"})
    drifted = build_schema_evidence_manifest(manifest_id="nsfr-schema-1", evidence=changed)
    assert baseline.fingerprint != drifted.fingerprint


def test_schema_manifest_requires_reviewed_evidence():
    with pytest.raises(ValueError, match="kpi_schema_manifest_reviewed_evidence_required"):
        build_schema_evidence_manifest(
            manifest_id="nsfr-schema-1",
            evidence=_evidence(reviewed=False, reviewer=None),
        )


def test_schema_manifest_approval_rejects_stale_manifest():
    manifest = build_schema_evidence_manifest(manifest_id="nsfr-schema-1", evidence=_evidence())
    with pytest.raises(ValueError, match="kpi_schema_manifest_approval_manifest_mismatch"):
        verify_schema_manifest_approval(
            manifest,
            _approval(manifest, manifest_fingerprint="a" * 64),
        )


def test_schema_manifest_approval_requires_explicit_reference():
    manifest = build_schema_evidence_manifest(manifest_id="nsfr-schema-1", evidence=_evidence())
    with pytest.raises(ValueError, match="kpi_schema_manifest_approval_ref_required"):
        verify_schema_manifest_approval(manifest, _approval(manifest, approval_ref=""))
