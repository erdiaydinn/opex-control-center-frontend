import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { planogramPreviewMessageCoverage } from "../src/platform/i18n/planogramPreviewMessages.js";

const path = "src/modules/planogram/PlanogramStudio.jsx";
const source = fs.readFileSync(path, "utf8");
const previewCss = fs.readFileSync("src/modules/planogram/planogram-preview.css", "utf8");

const required = [
  ["data-eay-product-state", "explicit product-state marker"],
  ["aria-busy", "busy semantics"],
  ["aria-live=\"polite\"", "polite async announcement"],
  ["aria-atomic=\"true\"", "atomic state announcement"],
  ["data-eay-product-state=\"error\"", "error product-state marker"],
  ["role=\"alert\"", "assertive error semantics"],
  ["data-eay-product-state=\"ready\"", "ready product-state marker"],
  ["t(\"retry\")", "localized retry action"],
  ["apiPost(\"/v1/planogram/preview\", candidate)", "canonical Core preview route"],
  ["canAction(\"planogram\", \"create\")", "server-resolved preview permission"],
  ["MAX_PREVIEW_FILE_BYTES", "bounded client upload"],
  ["normalizeCandidateBundle", "candidate bundle validation"],
  ["preview?.engine_result", "server-authoritative preview result"],
  ["productionReleaseBlocked", "explicit non-production preview truth"],
];

for (const [needle, label] of required) {
  if (!source.includes(needle)) {
    console.error(`${path}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (/error\.message|error\.stack|JSON\.stringify\(error/.test(source)) {
  console.error(`${path}: raw error details must not be rendered into the product surface.`);
  process.exit(1);
}

if (!source.includes('/v1/planogram/readiness')) {
  console.error("Planogram readiness must remain server-authoritative.");
  process.exit(1);
}
if (!source.includes('data.production_ready ? "READY" : "BLOCKED"')) {
  console.error("Planogram must preserve explicit fail-closed production readiness rendering.");
  process.exit(1);
}
if (!source.includes('legacyBridgeAllowed: false')) {
  console.error("Planogram legacy bridge quarantine must remain enforced.");
  process.exit(1);
}
if (source.includes("production_release_allowed ?") || source.includes("publishable ?")) {
  console.error("Request-supplied preview must never unlock production publication in the frontend.");
  process.exit(1);
}

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const locales = SUPPORTED_LOCALES.map((item) => item.code);
if (JSON.stringify(locales) !== JSON.stringify(expectedLocales)) {
  console.error("Planogram preview locale set drifted.");
  process.exit(1);
}
const coverage = planogramPreviewMessageCoverage(locales);
for (const locale of locales) {
  if ((coverage.missing[locale] || []).length) {
    console.error(`Planogram preview translations missing for ${locale}: ${coverage.missing[locale].join(", ")}`);
    process.exit(1);
  }
  if ((coverage.extra[locale] || []).length) {
    console.error(`Planogram preview translation key drift for ${locale}: ${coverage.extra[locale].join(", ")}`);
    process.exit(1);
  }
}

for (const rule of [
  "min-height: 48px",
  ":dir(rtl) .eay-planogram-back-icon",
  "@media (prefers-reduced-motion: reduce)",
  'html[data-eay-reduce-motion="true"]',
]) {
  if (!previewCss.includes(rule)) {
    console.error(`Planogram preview accessibility rule missing: ${rule}`);
    process.exit(1);
  }
}

console.log("Planogram native preview + loading/error/ready truth contract: PASS");
