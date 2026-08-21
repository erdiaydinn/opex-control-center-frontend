import fs from "node:fs";
import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const quality = JSON.parse(fs.readFileSync("config/product_quality_contract.json", "utf8"));
const prefs = fs.readFileSync("src/platform/preferences/PlatformPreferencesContext.jsx", "utf8");
const css = fs.readFileSync("src/platform/preferences/platform-preferences.css", "utf8");
const main = fs.readFileSync("src/main.jsx", "utf8");

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const expectedStates = ["loading", "error", "empty", "offline", "retry"];
const expectedSurfaces = [
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
];

requireCondition(quality.contract_version >= 3, "global product-quality contract must remain v3+");
requireCondition(
  JSON.stringify(quality.global_acceptance_targets.supported_locales) === JSON.stringify(expectedLocales),
  "global locale order/coverage drifted",
);
requireCondition(
  JSON.stringify(quality.global_acceptance_targets.required_user_states) === JSON.stringify(expectedStates),
  "global user-state contract drifted",
);
requireCondition(
  JSON.stringify(quality.product_surface_standard.required_surface_keys) === JSON.stringify(expectedSurfaces),
  "product-surface standard drifted",
);

const runtimeLocales = SUPPORTED_LOCALES.map((item) => item.code);
requireCondition(JSON.stringify(runtimeLocales) === JSON.stringify(expectedLocales), "runtime locale set drifted from quality contract");
const arabic = SUPPORTED_LOCALES.find((item) => item.code === "ar");
requireCondition(arabic?.dir === "rtl", "Arabic runtime locale must be RTL");
for (const locale of SUPPORTED_LOCALES.filter((item) => item.code !== "ar")) {
  requireCondition(locale.dir === "ltr", `non-Arabic locale direction drifted: ${locale.code}`);
}

requireCondition(prefs.includes("root.lang = locale"), "runtime locale must update document language");
requireCondition(prefs.includes("root.dir = localeMeta.dir"), "runtime locale must update document direction");
requireCondition(prefs.includes("root.dataset.eayTextScale"), "runtime text-scaling preference binding is missing");
requireCondition(prefs.includes("root.dataset.eayReduceMotion"), "runtime reduced-motion preference binding is missing");
requireCondition(prefs.includes("root.dataset.eayLargeTargets"), "runtime large-target preference binding is missing");
requireCondition(prefs.includes("root.dataset.eayFocusMode"), "runtime focus-mode preference binding is missing");

for (const rule of [
  "prefers-reduced-motion",
  "forced-colors",
  ":focus-visible",
  'html[data-eay-large-targets="true"]',
  "min-height: 48px",
  '[dir="rtl"]',
]) {
  requireCondition(css.includes(rule), `global accessibility CSS rule missing: ${rule}`);
}

requireCondition(main.includes("PlatformPreferencesProvider"), "global platform preferences provider is missing");
requireCondition(main.includes("<SkipToMainContent />"), "global skip navigation is missing");
requireCondition(main.includes("<NetworkStatusAnnouncer />"), "global offline status boundary is missing");
requireCondition(main.includes('id="eay-main-content"'), "canonical main landmark is missing");

const statesBySurface = quality.surface_ux_state_coverage || {};
requireCondition(JSON.stringify(Object.keys(statesBySurface)) === JSON.stringify(expectedSurfaces), "surface-state keys drifted");
for (const surface of expectedSurfaces) {
  requireCondition(
    JSON.stringify(statesBySurface[surface]) === JSON.stringify(expectedStates),
    `${surface} must explicitly cover loading/error/empty/offline/retry`,
  );
  const definition = quality.surfaces?.[surface];
  requireCondition(definition?.owner, `${surface} owner is missing`);
  requireCondition(Array.isArray(definition?.priority_flows) && definition.priority_flows.length > 0, `${surface} priority flows are missing`);
  requireCondition(Array.isArray(definition?.field_evidence) && definition.field_evidence.length > 0, `${surface} external acceptance evidence is missing`);
}

const standard = quality.product_surface_standard;
for (const key of [
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
]) {
  requireCondition(standard[key] === true, `global product-surface requirement regressed: ${key}`);
}

requireCondition(
  quality.release_policy.repository_quality_evidence_is_not_field_or_production_acceptance === true,
  "repository product-quality evidence must never become production evidence",
);
requireCondition(
  quality.release_policy.product_surface_may_not_claim_release_eligible_with_untracked_ui_states === true,
  "untracked UX states may not become release eligible",
);

console.log("EAY global product quality v3: PASS");
