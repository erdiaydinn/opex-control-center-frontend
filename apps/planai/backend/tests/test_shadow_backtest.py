from shadow_backtest import evaluate_shadow_backtest


def _pair(index, picking_before, picking_after):
    return {
        "pair_id": f"pair-{index}",
        "store_code": "STORE-1",
        "window_id": f"week-{index}",
        "source_ref": f"warehouse://planogram/{index}",
        "attested": True,
        "baseline": {
            "picking_seconds_per_order": picking_before,
            "oos_rate_pct": 2.0,
        },
        "candidate": {
            "picking_seconds_per_order": picking_after,
            "oos_rate_pct": 1.5,
        },
    }


def test_paired_backtest_reports_directional_improvement_without_causal_claim():
    result = evaluate_shadow_backtest(
        pairs=[_pair(1, 100, 90), _pair(2, 110, 100), _pair(3, 120, 115)]
    )
    assert result["available"] is True
    assert result["minimum_pair_gate_passed"] is True
    assert result["metric_summaries"]["picking_seconds_per_order"]["win_rate_pct"] == 100.0
    assert result["causal_claim_allowed"] is False
    assert result["market_leadership_claim_allowed"] is False


def test_missing_attestation_keeps_evidence_incomplete():
    row = _pair(1, 100, 90)
    row["attested"] = False
    result = evaluate_shadow_backtest(pairs=[row], minimum_pairs=1)
    assert result["evidence_complete"] is False
    assert "pair_attestation_missing:index:0" in result["blockers"]
