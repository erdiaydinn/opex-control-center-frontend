from __future__ import annotations

import ast
from pathlib import Path

EXPLANATION = (
    Path(__file__).parents[1]
    / "app"
    / "modules"
    / "inventory"
    / "explanation.py"
)
ROUTER = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "router.py"


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_explanation_context_is_read_only_and_tenant_warehouse_scoped() -> None:
    source = EXPLANATION.read_text(encoding="utf-8")
    rendered = ast.unparse(_function(EXPLANATION, "explanation_context"))
    assert "inventory_current_tenant" in rendered
    assert "principal.tenant_id" in rendered
    assert "principal.warehouse_scope" in rendered
    assert "inventory_documents" in rendered
    assert "inventory_events" in rendered
    assert "inventory_revisions" in rendered
    assert "inventory_audit" in rendered
    assert "inventory_mission_lease_closures" in rendered
    assert '"read_only": True' in source
    assert "INSERT INTO" not in source
    assert "UPDATE inventory_" not in source
    assert "DELETE FROM inventory_" not in source


def test_explanation_context_excludes_prompt_injection_and_sensitive_raw_fields() -> None:
    source = EXPLANATION.read_text(encoding="utf-8")
    assert '"free_text_excluded": True' in source
    assert '"recovery_reasons_free_text_excluded": True' in source
    assert "SELECT e.event_type,e.location_id" in source
    assert '"events": authoritative_events' in source
    assert '"authoritative_events": authoritative_events' in source
    assert '"abandoned_attempt_events_excluded_from_stock_truth": True' in source
    assert '"superseded_attempt_evidence_preserved": True' in source
    assert '"lease_closure_lifecycle"' in source
    assert "SELECT c.state,count(*)::integer AS closure_count" in source
    assert "a.state='COMPLETED'" in source
    assert "SELECT revision,state,snapshot_hash,created_at" in source
    assert "SELECT action,previous_hash,hash,occurred_at" in source
    assert "actor_subject" not in source
    assert "employee_id" not in source
    assert "device_id" not in source
    assert "SELECT action,record" not in source
    assert "SELECT revision,state,reason" not in source
    assert "c.reason" not in source
    assert "close_reason" not in source


def test_explanation_context_has_deterministic_integrity_fingerprint() -> None:
    source = EXPLANATION.read_text(encoding="utf-8")
    rendered = ast.unparse(_function(EXPLANATION, "_fingerprint"))
    assert "sort_keys=True" in rendered
    assert "sha256" in rendered
    explanation = ast.unparse(_function(EXPLANATION, "explanation_context"))
    assert "context_fingerprint" in explanation
    assert "inventory_completed_attempt_truth" in explanation
    assert "attempt_lifecycle" in explanation
    assert "lease_closure_lifecycle" in explanation
    assert '"schema_version": 3' in source


def test_production_route_requires_supervisor_authority_and_never_accepts_client_scope() -> None:
    rendered = ast.unparse(_function(ROUTER, "production_explanation_context"))
    node = _function(ROUTER, "production_explanation_context")
    parameters = {argument.arg for argument in node.args.args}
    assert "require_verified_identity(request, 'approveInventory')" in rendered
    assert "production_mode()" in rendered
    assert "explanation_context" in rendered
    assert "production_principal" in rendered
    assert "tenant_id" not in parameters
    assert "warehouse_id" not in parameters
    assert "role" not in parameters
    assert "permissions" not in parameters
