from __future__ import annotations

import physical_layout_candidate_economics as candidate_economics

FINGERPRINT = "a" * 64


def summary(label: str, average: float, p95: float) -> dict:
    return {
        "label": label,
        "layout_fingerprint": FINGERPRINT if label != "baseline" else "b" * 64,
        "tour_average_m": average,
        "tour_p95_m": p95,
        "tour_coverage_pct": 100.0,
        "production_authority": False,
    }


def assumptions() -> dict:
    return {
        "currency": "EUR",
        "orders_per_day": {"low": 100, "base": 100, "high": 100, "source_ref": "ops://orders", "attested": True},
        "operating_days_per_year": {"low": 300, "base": 300, "high": 300, "source_ref": "ops://days", "attested": True},
        "effective_seconds_per_meter": {"low": 1, "base": 1, "high": 1, "source_ref": "study://walk", "attested": True},
        "loaded_labor_cost_per_hour": {"low": 10, "base": 10, "high": 10, "source_ref": "finance://labor", "attested": True},
        "capex_items": [{"label": "move", "amount": 100, "currency": "EUR", "source_ref": "quote://move", "attested": True}],
    }


def test_candidate_economics_uses_replayed_baseline_and_candidate(monkeypatch) -> None:
    baseline = summary("baseline", 40, 45)
    candidate = summary("swap::A::1<->A::2", 25, 30)
    monkeypatch.setattr(
        candidate_economics,
        "preview_physical_layout_candidate",
        lambda **kwargs: {
            "available": True,
            "layout_fingerprint": FINGERPRINT,
            "baseline_candidate_summary": baseline,
            "candidate_summary": candidate,
        },
    )

    result = candidate_economics.evaluate_physical_layout_candidate_economics(
        products=[{"sku": "SKU"}],
        layout={},
        store_dna={},
        orders=[{"skus": ["SKU"]}],
        layout_fingerprint=FINGERPRINT,
        assumptions=assumptions(),
    )

    assert result["available"] is True
    assert result["layout_fingerprint"] == FINGERPRINT
    assert result["candidate_label"] == "swap::A::1<->A::2"
    assert result["economics"]["route"]["average_saving_m"] == 15
    assert result["economics"]["scenarios"][1]["route_saving_m_per_order"] == 15
    assert result["production_evidence"] is False
    assert result["finance_approved"] is False
    assert result["investment_decision_allowed"] is False
    assert result["realized_savings_proven"] is False


def test_candidate_economics_fails_closed_when_replay_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        candidate_economics,
        "preview_physical_layout_candidate",
        lambda **kwargs: {"available": False, "reason": "fingerprint_missing"},
    )
    result = candidate_economics.evaluate_physical_layout_candidate_economics(
        products=[],
        layout={},
        store_dna={},
        orders=[],
        layout_fingerprint=FINGERPRINT,
        assumptions=assumptions(),
    )
    assert result["available"] is False
    assert result["reason"] == "candidate_replay_unavailable"
    assert result["production_evidence"] is False
    assert result["finance_approved"] is False
    assert result["realized_savings_proven"] is False
