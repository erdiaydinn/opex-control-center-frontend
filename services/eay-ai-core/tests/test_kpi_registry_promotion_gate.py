import pytest

from app.kpi_registry_promotion_gate import seal_kpi_registry_promotion


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


class Artifact:
    metric = "picking"
    approved_for_registry_review = True
    executable = False
    schema_fingerprint = FP_B
    fingerprint = FP_A


def test_registry_promotion_binds_review_artifact_template_and_schema_but_stays_non_executable():
    decision = seal_kpi_registry_promotion(
        metric="picking",
        query_id="ops.kpi.picking.v1",
        review_artifact=Artifact(),
        query_template_fingerprint=FP_C,
        schema_fingerprint=FP_B,
        promotion_reference="KPI-PROMO-2026-001",
        reviewer="ops-metric-owner",
        reviewed_at="2026-08-11T12:00:00+00:00",
    )
    assert decision.approved_for_registry_change is True
    assert decision.executable is False
    assert decision.review_artifact_fingerprint == FP_A
    assert decision.query_template_fingerprint == FP_C
    assert len(decision.fingerprint) == 64


def test_registry_promotion_rejects_stale_schema():
    with pytest.raises(ValueError, match="kpi_registry_promotion_schema_mismatch"):
        seal_kpi_registry_promotion(
            metric="picking",
            query_id="ops.kpi.picking.v1",
            review_artifact=Artifact(),
            query_template_fingerprint=FP_C,
            schema_fingerprint="d" * 64,
            promotion_reference="KPI-PROMO-2026-001",
            reviewer="ops-metric-owner",
            reviewed_at="2026-08-11T12:00:00+00:00",
        )


def test_registry_promotion_rejects_executable_review_artifact():
    artifact = {
        "metric": "otp",
        "approved_for_registry_review": True,
        "executable": True,
        "schema_fingerprint": FP_B,
        "fingerprint": FP_A,
    }
    with pytest.raises(ValueError, match="review_artifact_must_be_non_executable"):
        seal_kpi_registry_promotion(
            metric="otp",
            query_id="ops.kpi.otp.v1",
            review_artifact=artifact,
            query_template_fingerprint=FP_C,
            schema_fingerprint=FP_B,
            promotion_reference="KPI-PROMO-2026-002",
            reviewer="ops-metric-owner",
            reviewed_at="2026-08-11T12:00:00+00:00",
        )


def test_registry_promotion_rejects_cross_metric_artifact():
    with pytest.raises(ValueError, match="kpi_registry_promotion_artifact_metric_mismatch"):
        seal_kpi_registry_promotion(
            metric="otp",
            query_id="ops.kpi.otp.v1",
            review_artifact=Artifact(),
            query_template_fingerprint=FP_C,
            schema_fingerprint=FP_B,
            promotion_reference="KPI-PROMO-2026-003",
            reviewer="ops-metric-owner",
            reviewed_at="2026-08-11T12:00:00+00:00",
        )


def test_registry_promotion_requires_second_human_promotion_reference():
    with pytest.raises(ValueError, match="kpi_registry_promotion_human_approval_required"):
        seal_kpi_registry_promotion(
            metric="picking",
            query_id="ops.kpi.picking.v1",
            review_artifact=Artifact(),
            query_template_fingerprint=FP_C,
            schema_fingerprint=FP_B,
            promotion_reference=" ",
            reviewer="ops-metric-owner",
            reviewed_at="2026-08-11T12:00:00+00:00",
        )
