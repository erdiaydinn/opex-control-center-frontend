import fs from "node:fs";
import process from "node:process";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { platformHealthMessageCoverage } from "../src/platform/i18n/platformHealthMessages.js";

const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const locales = SUPPORTED_LOCALES.map((item) => item.code);

if (JSON.stringify(locales) !== JSON.stringify(expectedLocales)) {
  console.error("Platform Health locale set drifted from the canonical ten-locale contract.");
  process.exit(1);
}

const coverage = platformHealthMessageCoverage(locales);
for (const locale of locales) {
  const missing = coverage.missing[locale] || [];
  const extra = coverage.extra[locale] || [];
  if (missing.length) {
    console.error(`Platform Health translations missing for ${locale}: ${missing.join(", ")}`);
    process.exit(1);
  }
  if (extra.length) {
    console.error(`Platform Health translation key drift for ${locale}: ${extra.join(", ")}`);
    process.exit(1);
  }
}

const health = fs.readFileSync("src/modules/platform-health/PlatformHealth.jsx", "utf8");
const quality = fs.readFileSync("src/modules/platform-health/platform-health-quality.css", "utf8");

const required = [
  ["translatePlatformHealth", "Platform Health must use the ten-locale message catalog"],
  ["usePlatformPreferences", "Platform Health must use shared locale/accessibility preferences"],
  ["formatDate", "Platform Health dates must use locale-aware formatting"],
  ["formatNumber", "Platform Health numbers must use locale-aware formatting"],
  ['data-eay-product-state={productState}', "Platform Health must expose explicit product states"],
  ['role="alert"', "Platform Health failures must be announced assertively"],
  ['aria-live="polite"', "Platform Health async state must expose polite announcements"],
  ['aria-busy={loading}', "Platform Health loading must expose busy semantics"],
  ['catch {', "Platform Health must sanitize backend errors instead of reflecting raw details"],
  ['import "./platform-health-quality.css"', "Platform Health must load its accessibility quality rules"],
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
  'toLocaleString("tr-TR")',
  "Platform Health yalnızca Super Admin",
  "Sağlık bilgisi alınamadı",
  "Kontrol ediliyor",
]) {
  if (health.includes(forbidden)) {
    console.error(`Platform Health regressed to role-local, raw-error, or hard-coded UI behavior: ${forbidden}`);
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

console.log("Platform Health ten-locale + accessible fail-closed product state: PASS");
