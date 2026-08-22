from __future__ import annotations

import physical_economics as economics


def v5_result(*, baseline_avg: float = 25.0, selected_avg: float = 18.0) -> dict:
    return {
        "physical_layout_optimizer": {
            "allowed": True,
            "selected_layout_label": "swap::A::1<->A::2",
            "candidates": [
                {
                    "label": "baseline",
                    "tour_average_m": baseline_avg,
                    "tour_p95_m": 35.0,
                    "tour_coverage_pct": 100.0,
                },
                {
                    "label": "swap::A::1<->A::2",
                    "tour_average_m": selected_avg,
                    "tour_p95_m": 24.0,
                    "tour_coverage_pct": 100.0,
                },
            ],
        }
    }


def rng(low, base, high, ref, *, attested=True):
    return {
        "low": low,
        "base": base,
        "high": high,
        "source_ref": ref,
        "attested": attested,
    }


def assumptions() -> dict:
    return {
        "currency": "EUR",
        "orders_per_day": rng(800, 1000, 1200, "bq://orders-30d"),
        "operating_days_per_year": rng(350, 360, 365, "ops://calendar-2026"),
        "effective_seconds_per_meter": rng(0.8, 1.0, 1.2, "pilot://route-time"),
        "loaded_labor_cost_per_hour": rng(8, 10, 12, "finance://labor-2026"),
        "capex_items": [
            {
                "label": "fixture move",
                "amount": 2500,
                "currency": "EUR",
                "source_ref": "quote://vendor-123",
                "attested": True,
            }
        ],
    }


def test_economics_requires_every_assumption_to_be_attested_and_sourced() -> None:
    raw = assumptions()
    raw["effective_seconds_per_meter"]["attested"] = False
    raw["capex_items"][0]["source_ref"] = ""

    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=v5_result(),
        assumptions=raw,
    )

    assert result["available"] is False
    assert "effective_seconds_per_meter_attestation_missing" in result["blockers"]
    assert "capex_source_ref_missing:index:0" in result["blockers"]
    assert result["finance_approved"] is False
    assert result["investment_decision_allowed"] is False


def test_currency_mismatch_fails_closed() -> None:
    raw = assumptions()
    raw["capex_items"][0]["currency"] = "TRY"

    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=v5_result(),
        assumptions=raw,
    )

    assert result["available"] is False
    assert "capex_currency_mismatch:index:0" in result["blockers"]


def test_incomplete_route_coverage_cannot_be_monetized() -> None:
    raw_result = v5_result()
    raw_result["physical_layout_optimizer"]["candidates"][1]["tour_coverage_pct"] = 95

    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=raw_result,
        assumptions=assumptions(),
    )

    assert result["available"] is False
    assert result["blockers"] == ["selected_route_coverage_incomplete"]


def test_attested_scenario_produces_downside_base_upside_without_approval() -> None:
    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=v5_result(),
        assumptions=assumptions(),
    )

    assert result["available"] is True
    assert result["route"]["average_saving_m"] == 7.0
    assert [row["scenario"] for row in result["scenarios"]] == [
        "downside",
        "base",
        "upside",
    ]
    base = result["scenarios"][1]
    assert base["route_seconds_saved_per_order"] == 7.0
    assert base["daily_hours_saved"] == 1.944
    assert base["daily_labor_value"] == 19.44
    assert base["annual_labor_value"] == 7000.0
    assert base["capex"] == 2500.0
    assert base["first_year_net_value"] == 4500.0
    assert base["payback_operating_days"] == 128.6
    assert base["first_year_roi_pct"] == 180.0
    assert result["all_inputs_attested"] is True
    assert result["production_evidence"] is False
    assert result["finance_approved"] is False
    assert result["investment_decision_allowed"] is False
    assert result["auto_execute_allowed"] is False


def test_no_route_gain_never_invents_savings() -> None:
    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=v5_result(baseline_avg=18, selected_avg=20),
        assumptions=assumptions(),
    )

    assert result["available"] is True
    assert result["route"]["average_saving_m"] == -2.0
    assert all(row["annual_labor_value"] == 0 for row in result["scenarios"])
    assert all(row["economically_positive_first_year"] is False for row in result["scenarios"])


def test_range_order_is_validated() -> None:
    raw = assumptions()
    raw["orders_per_day"] = rng(1200, 1000, 800, "bq://orders")

    result = economics.evaluate_physical_layout_economics(
        physical_layout_result=v5_result(),
        assumptions=raw,
    )

    assert result["available"] is False
    assert "orders_per_day_range_order_invalid" in result["blockers"]
