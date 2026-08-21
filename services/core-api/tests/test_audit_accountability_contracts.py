from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas import AuditRunStart

ROOT = Path(__file__).resolve().parents[1]


def test_run_payload_cannot_spoof_manager_subject() -> None:
    with pytest.raises(ValidationError):
        AuditRunStart(
            program_key="market.audit",
            program_version=1,
            location_id="store-1",
            manager_subject="spoofed-manager",
        )

    payload = AuditRunStart(
        program_key="market.audit",
        program_version=1,
        location_id="store-1",
        manager_subject=None,
    )
    assert payload.manager_subject is None


def test_accountability_resolver_requires_active_audit_manager_membership() -> None:
    source = (ROOT / "app/modules/audit/accountability.py").read_text(encoding="utf-8")
    assert "m.status = 'active'" in source
    assert "r.key = 'audit_manager'" in source
    assert "r.is_system IS TRUE" in source
    assert "audit_location_manager_assignments" in source


def test_run_authority_snapshots_only_server_resolved_manager() -> None:
    source = (ROOT / "app/modules/audit/run_authority.py").read_text(encoding="utf-8")
    assert "resolve_location_manager_subject" in source
    assert '"manager_subject": manager_subject' in source
    assert "payload.manager_subject" not in source


def test_routes_use_authoritative_run_start_and_governed_assignment_endpoint() -> None:
    routes = (ROOT / "app/modules/audit/routes.py").read_text(encoding="utf-8")
    assert "start_authoritative_run" in routes
    assert "return await start_authoritative_run(" in routes
    assert '"action:audit:manageLocations"' in routes
    assert '"/locations/{location_id}/manager-assignment"' in routes


def test_location_manager_assignment_schema_uses_membership_uuid() -> None:
    from app.modules.audit.schemas import AuditLocationManagerAssignmentCreate

    membership_id = uuid4()
    payload = AuditLocationManagerAssignmentCreate(
        manager_membership_id=membership_id,
        source_ref="setup-workbook:locations:v1",
    )
    assert payload.manager_membership_id == membership_id
    assert payload.expected_version is None


def test_accountability_migration_is_tenant_safe_and_delete_restricted() -> None:
    migration = (
        ROOT / "alembic/versions/0049_audit_location_accountability.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "0049_audit_location_accountability"' in migration
    assert 'down_revision: str = "0048_audit_assurance_routing"' in migration
    assert "audit_location_manager_assignments_tenant_isolation" in migration
    assert "fk_audit_location_manager_membership" in migration
    assert "REVOKE DELETE ON TABLE audit_location_manager_assignments" in migration
