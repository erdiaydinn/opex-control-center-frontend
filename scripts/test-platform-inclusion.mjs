import fs from "node:fs";
import { messageCoverage, SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { intelligenceMessageCoverage } from "../src/platform/i18n/intelligenceMessages.js";
import { academyPlayerMessageCoverage } from "../src/platform/i18n/academyPlayerMessages.js";
import { academyAuthoringMessageCoverage } from "../src/platform/i18n/academyAuthoringMessages.js";
import { planogramMessageCoverage } from "../src/platform/i18n/planogramMessages.js";

function requireCondition(condition, message) { if (!condition) throw new Error(message); }
const main=fs.readFileSync("src/main.jsx","utf8");
const prefs=fs.readFileSync("src/platform/preferences/PlatformPreferencesContext.jsx","utf8");
const control=fs.readFileSync("src/platform/preferences/AccessibilityControl.jsx","utf8");
const css=fs.readFileSync("src/platform/preferences/platform-preferences.css","utf8");
const planogram=fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx","utf8");
const academyAuthoring=fs.readFileSync("src/modules/academy/AcademyPathAuthoring.jsx","utf8");
const quality=JSON.parse(fs.readFileSync("config/product_quality_contract.json","utf8"));
requireCondition(main.includes("PlatformPreferencesProvider"),"global platform preferences provider is missing");
requireCondition(main.includes("AccessibilityControl"),"global accessibility control is missing");
requireCondition(main.indexOf("AccessibilityControl")<main.indexOf("<div id=\"eay-main-content\""),"accessibility control must be globally reachable before app content");
requireCondition(control.includes("role=\"dialog\""),"accessibility panel must expose dialog semantics");
requireCondition(control.includes("aria-expanded"),"accessibility trigger must expose expanded state");
requireCondition(control.includes("eay-skip-link"),"skip-to-content control is required");
requireCondition(css.includes("prefers-reduced-motion"),"OS reduced-motion preference must be respected");
requireCondition(css.includes("forced-colors"),"forced-colors support must be preserved");
requireCondition(css.includes(":focus-visible"),"visible keyboard focus is required");
requireCondition(prefs.includes("Intl.NumberFormat"),"locale-aware number formatting is required");
requireCondition(prefs.includes("Intl.DateTimeFormat"),"locale-aware date formatting is required");
const expectedLocales=["tr","en","de","ar","fr","es","it","nl","pl","pt-BR"];
requireCondition(JSON.stringify(SUPPORTED_LOCALES.map(item=>item.code))===JSON.stringify(expectedLocales),"runtime locale set/order drifted");
for(const locale of expectedLocales){requireCondition(quality.global_acceptance_targets.supported_locales.includes(locale),`quality contract locale missing: ${locale}`);}
for(const [label,coverage] of [["platform",messageCoverage()],["intelligence",intelligenceMessageCoverage(expectedLocales)],["academy player",academyPlayerMessageCoverage(expectedLocales)],["academy authoring",academyAuthoringMessageCoverage(expectedLocales)],["planogram",planogramMessageCoverage(expectedLocales)]]){for(const locale of expectedLocales){requireCondition((coverage.missing[locale]||[]).length===0,`missing ${label} translations for ${locale}: ${(coverage.missing[locale]||[]).join(", ")}`);requireCondition((coverage.extra[locale]||[]).length===0,`${label} translation key drift for ${locale}: ${(coverage.extra[locale]||[]).join(", ")}`);}}
requireCondition(academyAuthoring.includes('canAction("academy", "managePaths")'),"Academy path authoring must remain permission-bound");
requireCondition(academyAuthoring.includes("workspace?.authoring?.published_versions"),"Academy path content choices must remain server-authoritative");
requireCondition(academyAuthoring.includes("workspace?.authoring?.roles"),"Academy audience role choices must remain server-authoritative");
requireCondition(academyAuthoring.includes('/v1/academy/admin/paths'),"Academy path authoring must persist through the governed Core API");
requireCondition(quality.global_acceptance_targets.rtl_locales.includes("ar"),"Arabic RTL must remain mandatory");
requireCondition(quality.release_policy.accessibility_preferences_must_not_require_disability_or_health_diagnosis===true,"accessibility must not require diagnosis data");
requireCondition(quality.surfaces.jarvis.security_guardian_scope==="platform_admin_only","Security Guardian scope regressed");
for(const forbidden of ["VITE_PLANAI_LEGACY_URL","<iframe","postMessage(","access_token"]){requireCondition(!planogram.includes(forbidden),`Planogram legacy bridge regressed: ${forbidden}`);}
requireCondition(planogram.includes("/v1/planogram/readiness"),"Planogram must use Core-authoritative readiness route");
const academyMedia=new Set(quality.surfaces.academy.media_accessibility_required||[]);
for(const requirement of ["captions","transcript","audio_description_capability","descriptive_transcript_capability","keyboard_accessible_player"]){requireCondition(academyMedia.has(requirement),`Academy media accessibility missing: ${requirement}`);}
console.log("EAY platform inclusion + ten-locale message coverage: PASS");
