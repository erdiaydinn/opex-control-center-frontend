from app.context_intelligence import RelationStatus, assess_relation
from tests.test_context_intelligence import _marathon_signal, _orders


def test_matching_event_is_not_attributed_when_operation_is_within_normal_band():
    normal_orders = _orders().model_copy(update={"value": 9900, "baseline_value": 10000})

    relation = assess_relation(_marathon_signal(), normal_orders)

    assert relation.status is RelationStatus.INSUFFICIENT
    assert relation.deviation_pct == -1.0
    assert "operational_anomaly_not_material" in relation.blockers


def test_missing_baseline_can_only_produce_context_candidate():
    orders_without_baseline = _orders().model_copy(update={"baseline_value": None})

    relation = assess_relation(_marathon_signal(), orders_without_baseline)

    assert relation.status is RelationStatus.CONTEXT_CANDIDATE
    assert relation.deviation_pct is None
    assert relation.anomaly_strength == 0.0
    assert "baseline_evidence_missing" in relation.warnings
