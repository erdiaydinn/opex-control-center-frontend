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
  ["safeAuditDate(item?.created_at, formatDate)", "fail-safe locale-aware date formatting"],
  ["safeAuditText(item?.actor)", "fail-safe actor rendering"],
  ["safeAuditText(item?.action)", "fail-safe action rendering"],
  ["safeAuditText(item?.data?.status_code)", "fail-safe status rendering"],
  ["const requestId = safeRequestId(item?.request_id)", "fail-safe request-id rendering"],
  ["const normalizedDecision = safeDecision(item?.decision)", "fail-safe decision rendering"],
  ["<caption className=\"sr-only\">{a(\"title\")}</caption>", "accessible table caption"],
  ["<th scope=\"col\">{a(\"time\")}</th>", "column header scope semantics"],
  ["<th scope=\"col\">{a(\"requestId\")}</th>", "request-id column scope semantics"],
  ["className=\"sr-only\" role=\"status\" aria-live=\"polite\" aria-atomic=\"true\"", "result-count live announcement"],
  ["{a(\"total\")}: {summary.total}", "localized result count"],
  ["const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS)", "separate applied-filter authority"],
  ["const nextFilters = { actor, decision, action }", "submitted filter snapshot"],
  ["setAppliedFilters(nextFilters)", "applied-filter update"],
  ["onClick={() => loadEvents(appliedFilters)}", "refresh/retry use applied filters"],
  ["setAppliedFilters(EMPTY_FILTERS)", "reset applied-filter authority"],
  ["const requestSequence = useRef(0)", "monotonic request ordering authority"],
  ["const requestId = requestSequence.current + 1", "per-request sequence allocation"],
  ["requestSequence.current = requestId", "latest request publication"],
  ["if (requestId !== requestSequence.current) return", "stale success/error suppression"],
  ["if (requestId === requestSequence.current)", "latest-request loading completion"],
  ["requestSequence.current += 1", "unmount request invalidation"],
]) {
  if (!source.includes(needle)) {
    console.error(`Audit Log product-state contract missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const appliedFilterReloads = source.match(/loadEvents\(appliedFilters\)/g) || [];
if (appliedFilterReloads.length < 2) {
  console.error("Audit Log refresh and retry must both reload the last submitted filter snapshot.");
  process.exit(1);
}

const staleRequestGuards = source.match(/requestId !== requestSequence\.current/g) || [];
if (staleRequestGuards.length < 2) {
  console.error("Audit Log must suppress both stale success and stale error responses.");
  process.exit(1);
}

if (/async function loadEvents\(filters\s*=/.test(source)) {
  console.error("Audit Log loader must require an explicit filter snapshot instead of reading draft inputs implicitly.");
  process.exit(1);
}

for (const forbidden of [
  "err.message",
  "error.message",
  "Intl.DateTimeFormat(\"tr-TR\"",
  "Audit kayıtları alınamadı.",
  "İzin verildi",
  "Kayıt bulunamadı.",
  "item.request_id.slice(",
  "<td>{item.actor}</td>",
  "<code>{item.action}</code>",
  "item.data?.status_code ??",
  "labels[decision] || decision",
]) {
  if (source.includes(forbidden)) {
    console.error(`Audit Log must not expose hard-coded/raw or crash-prone presentation: ${forbidden}`);
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

console.log("Audit Log localization/product-state/accessibility/query-state/resilience/race contract: PASS");
