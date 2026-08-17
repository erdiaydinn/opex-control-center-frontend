import unittest
from copy import deepcopy
from unittest.mock import patch

from physical_optimizer import OBJECTIVE_ORDER, objective_key, optimize_production_plan
from tests.test_physical_engine import dna, layout, product


def fake_result(*, hard=0, unplaced=None, optimizer_allowed=True):
    unplaced = list(unplaced or [])
    return {
        "production_ready": optimizer_allowed and hard == 0,
        "publishable": optimizer_allowed and hard == 0,
        "solver_optimizer_allowed": optimizer_allowed,
        "physical_truth": {"blockers": [] if optimizer_allowed else ["physical_truth_missing"]},
        "summary": {
            "total": len(unplaced),
            "placed": 0,
            "unplaced": len(unplaced),
        },
        "planogram": {"aisles": []} if optimizer_allowed else None,
        "unplaced": [{"sku": sku} for sku in unplaced],
        "diagnostics": {
            "summary": {"strict_rule_violation_count": hard},
        },
        "operational_physical_validation": {
            "violation_count": 0,
            "valid": hard == 0,
        },
    }


class PhysicalOptimizerTests(unittest.TestCase):
    def truth_products(self):
        return [
            product("SNACK", "Ambient Snack", category="Snacks"),
            product("WATER", "Water 6 x 1.5 L"),
        ]

    def test_physical_truth_block_prevents_candidate_search(self):
        blocked = optimize_production_plan(
            [product("MISSING", "No approved dimensions", dimensions=False)],
            layout(),
            dna(),
        )
        self.assertFalse(blocked["solver_optimizer_allowed"])
        self.assertFalse(blocked["optimizer"]["allowed"])
        self.assertTrue(blocked["optimizer"]["blocked_by_physical_truth"])
        self.assertEqual(blocked["optimizer"]["selected_strategy"], "baseline")
        self.assertEqual(blocked["optimizer"]["candidate_count"], 1)
        self.assertTrue(blocked["optimizer"]["baseline_preserved"])

    def test_optimizer_is_deterministic_for_same_truth_inputs(self):
        first = optimize_production_plan(self.truth_products(), layout(), dna())
        second = optimize_production_plan(self.truth_products(), layout(), dna())
        self.assertTrue(first["optimizer"]["allowed"])
        self.assertEqual(
            first["optimizer"]["selected_strategy"],
            second["optimizer"]["selected_strategy"],
        )
        self.assertEqual(
            first["optimizer"]["selected_objective"],
            second["optimizer"]["selected_objective"],
        )
        self.assertEqual(first["optimizer"]["fingerprint"], second["optimizer"]["fingerprint"])

    def test_selected_candidate_can_never_be_worse_than_baseline(self):
        result = optimize_production_plan(self.truth_products(), layout(), dna())
        baseline = result["optimizer"]["baseline_objective"]
        selected = result["optimizer"]["selected_objective"]
        self.assertLessEqual(objective_key(selected), objective_key(baseline))
        self.assertTrue(result["optimizer"]["baseline_preserved"])
        self.assertEqual(tuple(baseline), OBJECTIVE_ORDER)

    def test_strictly_better_candidate_is_selected(self):
        products = [
            {"sku": "HIGH", "sales_qty_7d": 100},
            {"sku": "LOW", "sales_qty_7d": 1},
        ]
        baseline = fake_result(unplaced=["HIGH"])
        better = fake_result(unplaced=[])

        def generator(*args, **kwargs):
            return deepcopy(baseline if kwargs.get("scoring_config") is None else better)

        with patch("physical_optimizer.generate_production_plan", side_effect=generator):
            result = optimize_production_plan(products, {}, {})

        self.assertEqual(result["optimizer"]["selected_strategy"], "route_focus")
        self.assertTrue(result["optimizer"]["improved"])
        self.assertEqual(result["optimizer"]["baseline_objective"]["weighted_unplaced_sales"], 100)
        self.assertEqual(result["optimizer"]["selected_objective"]["weighted_unplaced_sales"], 0)

    def test_hard_violation_cannot_be_traded_for_soft_gain(self):
        products = [{"sku": "HIGH", "sales_qty_7d": 100}]
        baseline = fake_result(hard=0, unplaced=["HIGH"])
        unsafe_soft_win = fake_result(hard=1, unplaced=[])

        def generator(*args, **kwargs):
            return deepcopy(
                baseline if kwargs.get("scoring_config") is None else unsafe_soft_win
            )

        with patch("physical_optimizer.generate_production_plan", side_effect=generator):
            result = optimize_production_plan(products, {}, {})

        self.assertEqual(result["optimizer"]["selected_strategy"], "baseline")
        self.assertFalse(result["optimizer"]["improved"])
        self.assertEqual(result["optimizer"]["selected_objective"]["hard_violation_count"], 0)

    def test_baseline_wins_exact_objective_ties(self):
        tied = fake_result(unplaced=[])
        with patch(
            "physical_optimizer.generate_production_plan",
            side_effect=lambda *args, **kwargs: deepcopy(tied),
        ):
            result = optimize_production_plan([{"sku": "A", "sales_qty_7d": 1}], {}, {})
        self.assertEqual(result["optimizer"]["selected_strategy"], "baseline")
        self.assertFalse(result["optimizer"]["improved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
