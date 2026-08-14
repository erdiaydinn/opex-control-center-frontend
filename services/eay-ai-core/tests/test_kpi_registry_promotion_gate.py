import pytest

from app.kpi_registry_promotion_gate import (
    seal_kpi_registry_promotion,
    verify_registered_kpi_promotion,
)


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64


class Artifact:
    metric = "picking"
    approved_for_registry_review = True
    executable = False
    schema_fingerprint = FP_B
    fingerprint = FP_A


def make_decision():
    return seal_kpi_registry_promotion(
        metric="picking",
        query_id="ops.kpi.picking.v1",
        review_artifact=Artifact(),
        query_template_fingerprint=FP_C,
        schema_fingerprint=FP_B,
        promotion_reference="KPI-PROMO-2026-001",
        reviewer="ops-metric-owner",
        reviewed_at="2026-08-11T12:00:00+00:00",
    )


def verify_args(decision, **overrides):
    payload = {
        "promotion_fingerprint": decision.fingerprint,
        "metric": "picking",
        "query_id": "ops.kpi.picking.v1",
        "query_template_fingerprint": FP_C,
        "schema_fingerprint": FP_B,
        "review_artifact_fingerprint": FP_A,
        "promotions": {decision.fingerprint: decision},
    }
    payload.update(overrides)
    return payload


def test_registry_promotion_binds_review_artifact_template_and_schema_but_stays_non_executable():
    decision = make_decision()
    assert decision.approved_for_registry_change is True
    assert decision.executable is False
    assert decision.review_artifact_fingerprint == FP_A
    assert decision.query_template_fingerprint == FP_C
    assert decision.schema_fingerprint == FP_B
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


def test_random_promotion_hash_cannot_authorize_registry_execution():
    with pytest.raises(ValueError, match="kpi_registry_promotion_decision_not_registered:picking"):
        verify_registered_kpi_promotion(
            promotion_fingerprint="9" * 64,
            metric="picking",
            query_id="ops.kpi.picking.v1",
            query_template_fingerprint=FP_C,
            schema_fingerprint=FP_B,
            review_artifact_fingerprint=FP_A,
            promotions={},
        )


def test_exact_registered_promotion_decision_is_revalidated_before_use():
    decision = make_decision()
    verified = verify_registered_kpi_promotion(**verify_args(decision))
    assert verified == decision


def test_registered_promotion_is_invalidated_by_query_template_drift():
    decision = make_decision()
    with pytest.raises(ValueError, match="kpi_registry_promotion_decision_template_drift:picking"):
        verify_registered_kpi_promotion(
            **verify_args(decision, query_template_fingerprint="d" * 64)
        )


def test_registered_promotion_is_invalidated_by_schema_drift():
    decision = make_decision()
    with pytest.raises(ValueError, match="kpi_registry_promotion_decision_schema_drift:picking"):
        verify_registered_kpi_promotion(**verify_args(decision, schema_fingerprint="d" * 64))


def test_registered_promotion_is_invalidated_by_review_artifact_drift():
    decision = make_decision()
    with pytest.raises(
        ValueError, match="kpi_registry_promotion_decision_review_artifact_drift:picking"
    ):
        verify_registered_kpi_promotion(
            **verify_args(decision, review_artifact_fingerprint="d" * 64)
        )
