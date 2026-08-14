"""Fail closed when EAY product-quality coverage drifts from the module catalog."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "config" / "module_catalog.json").read_text(encoding="utf-8"))
QUALITY = json.loads((ROOT / "config" / "product_quality_contract.json").read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


catalog_modules = {module["key"]: module for module in CATALOG["commercial_modules"]}
coverage = set(QUALITY["commercial_module_coverage"])
require(coverage == set(catalog_modules), f"quality coverage drift: catalog={sorted(catalog_modules)} quality={sorted(coverage)}")

required_dimensions = {
    "functional_correctness",
    "security_and_scope",
    "data_integrity",
    "task_usability",
    "visual_quality",
    "accessibility",
    "performance",
    "resilience_and_offline",
    "localization",
    "audit_and_explainability",
}
require(required_dimensions == set(QUALITY["global_dimensions"]), "global quality dimensions are incomplete")

targets = QUALITY["global_acceptance_targets"]
require(targets["web_accessibility"] == "WCAG_2_2_AA", "web accessibility target must stay WCAG 2.2 AA")
require(set(targets["supported_locales"]) == {"tr", "en", "de", "ar"}, "TR/EN/DE/AR coverage is mandatory")
require(targets["rtl_required_for_ar"] is True, "Arabic RTL is mandatory")
require(targets["mobile_terminal_min_touch_target_dp"] >= 48, "mobile/terminal touch targets may not shrink below 48dp")
require(targets["critical_task_success_rate_percent"] >= 98, "critical task success target regressed")
require(targets["usability_sus_target"] >= 85, "market-leading usability target regressed")
require(targets["crash_free_sessions_percent"] >= 99.8, "crash-free target regressed")
require(targets["terminal_local_scan_feedback_p95_ms"] <= 150, "terminal feedback target regressed")
require(targets["offline_mutations_require_idempotent_replay"] is True, "offline mutation replay must be idempotent")

surfaces = QUALITY["surfaces"]
for key, module in catalog_modules.items():
    require(key in surfaces, f"missing product-quality surface for {key}")
    surface = surfaces[key]
    require(surface.get("priority_flows"), f"{key} has no priority flows")
    require(set(surface.get("channels", [])) == set(module["channels"]), f"{key} channel coverage drift")
    require(surface.get("field_evidence"), f"{key} must name external/field evidence")

require(surfaces["hiring"]["owner"] == "workforce", "Hiring must remain in the Workforce lifecycle")
require(surfaces["hiring"]["separate_employee_master_forbidden"] is True, "competing Employee Master is forbidden")
require(surfaces["inventory"]["terminal_is_native_product_surface"] is True, "Inventory terminal must remain a native product surface")
require(surfaces["insight_kpi"]["duplicate_metric_truth_forbidden"] is True, "Insight/KPI may not duplicate metric truth")

expense = QUALITY["next_phase_reserved"]["expense_management"]
require(expense["separate_module"] is True, "Expense Management must remain a separate module")
require(expense["silent_auto_post_forbidden"] is True, "receipt OCR may never silently post financial entries")
require({"receipt_capture", "ocr", "field_extraction", "confidence_review", "approval", "budget_link", "accounting_export", "audit"}.issubset(expense["planned_flow"]), "Expense Management planned flow is incomplete")

policy = QUALITY["release_policy"]
require(policy["repository_ready_is_not_production_ready"] is True, "repository evidence must not be promoted to production evidence")
require(policy["field_evidence_required_for_market_leading_claim"] is True, "market-leading claim requires field evidence")
require(policy["frontend_may_not_duplicate_authoritative_backend_or_kpi_truth"] is True, "frontend truth duplication is forbidden")

print("EAY product quality contract: PASS")
