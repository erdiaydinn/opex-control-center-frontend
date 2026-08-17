import fs from "node:fs";
import process from "node:process";

import { auditLogMessageCoverage } from "../src/platform/i18n/auditLogMessages.js";

const locales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const source = fs.readFileSync("src/modules/audit-log/AuditLog.jsx", "utf8");

for (const [needle, label] of [
  ["data-eay-product-state={productState}", "explicit product-state marker"],
  ["aria-busy={loading ? \"true\" : \"false\"}", "busy state semantics"],
  ["role=\"status\"", "loading/empty status semantics"],
  ["role=\"alert\"", "error alert semantics"],
  ["t(\"retry\")", "localized retry action"],
  ["translateAuditLog(locale, key)", "localized audit copy"],
  ["formatDate(item.created_at", "locale-aware date formatting"],
  ["<caption className=\"sr-only\">{a(\"title\")}</caption>", "accessible table caption"],
  ["<th scope=\"col\">{a(\"time\")}</th>", "column header scope semantics"],
  ["<th scope=\"col\">{a(\"requestId\")}</th>", "request-id column scope semantics"],
]) {
  if (!source.includes(needle)) {
    console.error(`Audit Log product-state contract missing ${label}: ${needle}`);
    process.exit(1);
  }
}

for (const forbidden of ["err.message", "error.message", "Intl.DateTimeFormat(\"tr-TR\"", "Audit kayıtları alınamadı.", "İzin verildi", "Kayıt bulunamadı."]) {
  if (source.includes(forbidden)) {
    console.error(`Audit Log must not expose hard-coded/raw error presentation: ${forbidden}`);
    process.exit(1);
  }
}

const coverage = auditLogMessageCoverage(locales);
for (const locale of locales) {
  if ((coverage.missing[locale] || []).length || (coverage.extra[locale] || []).length) {
    console.error(`Audit Log translation parity failed for ${locale}: missing=${coverage.missing[locale].join(",")} extra=${coverage.extra[locale].join(",")}`);
    process.exit(1);
  }
}

console.log("Audit Log localization/product-state/accessibility contract: PASS");
