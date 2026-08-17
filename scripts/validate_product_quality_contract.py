"""Fail closed when EAY product-quality coverage drifts from the module catalog or product surfaces."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "config" / "module_catalog.json").read_text(encoding="utf-8"))
QUALITY = json.loads((ROOT / "config" / "product_quality_contract.json").read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require(QUALITY.get("contract_version", 0) >= 3, "global product-quality contract must remain v3+")

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
required_locales = {"tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"}
require(required_locales == set(targets["supported_locales"]), "global language coverage regressed or drifted")
require(set(targets["rtl_locales"]) == {"ar"}, "Arabic must remain the canonical RTL locale")
require(targets["rtl_requires_document_direction"] is True, "RTL must drive document direction")
require(targets["localized_system_states"] is True, "system states must remain localized")
require(targets["text_scaling_without_loss_percent"] >= 200, "text scaling acceptance may not regress below 200 percent")
require(targets["mobile_terminal_min_touch_target_dp"] >= 48, "mobile/terminal touch targets may not shrink below 48dp")
require(targets["critical_task_success_rate_percent"] >= 98, "critical task success target regressed")
require(targets["usability_sus_target"] >= 85, "market-leading usability target regressed")
require(targets["crash_free_sessions_percent"] >= 99.8, "crash-free target regressed")
require(targets["terminal_local_scan_feedback_p95_ms"] <= 150, "terminal feedback target regressed")
require(targets["offline_mutations_require_idempotent_replay"] is True, "offline mutation replay must be idempotent")

required_user_states = {"loading", "error", "empty", "offline", "retry"}
require(set(targets["required_user_states"]) == required_user_states, "global loading/error/empty/offline/retry contract regressed")

required_accessibility = {
    "screen_reader_semantics",
    "keyboard_only_operation",
    "visible_focus",
    "forced_colors_support",
    "reduced_motion",
    "no_color_only_meaning",
    "text_scaling_without_loss",
    "large_touch_targets",
    "visual_equivalent_for_audio_alerts",
    "captions_by_default_when_available",
    "transcript_support",
    "audio_description_support",
    "descriptive_transcript_support",
    "non_drag_alternative_for_drag_interactions",
    "plain_language_and_focus_mode_support",
}
require(required_accessibility.issubset(set(targets["accessibility_enhancements_beyond_minimum"])), "inclusive accessibility enhancements regressed")

inclusive = QUALITY["inclusive_experience"]
for domain in ("visual", "hearing", "motor", "cognitive_and_learning", "motion_and_photosensitivity"):
    require(inclusive.get(domain), f"inclusive experience missing {domain} coverage")

surface_standard = QUALITY["product_surface_standard"]
required_product_surfaces = {
    "control_center",
    "workforce",
    "hiring",
    "inventory",
    "planogram",
    "dockos",
    "budget",
    "academy",
    "jarvis",
    "insight_kpi",
    "field_intelligence",
}
require(set(surface_standard["required_surface_keys"]) == required_product_surfaces, "required product-surface coverage drifted")
for key in (
    "inherits_global_locale_set",
    "arabic_rtl_required",
    "wcag_2_2_aa_required",
    "keyboard_only_required",
    "visible_focus_required",
    "screen_reader_semantics_required",
    "reduced_motion_required",
    "text_scaling_required",
    "state_copy_must_be_localized",
    "offline_behavior_must_be_explicit",
):
    require(surface_standard.get(key) is True, f"global product-surface standard regressed: {key}")

state_coverage = QUALITY["surface_ux_state_coverage"]
require(set(state_coverage) == required_product_surfaces, "surface UX-state coverage keys drifted")
for surface_key, states in state_coverage.items():
    require(set(states) == required_user_states, f"{surface_key} must explicitly cover loading/error/empty/offline/retry")

surfaces = QUALITY["surfaces"]
require(required_product_surfaces.issubset(set(surfaces)), "one or more mandatory product surfaces are missing")
for surface_key in sorted(required_product_surfaces):
    surface = surfaces[surface_key]
    require(surface.get("owner"), f"{surface_key} has no accountable owner")
    require(surface.get("channels"), f"{surface_key} has no channels")
    require(surface.get("priority_flows"), f"{surface_key} has no priority flows")
    require(surface.get("field_evidence"), f"{surface_key} must name external/field acceptance evidence")

for key, module in catalog_modules.items():
    require(key in surfaces, f"missing product-quality surface for {key}")
    surface = surfaces[key]
    require(set(surface.get("channels", [])) == set(module["channels"]), f"{key} channel coverage drift")

require(surfaces["hiring"]["owner"] == "workforce", "Hiring must remain in the Workforce lifecycle")
require(surfaces["hiring"]["separate_employee_master_forbidden"] is True, "competing Employee Master is forbidden")
require(surfaces["inventory"]["terminal_is_native_product_surface"] is True, "Inventory terminal must remain a native product surface")
require(surfaces["insight_kpi"]["duplicate_metric_truth_forbidden"] is True, "Insight/KPI may not duplicate metric truth")
require(surfaces["jarvis"]["security_guardian_scope"] == "platform_admin_only", "Security Guardian must remain platform-admin only")
academy_media = set(surfaces["academy"].get("media_accessibility_required", []))
require({"captions", "transcript", "audio_description_capability", "descriptive_transcript_capability", "keyboard_accessible_player"}.issubset(academy_media), "Academy media accessibility contract regressed")

field = surfaces["field_intelligence"]
require(field["owner"] == "field_intelligence", "Field Intelligence must retain an accountable product owner")
require({"mission_builder", "targeting", "capture", "evidence", "review", "rework", "reminder", "escalation", "verification", "results"}.issubset(set(field["priority_flows"])), "Field Intelligence quality flows are incomplete")

expense = QUALITY["next_phase_reserved"]["expense_management"]
require(expense["separate_module"] is True, "Expense Management must remain a separate module")
require(expense["silent_auto_post_forbidden"] is True, "receipt OCR may never silently post financial entries")
require({"receipt_capture", "ocr", "field_extraction", "confidence_review", "approval", "budget_link", "accounting_export", "audit"}.issubset(expense["planned_flow"]), "Expense Management planned flow is incomplete")

policy = QUALITY["release_policy"]
require(policy["repository_ready_is_not_production_ready"] is True, "repository evidence must not be promoted to production evidence")
require(policy["field_evidence_required_for_market_leading_claim"] is True, "market-leading claim requires field evidence")
require(policy["frontend_may_not_duplicate_authoritative_backend_or_kpi_truth"] is True, "frontend truth duplication is forbidden")
require(policy["accessibility_is_a_platform_requirement_not_an_optional_theme"] is True, "accessibility must remain a platform requirement")
require(policy["accessibility_preferences_must_not_require_disability_or_health_diagnosis"] is True, "accessibility preferences may not require sensitive diagnosis data")
require(policy["global_product_quality_gate_required_for_all_product_surfaces"] is True, "all product surfaces must remain under the global quality gate")
require(policy["product_surface_may_not_claim_release_eligible_with_untracked_ui_states"] is True, "untracked UX states may not be release eligible")
require(policy["repository_quality_evidence_is_not_field_or_production_acceptance"] is True, "repository quality evidence must not become production evidence")

print("EAY global product quality contract: PASS")
