from app.canary_evals import CanaryMetrics
from app.release_gate import RagReleaseMetrics, evaluate_release


def _canary():
    return CanaryMetrics(
        sample_size=250,
        error_rate=0.01,
        grounded_answer_rate=0.99,
        citation_validity_rate=0.999,
        unsafe_action_rate=0.0,
        kvkk_leak_rate=0.0,
        p95_latency_ms=3000,
    )


def test_release_gate_promotes_only_when_rag_and_canary_pass():
    rag = RagReleaseMetrics(
        sample_size=120,
        pass_rate=1.0,
        temporal_validity_rate=1.0,
        legal_source_rate=1.0,
        duplicate_evidence_rate=0.0,
    )
    decision = evaluate_release(_canary(), rag, current_percent=5)
    assert decision.promote is True
    assert decision.recommended_percent == 10


def test_release_gate_blocks_temporal_or_legal_grounding_regression():
    rag = RagReleaseMetrics(
        sample_size=120,
        pass_rate=0.995,
        temporal_validity_rate=0.99,
        legal_source_rate=0.98,
        duplicate_evidence_rate=0.0,
    )
    decision = evaluate_release(_canary(), rag, current_percent=10)
    assert decision.promote is False
    assert "rag_temporal_validity_failed" in decision.violations
    assert "rag_legal_source_grounding_failed" in decision.violations
    assert decision.recommended_percent <= 5
