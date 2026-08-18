from decimal import Decimal
from pathlib import Path

from app.modules.budget.intelligence import (
    BudgetTruth,
    build_budget_recommendation,
)


def test_ai_forecast_is_provenance_bound_recommendation_only():
    truth = BudgetTruth(
        Decimal("100"),
        Decimal("80"),
        Decimal("10"),
        Decimal("95"),
        Decimal("110"),
        Decimal("90"),
        Decimal("5"),
        {"orders": Decimal("15"), "price": Decimal("5")},
        ("scenario:v3", "actual:ledger"),
    )
    recommendation = build_budget_recommendation(truth)
    assert recommendation.recommendation_only
    assert recommendation.suggested_forecast_base_amount == Decimal("110")
    assert len(recommendation.input_fingerprint) == 64
    assert recommendation.root_causes[0][0] == "orders"


def test_ai_module_has_no_accounting_truth_mutation():
    source = (
        Path(__file__).resolve().parents[1]
        / "app/modules/budget/intelligence.py"
    ).read_text().lower()
    assert "update actual" not in source
    assert "update commitment" not in source
    assert "delete from" not in source


def test_finance_controls_require_four_eyes_hash_and_external_uat():
    source = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0039_budget_finance_controls.py"
    ).read_text()
    for token in (
        "independent export decision required",
        "output_sha256",
        "budget_import_version",
        "budget_finance_uat_attestation",
        "environment NOT IN ('ci','repository','synthetic')",
    ):
        assert token in source
