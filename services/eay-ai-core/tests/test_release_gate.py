from app.canary_evals import CanaryMetrics
from app.release_gate import (
    HistoricalLegalReleaseMetrics,
    RagReleaseMetrics,
    evaluate_release,
)


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


def _historical_legal(**overrides):
    payload = dict(
        sample_size=24,
        pass_rate=1.0,
        source_match_rate=1.0,
        fingerprint_validity_rate=1.0,
        inactive_legal_leak_rate=0.0,
        temporal_block_bypass_rate=0.0,
    )
    payload.update(overrides)
    return HistoricalLegalReleaseMetrics(**payload)


def test_release_gate_promotes_only_when_rag_canary_and_historical_legal_pass():
    rag = RagReleaseMetrics(
        sample_size=120,
        pass_rate=1.0,
        temporal_validity_rate=1.0,
        legal_source_rate=1.0,
        duplicate_evidence_rate=0.0,
    )
    decision = evaluate_release(
        _canary(),
        rag,
        current_percent=5,
        historical_legal=_historical_legal(),
    )
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
    decision = evaluate_release(
        _canary(),
        rag,
        current_percent=10,
        historical_legal=_historical_legal(),
    )
    assert decision.promote is False
    assert "rag_temporal_validity_failed" in decision.violations
    assert "rag_legal_source_grounding_failed" in decision.violations
    assert decision.recommended_percent <= 5


def test_release_gate_fails_closed_without_historical_legal_eval():
    rag = RagReleaseMetrics(
        sample_size=120,
        pass_rate=1.0,
        temporal_validity_rate=1.0,
        legal_source_rate=1.0,
        duplicate_evidence_rate=0.0,
    )
    decision = evaluate_release(_canary(), rag, current_percent=5)
    assert decision.promote is False
    assert "historical_legal_eval_missing" in decision.violations


def test_release_gate_blocks_inactive_legal_leak_and_temporal_bypass():
    rag = RagReleaseMetrics(
        sample_size=120,
        pass_rate=1.0,
        temporal_validity_rate=1.0,
        legal_source_rate=1.0,
        duplicate_evidence_rate=0.0,
    )
    decision = evaluate_release(
        _canary(),
        rag,
        current_percent=10,
        historical_legal=_historical_legal(
            pass_rate=0.95,
            source_match_rate=0.95,
            inactive_legal_leak_rate=0.05,
            temporal_block_bypass_rate=0.5,
        ),
    )
    assert decision.promote is False
    assert "historical_legal_pass_rate_failed" in decision.violations
    assert "historical_legal_source_match_failed" in decision.violations
    assert "inactive_legal_source_leak_detected" in decision.violations
    assert "temporal_legal_block_bypass_detected" in decision.violations
