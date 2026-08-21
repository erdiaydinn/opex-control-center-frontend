import fs from "node:fs";
import { messageCoverage, SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { intelligenceMessageCoverage } from "../src/platform/i18n/intelligenceMessages.js";
import { academyPlayerMessageCoverage } from "../src/platform/i18n/academyPlayerMessages.js";
import { academyAuthoringMessageCoverage } from "../src/platform/i18n/academyAuthoringMessages.js";
import { academyQuizAuthoringMessageCoverage } from "../src/platform/i18n/academyQuizAuthoringMessages.js";
import { academyContentMessageCoverage } from "../src/platform/i18n/academyContentMessages.js";
import { planogramMessageCoverage } from "../src/platform/i18n/planogramMessages.js";

function requireCondition(condition, message) { if (!condition) throw new Error(message); }
const main=fs.readFileSync("src/main.jsx","utf8");
const prefs=fs.readFileSync("src/platform/preferences/PlatformPreferencesContext.jsx","utf8");
const control=fs.readFileSync("src/platform/preferences/AccessibilityControl.jsx","utf8");
const skip=fs.readFileSync("src/platform/accessibility/SkipToMainContent.jsx","utf8");
const network=fs.readFileSync("src/platform/accessibility/NetworkStatusAnnouncer.jsx","utf8");
const css=fs.readFileSync("src/platform/preferences/platform-preferences.css","utf8");
const planogram=fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx","utf8");
const academyWorkspace=fs.readFileSync("src/modules/academy/AcademyWorkspace.jsx","utf8");
const academyAuthoring=fs.readFileSync("src/modules/academy/AcademyPathAuthoring.jsx","utf8");
const academyQuizAuthoring=fs.readFileSync("src/modules/academy/AcademyQuizAuthoring.jsx","utf8");
const academyPathCss=fs.readFileSync("src/modules/academy/academy-path-authoring.css","utf8");
const academyPlayerCss=fs.readFileSync("src/modules/academy/academy-player.css","utf8");
const academyQualityCss=fs.readFileSync("src/modules/academy/academy-quality.css","utf8");
const quality=JSON.parse(fs.readFileSync("config/product_quality_contract.json","utf8"));
requireCondition(main.includes("PlatformPreferencesProvider"),"global platform preferences provider is missing");
requireCondition(main.includes("AccessibilityControl"),"global accessibility control is missing");
requireCondition(main.includes("<SkipToMainContent />"),"shell-owned skip navigation is missing");
requireCondition(main.includes("<NetworkStatusAnnouncer />"),"global offline state boundary is missing");
requireCondition(main.indexOf("<AccessibilityControl />")<main.indexOf("<main id=\"eay-main-content\""),"accessibility control must be globally reachable before app content");
requireCondition(main.includes('<main id="eay-main-content" tabIndex="-1">'),"canonical main landmark must remain keyboard focusable");
requireCondition(control.includes("role=\"dialog\""),"accessibility panel must expose dialog semantics");
requireCondition(control.includes("aria-expanded"),"accessibility trigger must expose expanded state");
requireCondition(skip.includes("eay-skip-link")&&skip.includes('href="#eay-main-content"'),"shell-owned skip-to-content control is required");
requireCondition(!control.includes("eay-skip-link"),"accessibility control must not duplicate the shell skip link");
requireCondition(network.includes('window.addEventListener("offline"'),"global shell must observe browser offline state");
requireCondition(network.includes('window.addEventListener("online"'),"global shell must recover when connectivity returns");
requireCondition(network.includes('role="status"')&&network.includes('aria-live="polite"'),"offline state must be announced accessibly");
requireCondition(network.includes('t("offline")'),"offline state must use the localized platform message contract");
requireCondition(css.includes("prefers-reduced-motion"),"OS reduced-motion preference must be respected");
requireCondition(css.includes("forced-colors"),"forced-colors support must be preserved");
requireCondition(css.includes(":focus-visible"),"visible keyboard focus is required");
requireCondition(prefs.includes("Intl.NumberFormat"),"locale-aware number formatting is required");
requireCondition(prefs.includes("Intl.DateTimeFormat"),"locale-aware date formatting is required");
const expectedLocales=["tr","en","de","ar","fr","es","it","nl","pl","pt-BR"];
requireCondition(JSON.stringify(SUPPORTED_LOCALES.map(item=>item.code))===JSON.stringify(expectedLocales),"runtime locale set/order drifted");
for(const locale of expectedLocales){requireCondition(quality.global_acceptance_targets.supported_locales.includes(locale),`quality contract locale missing: ${locale}`);}
for(const [label,coverage] of [["platform",messageCoverage()],["intelligence",intelligenceMessageCoverage(expectedLocales)],["academy player",academyPlayerMessageCoverage(expectedLocales)],["academy authoring",academyAuthoringMessageCoverage(expectedLocales)],["academy quiz authoring",academyQuizAuthoringMessageCoverage(expectedLocales)],["academy content",academyContentMessageCoverage(expectedLocales)],["planogram",planogramMessageCoverage(expectedLocales)]]){for(const locale of expectedLocales){requireCondition((coverage.missing[locale]||[]).length===0,`missing ${label} translations for ${locale}: ${(coverage.missing[locale]||[]).join(", ")}`);requireCondition((coverage.extra[locale]||[]).length===0,`${label} translation key drift for ${locale}: ${(coverage.extra[locale]||[]).join(", ")}`);}}
requireCondition(academyWorkspace.includes("translateAcademyContent(locale, item.content_type)"),"Academy content-type labels must remain localized");
requireCondition(!academyWorkspace.includes("<span>{item.content_type}</span>"),"Academy catalog must not expose raw content-type enums");
requireCondition(!academyWorkspace.includes("{answer.mode}"),"Academy tutor must not expose raw answer-mode enums");
requireCondition(academyAuthoring.includes('canAction("academy", "managePaths")'),"Academy path authoring must remain permission-bound");
requireCondition(academyAuthoring.includes("workspace?.authoring?.published_versions"),"Academy path content choices must remain server-authoritative");
requireCondition(academyAuthoring.includes("workspace?.authoring?.roles"),"Academy audience role choices must remain server-authoritative");
requireCondition(academyAuthoring.includes('/v1/academy/admin/paths'),"Academy path authoring must persist through the governed Core API");
requireCondition(academyQuizAuthoring.includes('canAction("academy", "manageQuizzes")'),"Academy quiz authoring must remain permission-bound");
requireCondition(academyQuizAuthoring.includes("workspace?.authoring?.published_versions"),"Academy quiz content choices must remain server-authoritative");
requireCondition(academyQuizAuthoring.includes("workspace?.authoring?.quizzes"),"Academy quiz state must remain server-authoritative");
requireCondition(academyQuizAuthoring.includes('/v1/academy/admin/quizzes'),"Academy quiz authoring must persist through the governed Core API");
requireCondition(academyPathCss.startsWith('@import "./academy-quality.css";'),"Academy workspace must load shared touch-target quality rules");
requireCondition(academyPlayerCss.startsWith('@import "./academy-quality.css";'),"Academy player must load shared touch-target quality rules");
for(const rule of [".eay-academy-page .eay-academy-back{width:48px;height:48px}",".eay-academy-page .eay-academy-nav nav button{min-height:48px}",".eay-academy-page .eay-academy-refresh,.eay-academy-page .eay-academy-primary{min-height:48px}",".eay-academy-page .eay-academy-search{height:48px}",".academy-player-page .academy-player-outline button,.academy-player-page .academy-player-checkpoint,.academy-player-page .academy-player-quiz label{min-height:48px}"]){requireCondition(academyQualityCss.includes(rule),`Academy 48px interaction rule missing: ${rule}`);}
requireCondition(quality.global_acceptance_targets.rtl_locales.includes("ar"),"Arabic RTL must remain mandatory");
requireCondition(quality.release_policy.accessibility_preferences_must_not_require_disability_or_health_diagnosis===true,"accessibility must not require diagnosis data");
requireCondition(quality.surfaces.jarvis.security_guardian_scope==="platform_admin_only","Security Guardian scope regressed");
for(const forbidden of ["VITE_PLANAI_LEGACY_URL","<iframe","postMessage(","access_token"]){requireCondition(!planogram.includes(forbidden),`Planogram legacy bridge regressed: ${forbidden}`);}
requireCondition(planogram.includes("/v1/planogram/readiness"),"Planogram must use Core-authoritative readiness route");
const academyMedia=new Set(quality.surfaces.academy.media_accessibility_required||[]);
for(const requirement of ["captions","transcript","audio_description_capability","descriptive_transcript_capability","keyboard_accessible_player"]){requireCondition(academyMedia.has(requirement),`Academy media accessibility missing: ${requirement}`);}
console.log("EAY platform inclusion + ten-locale message coverage: PASS");
