const RANGE_FIELDS = ["low", "base", "high", "source_ref", "attested"];
const CAPEX_FIELDS = ["label", "amount", "currency", "source_ref", "attested"];
const ASSUMPTION_FIELDS = [
  "currency",
  "orders_per_day",
  "operating_days_per_year",
  "effective_seconds_per_meter",
  "loaded_labor_cost_per_hour",
  "capex_items",
];
const MAX_CAPEX_ITEMS = 100;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(raw, allowed) {
  const keys = Object.keys(raw).sort();
  return keys.length === allowed.length && keys.every((key, index) => key === [...allowed].sort()[index]);
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeRange(raw) {
  if (!isPlainObject(raw) || !exactKeys(raw, RANGE_FIELDS)) return null;
  const low = finiteNumber(raw.low);
  const base = finiteNumber(raw.base);
  const high = finiteNumber(raw.high);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (low == null || base == null || high == null) return null;
  if (!(low > 0 && low <= base && base <= high)) return null;
  if (sourceRef.length < 3 || sourceRef.length > 500 || raw.attested !== true) return null;
  return { low, base, high, source_ref: sourceRef, attested: true };
}

function normalizeCurrency(value) {
  const currency = String(value ?? "").trim().toUpperCase();
  return /^[A-Z]{3}$/.test(currency) ? currency : null;
}

function normalizeCapexItem(raw, currency) {
  if (!isPlainObject(raw) || !exactKeys(raw, CAPEX_FIELDS)) return null;
  const label = String(raw.label ?? "").trim();
  const amount = finiteNumber(raw.amount);
  const itemCurrency = normalizeCurrency(raw.currency);
  const sourceRef = String(raw.source_ref ?? "").trim();
  if (!label || label.length > 160 || amount == null || amount < 0) return null;
  if (itemCurrency !== currency) return null;
  if (sourceRef.length < 3 || sourceRef.length > 500 || raw.attested !== true) return null;
  return {
    label,
    amount,
    currency: itemCurrency,
    source_ref: sourceRef,
    attested: true,
  };
}

function topLevelEconomicsAuthorityIsBlocked(response) {
  const requiredFalse = [
    response.production_release_allowed,
    response.physical_relocation_execution_allowed,
    response.installation_approval_allowed,
    response.capex_approval_allowed,
    response.finance_approval_allowed,
    response.investment_decision_allowed,
    response.realized_savings_proven,
  ];
  return response.preview_only === true && requiredFalse.every((value) => value === false);
}

export function normalizePlanogramEconomicsAssumptions(payload) {
  if (!isPlainObject(payload) || !exactKeys(payload, ASSUMPTION_FIELDS)) return null;
  const currency = normalizeCurrency(payload.currency);
  if (!currency) return null;

  const ordersPerDay = normalizeRange(payload.orders_per_day);
  const operatingDays = normalizeRange(payload.operating_days_per_year);
  const secondsPerMeter = normalizeRange(payload.effective_seconds_per_meter);
  const laborCost = normalizeRange(payload.loaded_labor_cost_per_hour);
  if (!ordersPerDay || !operatingDays || !secondsPerMeter || !laborCost) return null;

  if (
    !Array.isArray(payload.capex_items) ||
    payload.capex_items.length === 0 ||
    payload.capex_items.length > MAX_CAPEX_ITEMS
  ) {
    return null;
  }
  const capexItems = payload.capex_items.map((item) => normalizeCapexItem(item, currency));
  if (capexItems.some((item) => !item)) return null;

  return {
    currency,
    orders_per_day: ordersPerDay,
    operating_days_per_year: operatingDays,
    effective_seconds_per_meter: secondsPerMeter,
    loaded_labor_cost_per_hour: laborCost,
    capex_items: capexItems,
  };
}

export function safePlanogramEconomicsPreview(response) {
  if (!isPlainObject(response) || !isPlainObject(response.result)) return null;
  const requiredFalse = [
    response.result.production_authority,
    response.result.physical_relocation_authority,
    response.result.installation_approved,
    response.result.capex_approved,
    response.result.finance_approved,
    response.result.investment_decision_allowed,
    response.result.realized_savings_proven,
    response.result.economics?.production_evidence,
    response.result.economics?.finance_approved,
    response.result.economics?.investment_decision_allowed,
  ];
  if (!topLevelEconomicsAuthorityIsBlocked(response) || requiredFalse.some((value) => value !== false)) {
    return null;
  }
  return response;
}

export function safePlanogramCandidateEconomicsPreview(response, expectedFingerprint) {
  if (!isPlainObject(response) || !isPlainObject(response.result)) return null;
  const fingerprint = String(expectedFingerprint || "").trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(fingerprint)) return null;
  if (!topLevelEconomicsAuthorityIsBlocked(response)) return null;
  if (response.candidate_selection_authority !== "server_recomputed_fingerprint_match_only") return null;
  if (String(response.result.layout_fingerprint || "").trim().toLowerCase() !== fingerprint) return null;

  const requiredFalse = [
    response.result.production_evidence,
    response.result.finance_approved,
    response.result.investment_decision_allowed,
    response.result.realized_savings_proven,
    response.result.economics?.production_evidence,
    response.result.economics?.finance_approved,
    response.result.economics?.investment_decision_allowed,
  ];
  if (requiredFalse.some((value) => value !== false)) return null;
  return response;
}

export const PLANOGRAM_ECONOMICS_LIMITS = Object.freeze({ maxCapexItems: MAX_CAPEX_ITEMS });
