import ast
import json
from pathlib import Path


GATES = Path("config/eay_category_leadership_gates.json")
REQUIRED_MODULES = {
    "platform_core",
    "security",
    "eay_ai_core",
    "jarvis",
    "repository_intelligence",
    "kpi_insight_analytics",
    "planogram",
    "workforce",
    "hiring_recruitment",
    "inventory",
    "dockos",
    "budget_intelligence",
    "academy",
    "field_intelligence",
    "audit",
    "shared_services",
}
REQUIRED_FIELDS = {
    "priority",
    "competitor_gap",
    "rule",
    "acceptance",
    "external_dependency",
    "evidence_type",
}


def load_gates():
    return json.loads(GATES.read_text(encoding="utf-8"))


def test_repository_green_and_synthetic_proof_are_not_production_truth():
    gates = load_gates()
    boundary = gates["truth_boundary"]
    assert boundary["repository_green_is_production_ready"] is False
    assert boundary["synthetic_evidence_is_field_evidence"] is False
    assert boundary["production_activation_requires_external_evidence"] is True


def test_every_commercial_and_shared_module_has_category_leadership_gates():
    gates = load_gates()
    modules = set(gates["modules"])
    assert REQUIRED_MODULES <= modules
    assert not (modules - REQUIRED_MODULES), (
        f"unreviewed modules in gate manifest: {sorted(modules - REQUIRED_MODULES)}"
    )

    for module, rules in gates["modules"].items():
        assert rules, f"{module} has no category leadership rules"
        for rule in rules:
            assert REQUIRED_FIELDS <= set(rule), f"{module} rule missing required fields"
            assert rule["priority"] in {"P0", "P1", "P2"}
            assert rule["competitor_gap"].strip()
            assert rule["rule"].strip()
            assert rule["acceptance"].strip()
            assert rule["external_dependency"].strip()
            assert rule["evidence_type"].strip()


def test_p0_rules_require_external_or_field_evidence_not_ci_only_claims():
    gates = load_gates()
    for module, rules in gates["modules"].items():
        for rule in rules:
            if rule["priority"] != "P0":
                continue
            text = " ".join(str(value).lower() for value in rule.values())
            assert (
                "external" in rule["evidence_type"]
                or "field" in rule["evidence_type"]
                or "production" in rule["evidence_type"]
            ), module
            assert "ci only" not in text
            assert "green ci = production" not in text


def test_field_intelligence_core_surface_is_live_through_existing_core_router():
    text = Path("services/core-api/app/intelligence_routes.py").read_text(encoding="utf-8")
    assert '@router.get("/field/bootstrap")' in text
    assert '@router.post("/field/missions"' in text
    assert 'require_field_permission(principal, "action:field_intelligence:createMission")' in text
    assert "create_mission(str(principal.tenant_id), principal.subject, payload, scope)" in text


def _literal_assignment_value(source: str, variable_name: str):
    tree = ast.parse(source)
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == variable_name:
            matches.append(ast.literal_eval(node.value))
    assert len(matches) == 1, f"expected one literal assignment for {variable_name}"
    return matches[0]


def test_field_permissions_and_core_migration_are_explicitly_authoritative():
    catalog = Path("services/core-api/app/core/permission_catalog.py").read_text(encoding="utf-8")
    migration = Path("services/core-api/alembic/versions/0019_field_intelligence_foundation.py").read_text(encoding="utf-8")

    assert '"field_intelligence"' in catalog
    assert 'action_permission("field_intelligence", "createMission")' in catalog
    assert 'action_permission("field_intelligence", "viewEvidence")' in catalog
    assert '"module:field_intelligence:view"' in migration
    assert '"action:field_intelligence:createMission"' in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert _literal_assignment_value(migration, "all_scope") == '\'{"type":"all"}\'::jsonb'
