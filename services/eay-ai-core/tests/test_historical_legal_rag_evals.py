from datetime import date

from app.historical_legal_rag_evals import (
    HistoricalLegalRagCase,
    evaluate_historical_legal_rag,
)


def test_historical_eval_accepts_date_specific_source_switch_and_blocked_case():
    fingerprint = "a" * 64
    result = evaluate_historical_legal_rag(
        [
            HistoricalLegalRagCase(
                case_id="before-switch",
                as_of=date(2026, 5, 31),
                expected_source_ids=("v1",),
                retrieved_source_ids=("v1",),
                temporal_resolution_fingerprint=fingerprint,
            ),
            HistoricalLegalRagCase(
                case_id="after-switch",
                as_of=date(2026, 6, 1),
                expected_source_ids=("v2",),
                retrieved_source_ids=("v2",),
                temporal_resolution_fingerprint="b" * 64,
            ),
            HistoricalLegalRagCase(
                case_id="ambiguous-graph",
                as_of=date(2026, 7, 1),
                expected_source_ids=(),
                retrieved_source_ids=(),
                temporal_resolution_fingerprint="c" * 64,
                resolution_blocked=True,
                model_called=False,
            ),
        ]
    )
    assert result.sample_size == 3
    assert result.pass_rate == 1.0
    assert result.source_match_rate == 1.0
    assert result.fingerprint_validity_rate == 1.0
    assert result.inactive_legal_leak_rate == 0.0
    assert result.temporal_block_bypass_rate == 0.0
    assert result.failures == ()


def test_historical_eval_detects_superseded_leak_missing_source_and_model_bypass():
    result = evaluate_historical_legal_rag(
        [
            HistoricalLegalRagCase(
                case_id="stale-source",
                as_of=date(2026, 6, 1),
                expected_source_ids=("v2",),
                retrieved_source_ids=("v1",),
                temporal_resolution_fingerprint="d" * 64,
            ),
            HistoricalLegalRagCase(
                case_id="blocked-but-called",
                as_of=date(2026, 7, 1),
                expected_source_ids=(),
                retrieved_source_ids=("v2",),
                temporal_resolution_fingerprint="not-a-sha",
                resolution_blocked=True,
                model_called=True,
            ),
        ]
    )
    assert result.pass_rate == 0.0
    assert result.source_match_rate == 0.0
    assert result.inactive_legal_leak_rate == 1.0
    assert result.temporal_block_bypass_rate == 1.0
    assert any(item.startswith("inactive_legal_source_leak:stale-source") for item in result.failures)
    assert any(item.startswith("expected_legal_source_missing:stale-source") for item in result.failures)
    assert "temporal_block_model_bypass:blocked-but-called" in result.failures
    assert "blocked_case_has_legal_evidence:blocked-but-called" in result.failures
    assert "invalid_temporal_fingerprint:blocked-but-called" in result.failures


def test_empty_historical_eval_cannot_look_healthy():
    result = evaluate_historical_legal_rag([])
    assert result.sample_size == 0
    assert result.pass_rate == 0.0
    assert result.source_match_rate == 0.0
    assert result.fingerprint_validity_rate == 0.0
