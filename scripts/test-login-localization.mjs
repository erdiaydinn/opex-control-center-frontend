import fs from "node:fs";

import { loginMessageCoverage } from "../src/platform/i18n/loginMessages.js";
import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const locales = SUPPORTED_LOCALES.map((item) => item.code);
const expected = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
requireCondition(JSON.stringify(locales) === JSON.stringify(expected), "Login locale set drifted");

const coverage = loginMessageCoverage(locales);
for (const locale of locales) {
  requireCondition((coverage.missing[locale] || []).length === 0, `Login translations missing for ${locale}: ${(coverage.missing[locale] || []).join(", ")}`);
  requireCondition((coverage.extra[locale] || []).length === 0, `Login translation key drift for ${locale}: ${(coverage.extra[locale] || []).join(", ")}`);
}

const login = fs.readFileSync("src/pages/Login.jsx", "utf8");
requireCondition(login.includes("translateLogin"), "Login must use its ten-locale catalog");
requireCondition(login.includes("usePlatformPreferences"), "Login must follow the platform locale preference");
for (const forbidden of [
  "Oturum kontrol ediliyor",
  "Kurumsal kimlik doğrulama",
  "Kurumsal SSO ile giriş yap",
  "Yerel demo parola",
]) {
  requireCondition(!login.includes(forbidden), `Login still contains hard-coded Turkish UI copy: ${forbidden}`);
}

console.log("EAY Login ten-locale localization contract: PASS");
