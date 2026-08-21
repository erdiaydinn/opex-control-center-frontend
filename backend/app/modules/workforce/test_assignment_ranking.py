import unittest
from unittest.mock import patch

from . import flexibility_ranking
from .assignment_ranking import POLICY_REF, evaluate_assignment_ranking


class WorkforceAssignmentRankingTests(unittest.TestCase):
    def shift(self, shift_id, person_id, day, start="09:00", end="17:00", minutes=480):
        return {
            "id": shift_id,
            "person_id": person_id,
            "status": "Atandı",
            "date": day,
            "start": start,
            "end": end,
            "expected_minutes": minutes,
        }

    def offer(self):
        return {
            "id": "OPEN-1",
            "date": "2099-08-21",
            "start": "09:00",
            "end": "17:00",
            "expected_minutes": 480,
        }

    def test_low_relative_load_and_recovery_rank_above_fatigued_assignment(self):
        light = [self.shift("L1", "P1", "2099-08-20")]
        heavy = [
            self.shift("H1", "P2", "2099-08-16", minutes=600),
            self.shift("H2", "P2", "2099-08-17", minutes=600),
            self.shift("H3", "P2", "2099-08-18", minutes=600),
            self.shift("H4", "P2", "2099-08-19", minutes=600),
            self.shift("H5", "P2", "2099-08-20", start="11:00", end="22:00", minutes=600),
        ]
        cohort = light + heavy

        light_result = evaluate_assignment_ranking(
            offer=self.offer(),
            person_id="P1",
            person_shifts=light,
            cohort_shifts=cohort,
            preference_match=True,
            minimum_rest_minutes=660,
        )
        heavy_result = evaluate_assignment_ranking(
            offer=self.offer(),
            person_id="P2",
            person_shifts=heavy,
            cohort_shifts=cohort,
            preference_match=False,
            minimum_rest_minutes=660,
        )

        self.assertGreater(light_result.fairness_score, heavy_result.fairness_score)
        self.assertLess(light_result.fatigue_risk_score, heavy_result.fatigue_risk_score)
        self.assertIn("WORKLOAD_BELOW_COHORT", light_result.reason_codes)
        self.assertIn("WORKLOAD_VERY_HIGH_RELATIVE_TO_COHORT", heavy_result.reason_codes)
        self.assertIn("REST_BUFFER_TIGHT", heavy_result.reason_codes)
        self.assertIn("RECOVERY_STREAK_HIGH", heavy_result.reason_codes)

    def test_ranking_is_explicitly_soft_and_explainable(self):
        result = evaluate_assignment_ranking(
            offer=self.offer(),
            person_id="P1",
            person_shifts=[],
            cohort_shifts=[],
            preference_match=None,
            minimum_rest_minutes=660,
        )

        record = result.as_record()
        self.assertEqual(record["policy_ref"], POLICY_REF)
        self.assertTrue(record["soft_only"])
        self.assertEqual(record["fatigue_risk_band"], "LOW")
        self.assertIn("PREFERENCE_UNDECLARED", record["reason_codes"])
        self.assertIn("WORKLOAD_COHORT_BASELINE_UNAVAILABLE", record["reason_codes"])
        self.assertIn("REST_BUFFER_NO_ADJACENT_SHIFT", record["reason_codes"])

    def test_night_shift_duration_is_counted_without_cross_day_loss(self):
        night = [
            self.shift(
                "N1",
                "P1",
                "2099-08-20",
                start="22:00",
                end="06:00",
                minutes=420,
            )
        ]
        result = evaluate_assignment_ranking(
            offer={**self.offer(), "start": "18:00", "end": "23:00"},
            person_id="P1",
            person_shifts=night,
            cohort_shifts=night,
            preference_match=True,
            minimum_rest_minutes=660,
        )

        self.assertEqual(result.recent_minutes, 420)
        self.assertEqual(result.cohort_median_recent_minutes, 420)

    def test_open_shift_discovery_refreshes_canonical_schedule_when_persistence_enabled(self):
        snapshot = {"shifts": []}
        with (
            patch.object(flexibility_ranking.persistence, "ENABLED", True),
            patch.object(
                flexibility_ranking.persistence,
                "load_snapshot",
                return_value=snapshot,
            ) as load_snapshot,
            patch.object(
                flexibility_ranking.service,
                "_snapshot_kinds",
                return_value=["shifts"],
            ),
            patch.object(flexibility_ranking.service, "_hydrate_snapshot") as hydrate,
            patch.object(flexibility_ranking.flexibility, "_load_availability", return_value=[]),
            patch.object(flexibility_ranking.flexibility, "_load_open_shifts", return_value=[]),
        ):
            result = flexibility_ranking.list_ranked_open_shifts_for_person("P1")

        self.assertEqual(result, [])
        load_snapshot.assert_called_once_with(["shifts"])
        hydrate.assert_called_once_with(snapshot)


if __name__ == "__main__":
    unittest.main()
