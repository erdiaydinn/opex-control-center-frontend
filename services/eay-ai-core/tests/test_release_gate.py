from datetime import date

from app.canary_evals import CanaryMetrics
from app.historical_legal_rag_evals import (
    HistoricalLegalRagCase,
    evaluate_historical_legal_rag,
)
from app.release_gate import (
    HistoricalLegalReleaseMetrics,
    RagReleaseMetrics,
    SafetyReleaseMetrics,
    evaluate_release,
)
from app.safety_evals import SafetyEvalCase, evaluate_safety_evals


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


def _safety(**overrides):
    payload = dict(
        sample_size=24,
        pass_rate=1.0,
        teacher_rejection_bypass_rate=0.0,
        citation_loss_rate=0.0,
        temporal_block_bypass_rate=0.0,
        tool_answer_mismatch_rate=0.0,
        fingerprint="a" * 64,
    )
    payload.update(overrides)
    return SafetyReleaseMetrics(**payload)


def _rag():
    return RagReleaseMetrics(
        sample_size=120,
        pass_rate=1.0,
        temporal_validity_rate=1.0,
        legal_source_rate=1.0,
        duplicate_evidence_rate=0.0,
    )


def test_release_gate_promotes_only_when_rag_canary_historical_and_safety_pass():
    decision = evaluate_release(
        _canary(),
        _rag(),
        current_percent=5,
        historical_legal=_historical_legal(),
        safety=_safety(),
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
        safety=_safety(),
    )
    assert decision.promote is False
    assert "rag_temporal_validity_failed" in decision.violations
    assert "rag_legal_source_grounding_failed" in decision.violations
    assert decision.recommended_percent <= 5


def test_release_gate_fails_closed_without_historical_legal_eval():
    decision = evaluate_release(_canary(), _rag(), current_percent=5, safety=_safety())
    assert decision.promote is False
    assert "historical_legal_eval_missing" in decision.violations


def test_release_gate_fails_closed_without_cross_layer_safety_eval():
    decision = evaluate_release(
        _canary(),
        _rag(),
        current_percent=5,
        historical_legal=_historical_legal(),
    )
    assert decision.promote is False
    assert "cross_layer_safety_eval_missing" in decision.violations


def test_release_gate_blocks_inactive_legal_leak_and_temporal_bypass():
    decision = evaluate_release(
        _canary(),
        _rag(),
        current_percent=10,
        historical_legal=_historical_legal(
            pass_rate=0.95,
            source_match_rate=0.95,
            inactive_legal_leak_rate=0.05,
            temporal_block_bypass_rate=0.5,
        ),
        safety=_safety(),
    )
    assert decision.promote is False
    assert "historical_legal_pass_rate_failed" in decision.violations
    assert "historical_legal_source_match_failed" in decision.violations
    assert "inactive_legal_source_leak_detected" in decision.violations
    assert "temporal_legal_block_bypass_detected" in decision.violations


def test_release_gate_blocks_teacher_citation_temporal_and_tool_regressions():
    decision = evaluate_release(
        _canary(),
        _rag(),
        current_percent=10,
        historical_legal=_historical_legal(),
        safety=_safety(
            pass_rate=0.8,
            teacher_rejection_bypass_rate=0.05,
            citation_loss_rate=0.05,
            temporal_block_bypass_rate=0.05,
            tool_answer_mismatch_rate=0.05,
        ),
    )
    assert decision.promote is False
    assert "cross_layer_safety_pass_rate_failed" in decision.violations
    assert "teacher_quality_rejection_bypass_detected" in decision.violations
    assert "citation_loss_detected" in decision.violations
    assert "cross_layer_temporal_block_bypass_detected" in decision.violations
    assert "tool_answer_mismatch_detected" in decision.violations


def test_release_metrics_are_derived_losslessly_from_historical_eval_result():
    result = evaluate_historical_legal_rag(
        [
            HistoricalLegalRagCase(
                case_id="historical-v2",
                as_of=date(2026, 6, 1),
                expected_source_ids=("v2",),
                retrieved_source_ids=("v2",),
                temporal_resolution_fingerprint="a" * 64,
            )
        ]
    )
    metrics = HistoricalLegalReleaseMetrics.from_eval(result)
    assert metrics.sample_size == result.sample_size
    assert metrics.pass_rate == result.pass_rate
    assert metrics.source_match_rate == result.source_match_rate
    assert metrics.fingerprint_validity_rate == result.fingerprint_validity_rate
    assert metrics.inactive_legal_leak_rate == result.inactive_legal_leak_rate
    assert metrics.temporal_block_bypass_rate == result.temporal_block_bypass_rate


def test_safety_release_metrics_are_derived_losslessly_from_eval_result():
    result = evaluate_safety_evals(
        [
            SafetyEvalCase(
                case_id=f"safe-{idx}",
                expected_evidence_ids=("source-a",),
                cited_evidence_ids=("source-a",),
            )
            for idx in range(20)
        ]
    )
    metrics = SafetyReleaseMetrics.from_eval(result)
    assert metrics.sample_size == result.sample_size
    assert metrics.pass_rate == result.pass_rate
    assert metrics.citation_loss_rate == result.citation_loss_rate
    assert metrics.fingerprint == result.fingerprint
