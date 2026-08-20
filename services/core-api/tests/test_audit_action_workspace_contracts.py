from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_action_reads_are_tenant_and_resource_scope_bound() -> None:
    repository = (ROOT / "app/modules/audit/repository.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/modules/audit/routes.py").read_text(encoding="utf-8")

    assert "async def list_actions(" in repository
    assert "aa.tenant_id = CAST(:tenant_id AS UUID)" in repository
    assert ":unrestricted" in repository
    assert "ar.location_id = ANY" in repository
    assert "COALESCE(fl.region, '') = ANY" in repository
    assert 'require_audit_scope(principal, "feature:audit:actions")' in routes
    assert "await _require_action_scope(principal, scope, action_id)" in routes


def test_action_origin_is_resolved_from_governed_template_version() -> None:
    repository = (ROOT / "app/modules/audit/repository.py").read_text(encoding="utf-8")

    assert "JOIN audit_program_versions apv" in repository
    assert "JOIN field_templates ft" in repository
    assert "jsonb_array_elements" in repository
    assert "field_definition->>'key' = aa.item_key" in repository
    assert "origin_field" in repository


def test_action_updates_preserve_optimistic_version_and_receipt_authority() -> None:
    repository = (ROOT / "app/modules/audit/repository.py").read_text(encoding="utf-8")
    routes = (ROOT / "app/modules/audit/routes.py").read_text(encoding="utf-8")

    assert "row.version != payload.expected_version" in repository
    assert "audit action version conflict" in repository
    assert "version = version + 1" in repository
    assert 'if payload.status == "ai_verified"' in routes
    assert '"action:audit:verifyAction"' in routes
