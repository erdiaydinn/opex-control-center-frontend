import fs from "node:fs";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { controlCenterMessageCoverage } from "../src/platform/i18n/controlCenterMessages.js";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const locales = SUPPORTED_LOCALES.map((item) => item.code);
const expectedLocales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
requireCondition(JSON.stringify(locales) === JSON.stringify(expectedLocales), "Control Center locale set drifted");

const coverage = controlCenterMessageCoverage(locales);
for (const locale of locales) {
  requireCondition((coverage.missing[locale] || []).length === 0, `Control Center translations missing for ${locale}: ${(coverage.missing[locale] || []).join(", ")}`);
  requireCondition((coverage.extra[locale] || []).length === 0, `Control Center translation key drift for ${locale}: ${(coverage.extra[locale] || []).join(", ")}`);
}

const home = fs.readFileSync("src/modules/control-center/ControlCenterHome.jsx", "utf8");
const card = fs.readFileSync("src/modules/control-center/CommandModuleCard.jsx", "utf8");
const modules = fs.readFileSync("src/modules/control-center/commandCenterModules.js", "utf8");

requireCondition(home.includes("translateControlCenter"), "Control Center home must use the ten-locale catalog");
requireCondition(home.includes("formatDate(new Date()"), "Control Center date must use the shared locale-aware formatter");
requireCondition(home.includes("toLocaleLowerCase(locale)"), "Control Center search normalization must follow the active locale");
requireCondition(home.includes("accessibility.reduceMotion"), "Control Center home must respect reduced-motion preference");
requireCondition(home.includes('aria-live="polite"'), "Control Center empty state must be announced accessibly");
requireCondition(card.includes("translateControlCenter"), "Control Center cards must use the ten-locale catalog");
requireCondition(card.includes("accessibility.reduceMotion"), "Control Center cards must respect reduced-motion preference");
requireCondition(card.includes('aria-disabled={isDisabled}'), "Control Center cards must expose disabled state");
requireCondition(card.includes('aria-label={cc("openModuleAria"'), "Control Center cards must expose localized accessible names");

for (const forbidden of [
  "Günaydın",
  "İyi günler",
  "İyi akşamlar",
  "Operasyonu takip etme",
  "Modül, operasyon alanı",
  "Role based görünüm aktif",
  "Bu kullanıcı için görünen modül yok",
]) {
  requireCondition(!home.includes(forbidden), `Control Center home still exposes hard-coded UI text: ${forbidden}`);
}
for (const forbidden of ["<small>Scope</small>", "<small>Shortcut</small>", '"Hazırlanıyor"', '"Modüle gir"']) {
  requireCondition(!card.includes(forbidden), `Control Center card still exposes hard-coded UI text: ${forbidden}`);
}

for (const keyField of ["titleKey", "descriptionKey", "groupKey", "metaKey", "healthLabelKey"]) {
  requireCondition(modules.includes(keyField), `Control Center module catalog must remain key-based: ${keyField}`);
}
requireCondition(!/\bdescription\s*:\s*["'`]/u.test(modules), "Control Center module descriptions must not be hard-coded literals");
requireCondition(!/\bgroup\s*:\s*["'`]/u.test(modules), "Control Center module groups must not be hard-coded literals");
requireCondition(!/\bmeta\s*:\s*["'`]/u.test(modules), "Control Center module metadata must not bypass localization");

console.log("EAY Control Center ten-locale + reduced-motion regression: PASS");
