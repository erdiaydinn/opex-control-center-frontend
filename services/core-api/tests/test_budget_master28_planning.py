import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.budget.planning import create_forecast
from app.modules.budget.schemas import ForecastCreate


class _MissingScopeResult:
    def first(self):
        return None


class _ScopeRejectingSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return _MissingScopeResult()


def test_forecast_fails_closed_before_insert_when_scope_does_not_match_line() -> None:
    tenant_id = uuid4()
    line_id = uuid4()
    period_id = uuid4()
    center_id = uuid4()
    session = _ScopeRejectingSession()
    uow = SimpleNamespace(session=session, tenant_id=tenant_id, actor="forecast-user")
    body = ForecastCreate(
        budget_line_id=line_id,
        fiscal_period_id=period_id,
        cost_center_id=center_id,
        forecast_base_amount="125.50",
        as_of=date(2026, 8, 18),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_forecast(uow, body))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Forecast scope does not match the authoritative Budget Line"
    assert len(session.calls) == 1
    statement, params = session.calls[0]
    assert "FROM budget_line" in statement
    assert "fiscal_period_id=:period" in statement
    assert "cost_center_id=:center" in statement
    assert params == {
        "tenant": tenant_id,
        "line": line_id,
        "period": period_id,
        "center": center_id,
    }


def test_planning_snapshot_provenance_never_claims_legacy_activation_truth() -> None:
    migration = Path(
        "services/core-api/alembic/versions/0037_budget_planning_authority.py"
    ).read_text(encoding="utf-8")

    assert 'ACTIVATION_TRIGGER = "ACTIVATION_TRIGGER"' in migration
    assert (
        'LEGACY_RECONSTRUCTION = "LEGACY_MIGRATION_RECONSTRUCTION"'
        in migration
    )
    assert "planning_snapshot_at = CURRENT_TIMESTAMP" in migration
    assert "planning_snapshot_provenance = '{LEGACY_RECONSTRUCTION}'" in migration
    assert "NEW.planning_snapshot_at := NEW.activated_at" in migration
    assert (
        "NEW.planning_snapshot_provenance := '{ACTIVATION_TRIGGER}'"
        in migration
    )
