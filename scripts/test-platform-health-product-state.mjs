import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { platformHealthMessageCoverage } from "../src/platform/i18n/platformHealthMessages.js";
import { securityGuardianMessageCoverage } from "../src/platform/i18n/securityGuardianMessages.js";

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const locales = SUPPORTED_LOCALES.map((item) => item.code);

if (JSON.stringify(locales) !== JSON.stringify(expectedLocales)) {
  console.error("Platform Health locale set drifted from the canonical ten-locale contract.");
  process.exit(1);
}

for (const [label, coverage] of [
  ["Platform Health", platformHealthMessageCoverage(locales)],
  ["Security Guardian", securityGuardianMessageCoverage(locales)],
]) {
  for (const locale of locales) {
    const missing = coverage.missing[locale] || [];
    const extra = coverage.extra[locale] || [];
    if (missing.length) {
      console.error(`${label} translations missing for ${locale}: ${missing.join(", ")}`);
      process.exit(1);
    }
    if (extra.length) {
      console.error(`${label} translation key drift for ${locale}: ${extra.join(", ")}`);
      process.exit(1);
    }
  }
}

const health = fs.readFileSync("src/modules/platform-health/PlatformHealth.jsx", "utf8");
const quality = fs.readFileSync("src/modules/platform-health/platform-health-quality.css", "utf8");
const guardianCss = fs.readFileSync("src/modules/platform-health/platform-health-guardian.css", "utf8");

const required = [
  ["translatePlatformHealth", "Platform Health must use the ten-locale message catalog"],
  ["translateSecurityGuardian", "Security Guardian must use the ten-locale message catalog"],
  ["usePlatformPreferences", "Platform Health must use shared locale/accessibility preferences"],
  ["formatDate", "Platform Health dates must use locale-aware formatting"],
  ["formatNumber", "Platform Health numbers must use locale-aware formatting"],
  ["apiFetchWithStatus", "Platform Health must preserve structured degraded diagnostics"],
  ['result.status === 503', "only an explicit HTTP 503 diagnostic may be accepted as degraded"],
  ['result.data?.status === "degraded"', "degraded acceptance must require the canonical response state"],
  ["Boolean(result.data?.checks)", "degraded acceptance must require structured health checks"],
  ['"/v1/platform/security-guardian/workspace"', "Guardian must load from the protected Core control-plane route"],
  ['guardianResult.data?.scope === "eay_platform"', "Guardian response must prove EAY platform scope"],
  ['guardianResult.data?.visibility === "platform_admin_only"', "Guardian response must preserve platform-admin-only visibility"],
  ['human_approval_required', "Guardian must surface the human-approval policy"],
  ['automatic_production_remediation', "Guardian must surface automatic-remediation policy truth"],
  ['data-eay-product-state={productState}', "Platform Health must expose explicit product states"],
  ['role="alert"', "Platform Health failures must be announced assertively"],
  ['aria-live="polite"', "Platform Health async state must expose polite announcements"],
  ['aria-busy={loading}', "Platform Health loading must expose busy semantics"],
  ['catch {', "Platform Health must sanitize backend errors instead of reflecting raw details"],
  ['import "./platform-health-quality.css"', "Platform Health must load accessibility quality rules"],
  ['import "./platform-health-guardian.css"', "Platform Health must load Guardian presentation rules"],
];

for (const [needle, message] of required) {
  if (!health.includes(needle)) {
    console.error(`${message}: ${needle}`);
    process.exit(1);
  }
}

for (const forbidden of [
  "useAuth",
  "isSuperAdmin",
  "err.message",
  "error.message",
  'toLocaleString("tr-TR")',
  "Platform Health yalnızca Super Admin",
  "Sağlık bilgisi alınamadı",
  "Kontrol ediliyor",
  "zero vulnerabilities",
  "no vulnerabilities",
]) {
  if (health.includes(forbidden)) {
    console.error(`Platform Health regressed to role-local, raw-error, hard-coded, or unsupported security claims: ${forbidden}`);
    process.exit(1);
  }
}

for (const rule of [
  "min-height: 48px",
  ':dir(rtl) .platform-health-back-icon',
  '@media (prefers-reduced-motion: reduce)',
  'html[data-eay-reduce-motion="true"]',
]) {
  if (!quality.includes(rule)) {
    console.error(`Platform Health accessibility quality rule missing: ${rule}`);
    process.exit(1);
  }
}

for (const rule of [
  ".platform-health-guardian",
  "grid-template-columns",
  "overflow-wrap: anywhere",
  "@media (max-width: 620px)",
]) {
  if (!guardianCss.includes(rule)) {
    console.error(`Security Guardian responsive quality rule missing: ${rule}`);
    process.exit(1);
  }
}

console.log("Platform Health degraded diagnostics + ten-locale Guardian truth boundary: PASS");
