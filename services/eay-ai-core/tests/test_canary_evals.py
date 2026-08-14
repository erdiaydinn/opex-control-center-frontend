from app.canary_evals import CanaryMetrics, evaluate_canary


def healthy(**kwargs):
    values = dict(
        sample_size=500, error_rate=0.01, grounded_answer_rate=0.99,
        citation_validity_rate=0.999, unsafe_action_rate=0.0,
        kvkk_leak_rate=0.0, p95_latency_ms=3000,
    )
    values.update(kwargs)
    return CanaryMetrics(**values)


def test_healthy_canary_can_expand():
    decision = evaluate_canary(healthy(), current_percent=5)
    assert decision.promote
    assert decision.recommended_percent == 10


def test_unsafe_or_kvkk_failure_blocks_promotion():
    decision = evaluate_canary(healthy(unsafe_action_rate=0.001, kvkk_leak_rate=0.001), current_percent=10)
    assert not decision.promote
    assert "unsafe_action_detected" in decision.violations
    assert "kvkk_leak_detected" in decision.violations
    assert decision.recommended_percent <= 5


def test_small_sample_blocks_promotion():
    assert not evaluate_canary(healthy(sample_size=20), current_percent=5).promote
