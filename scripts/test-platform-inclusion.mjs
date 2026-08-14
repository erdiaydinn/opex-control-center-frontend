import fs from "node:fs";
import { messageCoverage, SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { intelligenceMessageCoverage } from "../src/platform/i18n/intelligenceMessages.js";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const main = fs.readFileSync("src/main.jsx", "utf8");
const prefs = fs.readFileSync("src/platform/preferences/PlatformPreferencesContext.jsx", "utf8");
const control = fs.readFileSync("src/platform/preferences/AccessibilityControl.jsx", "utf8");
const css = fs.readFileSync("src/platform/preferences/platform-preferences.css", "utf8");
const quality = JSON.parse(fs.readFileSync("config/product_quality_contract.json", "utf8"));

requireCondition(main.includes("PlatformPreferencesProvider"), "global platform preferences provider is missing");
requireCondition(main.includes("AccessibilityControl"), "global accessibility control is missing");
requireCondition(main.indexOf("AccessibilityControl") < main.indexOf("<div id=\"eay-main-content\""), "accessibility control must be globally reachable before app content");
requireCondition(control.includes("role=\"dialog\""), "accessibility panel must expose dialog semantics");
requireCondition(control.includes("aria-expanded"), "accessibility trigger must expose expanded state");
requireCondition(control.includes("eay-skip-link"), "skip-to-content control is required");
requireCondition(css.includes("prefers-reduced-motion"), "OS reduced-motion preference must be respected");
requireCondition(css.includes("forced-colors"), "forced-colors support must be preserved");
requireCondition(css.includes(":focus-visible"), "visible keyboard focus is required");
requireCondition(prefs.includes("Intl.NumberFormat"), "locale-aware number formatting is required");
requireCondition(prefs.includes("Intl.DateTimeFormat"), "locale-aware date formatting is required");

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
requireCondition(
  JSON.stringify(SUPPORTED_LOCALES.map((item) => item.code)) === JSON.stringify(expectedLocales),
  "runtime locale set/order drifted"
);
for (const locale of expectedLocales) {
  requireCondition(quality.global_acceptance_targets.supported_locales.includes(locale), `quality contract locale missing: ${locale}`);
}

const coverage = messageCoverage();
for (const locale of expectedLocales) {
  requireCondition((coverage.missing[locale] || []).length === 0, `missing translations for ${locale}: ${(coverage.missing[locale] || []).join(", ")}`);
  requireCondition((coverage.extra[locale] || []).length === 0, `translation key drift for ${locale}: ${(coverage.extra[locale] || []).join(", ")}`);
}

const intelligenceCoverage = intelligenceMessageCoverage(expectedLocales);
for (const locale of expectedLocales) {
  requireCondition((intelligenceCoverage.missing[locale] || []).length === 0, `missing intelligence translations for ${locale}: ${(intelligenceCoverage.missing[locale] || []).join(", ")}`);
  requireCondition((intelligenceCoverage.extra[locale] || []).length === 0, `intelligence translation key drift for ${locale}: ${(intelligenceCoverage.extra[locale] || []).join(", ")}`);
}

requireCondition(quality.global_acceptance_targets.rtl_locales.includes("ar"), "Arabic RTL must remain mandatory");
requireCondition(quality.release_policy.accessibility_preferences_must_not_require_disability_or_health_diagnosis === true, "accessibility must not require diagnosis data");
requireCondition(quality.surfaces.jarvis.security_guardian_scope === "platform_admin_only", "Security Guardian scope regressed");

const academyMedia = new Set(quality.surfaces.academy.media_accessibility_required || []);
for (const requirement of ["captions", "transcript", "audio_description_capability", "descriptive_transcript_capability", "keyboard_accessible_player"]) {
  requireCondition(academyMedia.has(requirement), `Academy media accessibility missing: ${requirement}`);
}

console.log("EAY platform inclusion + ten-locale message coverage: PASS");
