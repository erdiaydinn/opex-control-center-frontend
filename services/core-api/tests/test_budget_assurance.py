from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.budget import assurance


@pytest.mark.asyncio
async def test_control_tower_is_server_authoritative_and_evidence_bound(monkeypatch):
    tenant_id = uuid4()
    rows = [
        {
            "budget_line_id": uuid4(),
            "cost_center": "OPS-IST",
            "category": "Maintenance",
            "supplier_id": None,
            "supplier_name": "Supplier A",
            "store_code": "S001",
            "budget_base_amount": "1000",
            "actual_base_amount": "700",
            "committed_base_amount": "250",
            "forecast_base_amount": "1150",
            "variance_base_amount": "-150",
        },
        {
            "budget_line_id": uuid4(),
            "cost_center": "OPS-ANK",
            "category": "Energy",
            "supplier_id": None,
            "supplier_name": "Supplier B",
            "store_code": "S002",
            "budget_base_amount": "2000",
            "actual_base_amount": "800",
            "committed_base_amount": "300",
            "forecast_base_amount": "1800",
            "variance_base_amount": "200",
        },
    ]

    async def fake_variance_summary(_uow):
        return {"tenant_id": str(tenant_id), "count": len(rows), "items": rows}

    monkeypatch.setattr(assurance, "variance_summary", fake_variance_summary)
    uow = SimpleNamespace(tenant_id=tenant_id)
    result = await assurance.build_financial_control_tower(uow)

    assert result["summary"] == {
        "budget": "3000.00",
        "actual": "1500.00",
        "commitment": "550.00",
        "forecast": "2950.00",
        "remaining_headroom": "950.00",
        "forecast_variance": "50.00",
        "utilization_pct": "68.33",
        "forecast_utilization_pct": "98.33",
    }
    assert result["truth_boundary"]["browser_formula_authority"] is False
    assert result["truth_boundary"]["ai_financial_mutation_authority"] is False
    assert result["truth_boundary"]["human_review_required_for_findings"] is True
    assert len(result["evidence_fingerprint"]) == 64
    assert result["findings"][0]["severity"] == "critical"
    assert result["findings"][0]["requires_human_review"] is True
    assert result["findings"][0]["automatic_financial_mutation_permitted"] is False


@pytest.mark.asyncio
async def test_assurance_binds_financial_event_tip(monkeypatch):
    tenant_id = uuid4()

    async def fake_tower(_uow):
        return {"findings": [], "evidence_fingerprint": "a" * 64}

    async def fake_events(_uow, _limit):
        return {"count": 2, "items": [{"event_hash": "b" * 64}, {"event_hash": "c" * 64}]}

    monkeypatch.setattr(assurance, "build_financial_control_tower", fake_tower)
    monkeypatch.setattr(assurance, "financial_events", fake_events)
    result = await assurance.build_financial_assurance(SimpleNamespace(tenant_id=tenant_id), 50)

    assert result["financial_event_tip"] == "b" * 64
    assert result["source_fingerprint"] == "a" * 64
    assert result["control_model"]["closure_requires_verification"] is True
    assert result["control_model"]["ai_disagreement_is_review_signal_not_sanction"] is True
    assert len(result["assurance_fingerprint"]) == 64
