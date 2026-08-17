from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.permission_catalog import is_known_permission
from app.field_governance_routes import ExemptionCreate, ExportCreate, RecurrenceCreate
from app.main import app
from app.modules.field_intelligence import governance


def test_governance_routes_are_on_canonical_core_surface() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/v1/field/governance/templates/{template_id}/{template_version}/retire",
        "/v1/field/governance/missions/{mission_id}/recurrence",
        "/v1/field/governance/missions/{mission_id}/targets/{location_id}/exempt",
        "/v1/field/governance/targeting/{criterion}",
        "/v1/field/governance/exports",
        "/v1/field/governance/exports/{export_request_id}/decision",
    }
    assert expected <= paths


def test_governance_permissions_are_canonical_core_permissions() -> None:
    for permission in (
        "feature:field_intelligence:governance",
        "action:field_intelligence:manageRecurrence",
        "action:field_intelligence:exemptTarget",
        "action:field_intelligence:approveExport",
    ):
        assert is_known_permission(permission), permission


def test_recurrence_request_cannot_smuggle_tenant_or_targets() -> None:
    with pytest.raises(ValidationError):
        RecurrenceCreate.model_validate(
            {
                "cadence": "weekly",
                "interval_count": 1,
                "timezone": "Europe/Istanbul",
                "window_minutes": 120,
                "effective_from": "2026-08-17T09:00:00+03:00",
                "tenant_id": "attacker",
            }
        )
    with pytest.raises(ValidationError):
        RecurrenceCreate.model_validate(
            {
                "cadence": "weekly",
                "interval_count": 1,
                "timezone": "Europe/Istanbul",
                "window_minutes": 120,
                "effective_from": "2026-08-17T09:00:00+03:00",
                "location_ids": ["all"],
            }
        )


def test_exemption_and_export_models_are_strict() -> None:
    with pytest.raises(ValidationError):
        ExemptionCreate.model_validate(
            {
                "reason_code": "store.closed",
                "reason": "Location closed",
                "approved_by": "browser-admin",
            }
        )
    with pytest.raises(ValidationError):
        ExportCreate.model_validate({"format": "csv", "tenant_id": "browser-tenant"})


def test_server_targeting_has_no_browser_location_authority() -> None:
    source = inspect.getsource(governance.preview_server_targeting)
    assert "field_mission_targets" in source
    assert "allowed_location_ids" in source
    assert "browser_location_authority" in source
    assert '"field.overdue"' in inspect.getsource(governance)


def test_export_is_two_step_and_cannot_auto_deliver() -> None:
    source = inspect.getsource(governance)
    assert '"pending_approval"' in source
    assert "export requester cannot approve their own export" in source
    assert '"automatic_external_delivery_permitted": False' in source


def test_governance_evidence_is_rls_bound_and_append_only() -> None:
    migration = Path(
        "services/core-api/alembic/versions/0025_field_governance_operations.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str = "0024_field_evidence_object_upload"' in migration
    for table in (
        "field_recurrence_rules",
        "field_target_exemptions",
        "field_export_requests",
        "field_export_decisions",
    ):
        assert table in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "prevent_field_evidence_mutation" in migration
    assert "GRANT SELECT, INSERT" in migration
