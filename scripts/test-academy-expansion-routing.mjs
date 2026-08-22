import fs from "node:fs";
import process from "node:process";

import { academyExpansionMessageCoverage } from "../src/platform/i18n/academyExpansionMessages.js";
import { academyGraphMessageCoverage } from "../src/platform/i18n/academyGraphMessages.js";
import { academyInteractionMessageCoverage } from "../src/platform/i18n/academyInteractionMessages.js";
import { academyLocalizationTelemetryMessageCoverage } from "../src/platform/i18n/academyLocalizationTelemetryMessages.js";
import { academySkillGapMessageCoverage } from "../src/platform/i18n/academySkillGapMessages.js";
import { academyStudioTermMessageCoverage } from "../src/platform/i18n/academyStudioTermMessages.js";

const UI_LOCALES = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const appPath = "src/App.jsx";
const workspacePath = "src/modules/academy/AcademyWorkspace.jsx";
const hubPath = "src/modules/academy/AcademyExpansionHub.jsx";
const achievementsPath = "src/modules/academy/AcademyAchievements.jsx";
const scenarioPath = "src/modules/academy/AcademyScenarioStudio.jsx";
const graphPath = "src/modules/academy/AcademyScenarioGraphCanvas.jsx";
const interactionPath = "src/modules/academy/AcademyInteractionTimelineStudio.jsx";
const localizationPath = "src/modules/academy/AcademyLocalizationGovernance.jsx";
const skillGapPath = "src/modules/academy/AcademySkillGap.jsx";
const app = fs.readFileSync(appPath, "utf8");
const workspace = fs.readFileSync(workspacePath, "utf8");
const hub = fs.readFileSync(hubPath, "utf8");
const achievements = fs.readFileSync(achievementsPath, "utf8");
const scenario = fs.readFileSync(scenarioPath, "utf8");
const graph = fs.readFileSync(graphPath, "utf8");
const interaction = fs.readFileSync(interactionPath, "utf8");
const localization = fs.readFileSync(localizationPath, "utf8");
const skillGap = fs.readFileSync(skillGapPath, "utf8");

const appRequirements = [
  ['lazy(() => import("./modules/academy/AcademyExpansionHub.jsx"))', "lazy Academy expansion boundary"],
  ['path="/academy/experience"', "Academy expansion route"],
  ['moduleKey="academy"><AcademyExpansionHub', "Academy module permission boundary"],
];

for (const [needle, label] of appRequirements) {
  if (!app.includes(needle)) {
    console.error(`${appPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const workspaceRequirements = [
  ['navigate("/academy/experience")', "visible Academy experience launcher"],
  ['translateAcademySkillGap(locale, "skillGap")', "learner launcher label"],
  ['translateAcademyExpansion(locale, "scenarioStudio")', "studio launcher label"],
];
for (const [needle, label] of workspaceRequirements) {
  if (!workspace.includes(needle)) {
    console.error(`${workspacePath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const hubRequirements = [
  ['canFeature("academy", "contentStudio")', "content-studio feature authority"],
  ['useState(canStudio ? "scenario" : "skill-gap")', "learner-safe default surface"],
  ['data-eay-product-state="loading"', "loading product-state marker"],
  ['data-eay-product-state="ready"', "ready product-state marker"],
  ['role="alert"', "error announcement semantics"],
  ['navigate("/academy")', "back-to-Academy composition"],
  ['<AcademyScenarioStudio', "scenario Studio composition"],
  ['<AcademyInteractionTimelineStudio', "interaction timeline composition"],
  ['<AcademyLocalizationGovernance', "localization governance composition"],
  ['<AcademySkillGap', "skill-gap composition"],
  ['<AcademyAchievements', "achievement composition"],
];

for (const [needle, label] of hubRequirements) {
  if (!hub.includes(needle)) {
    console.error(`${hubPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (!achievements.includes('/v1/academy/credentials/me')) {
  console.error(`${achievementsPath}: learner achievements must use canonical self-scoped credential authority.`);
  process.exit(1);
}
if (achievements.includes('signed_portable_credential: true')) {
  console.error(`${achievementsPath}: portable credential must not be promoted by frontend hardcode.`);
  process.exit(1);
}

if (!skillGap.includes('/v1/academy/credentials/me/skill-gaps')) {
  console.error(`${skillGapPath}: skill gaps must use canonical self-scoped Learning OS authority.`);
  process.exit(1);
}
if (/subject=|required_level=|current_level=/.test(skillGap)) {
  console.error(`${skillGapPath}: learner must not supply subject or proficiency authority in the request.`);
  process.exit(1);
}
const skillGapActionRequirements = [
  ['useNavigate', "router-owned recommendation navigation"],
  ['path?.enrollment_id', "server-authoritative enrollment navigation guard"],
  ['navigate(`/academy/enrollments/${encodeURIComponent(String(path.enrollment_id))}`)', "direct self-scoped enrollment route"],
  ['navigate("/academy")', "safe Academy fallback when no enrollment exists"],
  ['sx("openLearning")', "localized direct learning action"],
  ['sx("openAcademy")', "localized Academy fallback action"],
];
for (const [needle, label] of skillGapActionRequirements) {
  if (!skillGap.includes(needle)) {
    console.error(`${skillGapPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const scenarioRequirements = [
  ['<AcademyScenarioGraphCanvas', "graph canvas composition"],
  ['payload: { ...(item.payload || {}), authoring_position: position }', "authoring position persistence"],
  ['setEntryNodeKey', "stable entry-node identity"],
  ['from_node_key: edge.from_node_key === oldKey ? newKey', "node rename edge migration"],
  ['to_node_key: edge.to_node_key === oldKey ? newKey', "node rename target migration"],
  ['nodes.filter((item) => item.terminal).length <= 1', "last-terminal removal guard"],
  ['edge.from_node_key !== node.node_key && edge.to_node_key !== node.node_key', "connected-edge cleanup"],
  ['moveNodeOrder(index, -1)', "node reorder up"],
  ['moveNodeOrder(index, 1)', "node reorder down"],
  ['removeEdge(index)', "edge removal"],
  ['entry_node_key: entryNodeKey', "server-authoritative entry-node submission"],
  ['crypto.subtle.digest("SHA-256"', "scenario source fingerprint"],
];
for (const [needle, label] of scenarioRequirements) {
  if (!scenario.includes(needle)) {
    console.error(`${scenarioPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const graphRequirements = [
  ['onPointerDown', "pointer drag support"],
  ['setPointerCapture', "pointer capture"],
  ['ArrowLeft', "keyboard left movement"],
  ['ArrowRight', "keyboard right movement"],
  ['ArrowUp', "keyboard up movement"],
  ['ArrowDown', "keyboard down movement"],
  ['markerEnd="url(#academy-scenario-arrow)"', "directed edge rendering"],
  ['aria-label={`${node.node_key}. ${st(node.node_type)}. ${gx("keyboardMove")}`}', "keyboard move accessible name"],
  ['const [zoom, setZoom] = useState(1)', "local presentation-only zoom state"],
  ['(event.clientX - drag.startClientX) / zoom', "zoom-correct pointer x coordinate"],
  ['(event.clientY - drag.startClientY) / zoom', "zoom-correct pointer y coordinate"],
  ['function fitView()', "fit-to-viewport control"],
  ['function resetView()', "reset viewport control"],
  ['gx("zoomOut")', "localized zoom-out control"],
  ['gx("zoomIn")', "localized zoom-in control"],
  ['gx("fitView")', "localized fit-view control"],
  ['gx("resetView")', "localized reset-view control"],
  ['const diagnostics = useMemo(() => {', "live graph preflight diagnostics"],
  ['seenNodeKeys.has(key)', "duplicate node-key diagnostic"],
  ['!nodes.some((node) => node.terminal)', "missing terminal diagnostic"],
  ['!knownKeys.has(edge.from_node_key) || !knownKeys.has(edge.to_node_key)', "broken edge-reference diagnostic"],
  ['seenChoices.has(choiceIdentity)', "duplicate source-choice diagnostic"],
  ['!String(localizedLabel).trim()', "blank edge-label diagnostic"],
  ['className={`eay-academy-graph-preflight ${diagnostics.length ? "has-issues" : "is-ready"}`}', "preflight product-state surface"],
  ['role="status" aria-live="polite"', "accessible live preflight announcement"],
  ['gx("preflightReady")', "localized clean preflight state"],
];
for (const [needle, label] of graphRequirements) {
  if (!graph.includes(needle)) {
    console.error(`${graphPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const interactionRequirements = [
  ['apiPost("/v1/academy/admin/interaction-sets"', "canonical interaction authoring API"],
  ['crypto.subtle.digest("SHA-256"', "source fingerprint"],
  ['"checkpoint"', "checkpoint node"],
  ['"hotspot"', "hotspot node"],
  ['"multiple_choice"', "backend-aligned multiple-choice node"],
  ['"branch"', "branch node"],
  ['"cta"', "call-to-action node"],
  ['blocking: true', "blocking default"],
  ['required: true', "required default"],
  ['max="1000"', "backend-aligned score weight ceiling"],
];
for (const [needle, label] of interactionRequirements) {
  if (!interaction.includes(needle)) {
    console.error(`${interactionPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}
if (interaction.includes('"multi_choice"')) {
  console.error(`${interactionPath}: deprecated multi_choice alias must not diverge from backend multiple_choice authority.`);
  process.exit(1);
}

const localizationRequirements = [
  ['workspace?.authoring?.content_versions', "all-version localization authoring inventory"],
  ['item.content_version_id !== selectedSource.content_version_id', "source/target version separation"],
  ['["draft", "published"].includes(item.version_status)', "target lifecycle allowlist"],
  ['["draft", "published"].includes(item.content_status)', "content lifecycle allowlist"],
  ['value={item.content_version_id}', "exact target version identity"],
  ['apiGet("/v1/academy/localization/telemetry")', "governed localization telemetry API"],
  ['required_coverage_percent', "required-locale authority coverage"],
  ['required_authority_gap_count', "authority-gap telemetry"],
  ['stale_translation_count', "stale/source-change telemetry"],
  ['pending_review_count', "review-queue telemetry"],
  ['machine_draft_content_count', "machine-draft exposure telemetry"],
  ['rejected_translation_count', "review rejection telemetry"],
];
for (const [needle, label] of localizationRequirements) {
  if (!localization.includes(needle)) {
    console.error(`${localizationPath}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}
if (localization.includes('workspace?.content || []')) {
  console.error(`${localizationPath}: translation targets must not regress to latest-content-only inventory.`);
  process.exit(1);
}
if (/quality[_A-Z]?score/i.test(localization)) {
  console.error(`${localizationPath}: frontend must not invent a linguistic quality score without QA evidence.`);
  process.exit(1);
}

for (const [name, coverage] of [
  ["expansion", academyExpansionMessageCoverage(UI_LOCALES)],
  ["graph", academyGraphMessageCoverage(UI_LOCALES)],
  ["interaction", academyInteractionMessageCoverage(UI_LOCALES)],
  ["localization-telemetry", academyLocalizationTelemetryMessageCoverage(UI_LOCALES)],
  ["skill-gap", academySkillGapMessageCoverage(UI_LOCALES)],
  ["studio-terms", academyStudioTermMessageCoverage(UI_LOCALES)],
]) {
  for (const locale of UI_LOCALES) {
    if ((coverage.missing[locale] || []).length || (coverage.extra[locale] || []).length) {
      console.error(`Academy ${name} i18n coverage mismatch for ${locale}: ${JSON.stringify({ missing: coverage.missing[locale], extra: coverage.extra[locale] })}`);
      process.exit(1);
    }
  }
}

if (/localStorage|sessionStorage/.test(hub) || /localStorage|sessionStorage/.test(skillGap) || /localStorage|sessionStorage/.test(scenario)) {
  console.error(`${hubPath}: Academy experience authority must not be inferred from browser storage.`);
  process.exit(1);
}

console.log("Academy experience routing, actionable self-scope, graph preflight and viewport authoring, localization telemetry, schema, version and locale authority contract: PASS");
