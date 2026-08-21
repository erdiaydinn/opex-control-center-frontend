"""Read-only explainable ranking for employee open-shift discovery.

Hard eligibility remains owned by ``flexibility.evaluate_open_shift``. This layer
can only enrich and order options that already passed that authority.
"""

from __future__ import annotations

from copy import deepcopy

from . import flexibility, persistence, service
from .assignment_ranking import evaluate_assignment_ranking


def _hydrate_canonical_schedule() -> None:
    """Refresh the schedule snapshot before computing advisory ranking signals."""
    if not persistence.ENABLED:
        return
    service._hydrate_snapshot(persistence.load_snapshot(service._snapshot_kinds()))


def _ranking_for_offer(offer: dict, person_id: str, preference_match: bool | None) -> dict:
    person_shifts = [
        row
        for row in service.list_shifts(str(person_id))
        if row.get("status") != "İptal"
    ]
    minimum_rest = service._rule_value("betweenShifts", str(offer["date"]), 660)
    return evaluate_assignment_ranking(
        offer=offer,
        person_id=str(person_id),
        person_shifts=person_shifts,
        cohort_shifts=list(service._SHIFTS),
        preference_match=preference_match,
        minimum_rest_minutes=minimum_rest,
    ).as_record()


def list_ranked_open_shifts_for_person(person_id: str) -> list[dict]:
    _hydrate_canonical_schedule()
    availability = flexibility._load_availability()
    rows: list[dict] = []
    for offer in flexibility._load_open_shifts():
        if offer.get("status") != "OPEN":
            continue
        if int(offer.get("claimed_count", 0)) >= int(offer.get("capacity", 1)):
            continue
        evaluation = flexibility.evaluate_open_shift(offer, person_id, availability)
        if not evaluation["eligible"]:
            continue
        ranking = _ranking_for_offer(
            offer,
            str(person_id),
            evaluation.get("preference_match"),
        )
        rows.append(
            {
                **{key: value for key, value in offer.items() if key != "claims"},
                "eligibility": {**evaluation, "assignment_ranking": ranking},
                "remaining_capacity": (
                    int(offer.get("capacity", 1))
                    - int(offer.get("claimed_count", 0))
                ),
            }
        )
    return deepcopy(
        sorted(
            rows,
            key=lambda row: (
                -int(row["eligibility"]["assignment_ranking"]["fairness_score"]),
                int(row["eligibility"]["assignment_ranking"]["fatigue_risk_score"]),
                -int(row["eligibility"].get("score", 0)),
                str(row["date"]),
                str(row["start"]),
            ),
        )
    )
