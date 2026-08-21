from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "eay_release_candidate.json"
MODULE_CATALOG_PATH = ROOT / "config" / "module_catalog.json"
QUALITY_CONTRACT_PATH = ROOT / "config" / "product_quality_contract.json"
WORKFLOW_ROOT = ROOT / ".github" / "workflows"

SHA40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_PHASES = [
    "software_integration",
    "staging_infrastructure",
    "device_and_data_pilot",
    "production_acceptance",
]

REQUIRED_MODULE_GATES = {
    "workforce": {"corporate_oidc", "field_pilot", "real_hr_roster_leave_attendance_inputs"},
    "inventory": {"managed_android_signing", "mdm_distribution", "corporate_oidc", "physical_zebra_devices"},
    "planogram": {"approved_sku_physical_dimensions", "real_store_dna", "measured_fixture_geometry_and_capacity"},
    "dockos": {"corporate_oidc", "bigquery_po_identity", "real_smtp", "supplier_dc_pilot"},
    "budget": {"real_finance_inputs_and_mapping", "finance_owner_uat", "production_accounting_reconciliation"},
    "academy": {"object_storage_and_cdn", "corporate_oidc_claim_mapping", "real_1200_concurrent_video_delivery_test"},
    "jarvis": {
        "authorized_read_only_production_bigquery_identity",
        "live_information_schema_observation",
        "authoritative_tenant_discriminator_confirmation",
        "controlled_live_cross_tenant_zero_leak_proof",
    },
}

REQUIRED_SHARED_DEPENDENCIES = {
    "platform_core",
    "security",
    "eay_ai_core",
    "repository_intelligence",
    "insight_kpi",
    "product_quality",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_workflows_exist(component: str, workflows: list[str]) -> None:
    if not workflows:
        raise AssertionError(f"{component}: required_workflows must not be empty")
    for workflow in workflows:
        if Path(workflow).name != workflow or not workflow.endswith((".yml", ".yaml")):
            raise AssertionError(f"{component}: invalid workflow name: {workflow}")
        path = WORKFLOW_ROOT / workflow
        if not path.is_file() or path.stat().st_size == 0:
            raise AssertionError(f"{component}: required workflow missing: {workflow}")


def assert_fail_closed_component(component: str, record: dict) -> None:
    if record.get("software_test_ready") is not True:
        raise AssertionError(f"{component}: RC0 requires software_test_ready=true")
    gates = record.get("external_acceptance_gates")
    if not isinstance(gates, list) or not gates or len(gates) != len(set(gates)):
        raise AssertionError(f"{component}: external acceptance gates must be a non-empty unique list")
    if record.get("production_ready") is not False:
        raise AssertionError(f"{component}: open external gates require production_ready=false")
    assert_workflows_exist(component, record.get("required_workflows", []))


def main() -> None:
    manifest = load_json(MANIFEST_PATH)
    catalog = load_json(MODULE_CATALOG_PATH)
    quality = load_json(QUALITY_CONTRACT_PATH)

    if manifest.get("schema_version") != 1:
        raise AssertionError("unsupported EAY RC manifest schema")
    if manifest.get("release_candidate_id") != "EAY-RC0-INTERNAL-TEST":
        raise AssertionError("unexpected release candidate identity")
    if manifest.get("source_branch") != "release/platform-convergence-v0.1":
        raise AssertionError("RC source branch must be the cumulative convergence branch")
    if manifest.get("release_state") != "software_integration_test_ready":
        raise AssertionError("RC0 must remain in software-integration test-ready state")

    evidence = manifest.get("evidence_policy", {})
    if evidence.get("runtime_github_sha_is_authoritative") is not True:
        raise AssertionError("runtime exact SHA must remain authoritative")
    if evidence.get("all_required_ci_must_pass_on_exact_head") is not True:
        raise AssertionError("exact-head cumulative CI must remain mandatory")
    if evidence.get("repository_ready_is_not_production_ready") is not True:
        raise AssertionError("repository readiness must not imply production readiness")
    if evidence.get("external_evidence_may_not_be_replaced_by_synthetic_evidence") is not True:
        raise AssertionError("external evidence must not be replaceable by synthetic evidence")
    baseline = evidence.get("last_verified_parent_sha_before_manifest", "")
    if not SHA40.fullmatch(baseline):
        raise AssertionError("last verified parent evidence SHA must be an exact 40-character SHA")

    controls = manifest.get("release_controls", {})
    expected_false = ["main_merge_permitted", "production_activation_permitted", "production_ready"]
    for key in expected_false:
        if controls.get(key) is not False:
            raise AssertionError(f"release control must remain false: {key}")
    if controls.get("unresolved_external_gate_blocks_production") is not True:
        raise AssertionError("unresolved external gates must block production")
    if controls.get("frozen_security_and_ai_foundations_may_not_be_mutated_for_rc") is not True:
        raise AssertionError("frozen foundations must remain protected")

    phases = manifest.get("testing_phases", [])
    if [phase.get("key") for phase in phases] != REQUIRED_PHASES:
        raise AssertionError("testing phases must preserve the canonical acceptance order")
    if phases[0].get("state") != "ready":
        raise AssertionError("software integration phase must be ready")
    for phase in phases[1:]:
        if phase.get("state") != "blocked_external":
            raise AssertionError(f"{phase.get('key')}: must remain blocked on external acceptance")

    catalog_modules = {item["key"] for item in catalog.get("commercial_modules", [])}
    quality_modules = set(quality.get("commercial_module_coverage", []))
    rc_modules = set(manifest.get("commercial_modules", {}))
    if rc_modules != catalog_modules or rc_modules != quality_modules:
        raise AssertionError(
            f"commercial module coverage drift: catalog={sorted(catalog_modules)} quality={sorted(quality_modules)} rc={sorted(rc_modules)}"
        )

    for module, required_gates in REQUIRED_MODULE_GATES.items():
        record = manifest["commercial_modules"][module]
        assert_fail_closed_component(module, record)
        actual_gates = set(record["external_acceptance_gates"])
        missing = required_gates - actual_gates
        if missing:
            raise AssertionError(f"{module}: mandatory real-world gates missing: {sorted(missing)}")

    workforce_notes = manifest["commercial_modules"]["workforce"].get("notes", "").lower()
    if "hiring" not in workforce_notes or "employee master" not in workforce_notes:
        raise AssertionError("Hiring must remain bound to the canonical Workforce Employee Master lifecycle")

    planogram_notes = manifest["commercial_modules"]["planogram"].get("notes", "").lower()
    if "does not mean physical master data is complete" not in planogram_notes:
        raise AssertionError("Planogram green CI must not be misrepresented as physical-truth completion")

    jarvis_notes = manifest["commercial_modules"]["jarvis"].get("notes", "").lower()
    if "synthetic proof cannot promote" not in jarvis_notes:
        raise AssertionError("Jarvis live-evidence boundary must remain explicit")

    shared = manifest.get("shared_release_dependencies", {})
    if set(shared) != REQUIRED_SHARED_DEPENDENCIES:
        raise AssertionError("shared release dependency coverage drift")
    for component, record in shared.items():
        assert_fail_closed_component(component, record)

    reserved = manifest.get("reserved_not_in_current_rc", {})
    if set(reserved) != {"expense_management"}:
        raise AssertionError("Expense Management must be the only explicitly reserved next-phase module in RC0")
    expense = reserved["expense_management"]
    if expense.get("state") != "deferred_until_current_p0_acceptance" or expense.get("separate_module") is not True:
        raise AssertionError("Expense Management must remain deferred and separate")
    if expense.get("silent_auto_post_forbidden") is not True:
        raise AssertionError("Expense OCR may never silently post financial state")
    required_expense_flow = {"receipt_capture", "ocr", "field_extraction", "confidence_review", "approval", "budget_link", "accounting_export", "audit"}
    if not required_expense_flow.issubset(set(expense.get("planned_flow", []))):
        raise AssertionError("Expense Management reserved flow lost required controls")

    print("EAY_RC0_TEST_READINESS=PASS")
    print("SOFTWARE_INTEGRATION_TEST_READY=true")
    print("PRODUCTION_READY=false")
    print(f"COMMERCIAL_MODULES={','.join(sorted(rc_modules))}")
    print(f"BASELINE_EVIDENCE_SHA={baseline}")


if __name__ == "__main__":
    main()
