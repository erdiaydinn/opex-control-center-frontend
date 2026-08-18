from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.grounded_evidence_planner import (
    EVIDENCE_PLAN_CONTRACT,
    MAX_EVIDENCE_QUERIES,
    build_evidence_plan,
    execute_evidence_plan,
    select_evidence,
)


def request(message: str, layers=None):
    return SimpleNamespace(
        message=message,
        layers=list(layers or ["legal", "company", "standard", "operational"]),
    )


def evidence(evidence_id: str, layer: str, score: float):
    return SimpleNamespace(id=evidence_id, layer=layer, score=score)


class FakeStore:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query
        self.calls = []

    def search(self, query, as_of, layers, limit):
        self.calls.append((query, tuple(layers), limit, as_of))
        return list(self.rows_by_query.get((query, tuple(layers)), []))[:limit]


def test_operational_question_does_not_activate_unneeded_legal_company_layers() -> None:
    plan = build_evidence_plan(
        request("NSFR neden yükseldi? Kök neden ve öneri nedir?"),
        8,
    )

    assert plan.contract == EVIDENCE_PLAN_CONTRACT
    assert plan.inferred_required_layers == ["operational"]
    assert plan.active_layers == ["operational"]
    assert plan.legal_temporal_resolution_required is False
    assert plan.steps
    assert all(step.layers == ["operational"] for step in plan.steps)
    assert len(plan.steps) <= MAX_EVIDENCE_QUERIES
    assert any(step.purpose == "clause" for step in plan.steps)
    assert any("NSFR" in step.query for step in plan.steps)


def test_legal_company_comparison_plans_both_authority_layers() -> None:
    plan = build_evidence_plan(
        request("Şirket politikamız mevzuattan daha katı mı?"),
        8,
    )

    assert plan.inferred_required_layers == ["legal", "company"]
    assert plan.active_layers == ["legal", "company"]
    assert plan.legal_temporal_resolution_required is True
    assert plan.steps[0].layers == ["legal", "company"]
    assert any(step.layers == ["legal"] for step in plan.steps)
    assert any(step.layers == ["company"] for step in plan.steps)


def test_ambiguous_question_preserves_allowed_layer_window() -> None:
    plan = build_evidence_plan(
        request("Bunun hakkında ne biliyoruz?", ["legal", "standard"]),
        5,
    )

    assert plan.inferred_required_layers == []
    assert plan.active_layers == ["legal", "standard"]
    assert plan.legal_temporal_resolution_required is True
    assert len(plan.steps) == 1


def test_execution_deduplicates_and_keeps_best_observed_score() -> None:
    plan = build_evidence_plan(
        request("NSFR neden yükseldi?", ["operational"]),
        4,
    )
    first = plan.steps[0]
    store = FakeStore(
        {
            (first.query, tuple(first.layers)): [
                evidence("ops-1", "operational", 0.4),
                evidence("ops-2", "operational", 0.6),
            ]
        }
    )
    # A second planned query can rediscover ops-1 at a better score.
    if len(plan.steps) > 1:
        second = plan.steps[1]
        store.rows_by_query[(second.query, tuple(second.layers))] = [
            evidence("ops-1", "operational", 0.9)
        ]

    candidates = execute_evidence_plan(plan, store=store, as_of=date(2026, 8, 17))
    assert plan.candidate_count == 2
    assert [row.id for row in candidates] == ["ops-1", "ops-2"]
    assert candidates[0].score == 0.9 if len(plan.steps) > 1 else 0.4


def test_selection_reserves_coverage_for_each_required_layer() -> None:
    plan = build_evidence_plan(
        request("Şirket politikamız mevzuattan daha katı mı?"),
        8,
    )
    candidates = [
        evidence("law-1", "legal", 0.95),
        evidence("law-2", "legal", 0.94),
        evidence("company-1", "company", 0.40),
        evidence("law-3", "legal", 0.93),
    ]

    selected = select_evidence(plan, candidates, limit=2)
    assert {row.layer for row in selected} == {"legal", "company"}
    assert plan.selected_count == 2
    assert plan.selected_layer_counts == {"company": 1, "legal": 1}


def test_query_count_and_per_query_limits_remain_bounded() -> None:
    plan = build_evidence_plan(
        request(
            "NSFR ve PFR neden yükseldi; refund ile karşılaştır ve risk önerisi ver",
            ["operational"],
        ),
        20,
    )
    assert len(plan.steps) <= MAX_EVIDENCE_QUERIES
    assert all(1 <= step.limit <= 32 for step in plan.steps)
