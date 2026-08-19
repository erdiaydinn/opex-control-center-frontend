const OBJECTIVE_FIELDS = [
  "hard_violation_count",
  "weighted_unplaced_sales",
  "unplaced_sku_count",
  "tour_unsimulated_order_count",
  "tour_p95_m",
  "tour_average_m",
  "coverage_shortfall",
  "brand_fragmentation",
  "capacity_pressure",
];

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function numberOrInfinity(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.POSITIVE_INFINITY;
}

function metric(candidate, field) {
  if (field === "tour_p95_m") return numberOrInfinity(candidate.tour_p95_m ?? candidate.objective?.tour_p95_m);
  if (field === "tour_average_m") return numberOrInfinity(candidate.tour_average_m ?? candidate.objective?.tour_average_m);
  return numberOrInfinity(candidate.objective?.[field]);
}

function dominates(left, right) {
  let strictlyBetter = false;
  for (const field of OBJECTIVE_FIELDS) {
    const a = metric(left, field);
    const b = metric(right, field);
    if (a > b) return false;
    if (a < b) strictlyBetter = true;
  }
  const aMoves = numberOrInfinity(left.moved_module_count);
  const bMoves = numberOrInfinity(right.moved_module_count);
  if (aMoves > bMoves) return false;
  if (aMoves < bMoves) strictlyBetter = true;
  return strictlyBetter;
}

function uniqueByFingerprint(candidates) {
  const seen = new Set();
  return candidates.filter((candidate) => {
    const fingerprint = String(candidate.layout_fingerprint || "").trim();
    if (!fingerprint || seen.has(fingerprint)) return false;
    seen.add(fingerprint);
    return true;
  });
}

function objectiveTuple(candidate, fields) {
  return fields.map((field) => metric(candidate, field));
}

function compareTuple(left, right) {
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    const a = left[index] ?? Number.POSITIVE_INFINITY;
    const b = right[index] ?? Number.POSITIVE_INFINITY;
    if (a !== b) return a - b;
  }
  return 0;
}

function bestBy(candidates, tuple) {
  if (!candidates.length) return null;
  return [...candidates].sort((left, right) => {
    const compared = compareTuple(tuple(left), tuple(right));
    if (compared) return compared;
    return String(left.layout_fingerprint || "").localeCompare(String(right.layout_fingerprint || ""));
  })[0];
}

export function safePhysicalLayoutPortfolioResponse(response) {
  if (!isPlainObject(response) || !isPlainObject(response.result)) return null;
  if (response.preview_only !== true) return null;
  const requiredFalse = [
    response.production_release_allowed,
    response.physical_relocation_execution_allowed,
    response.installation_approval_allowed,
    response.capex_approval_allowed,
    response.result.production_authority,
    response.result.physical_relocation_authority,
    response.result.installation_approved,
    response.result.capex_approved,
    response.result.physical_layout_optimizer?.production_authority,
    response.result.physical_layout_optimizer?.physical_relocation_authority,
    response.result.physical_layout_optimizer?.installation_approved,
  ];
  if (requiredFalse.some((value) => value !== false)) return null;
  return response;
}

export function safePhysicalLayoutCandidateReplayResponse(response, expectedFingerprint) {
  if (!isPlainObject(response) || !isPlainObject(response.result)) return null;
  if (response.preview_only !== true || response.result.preview_only !== true) return null;
  if (response.result.available !== true) return null;
  if (!isPlainObject(response.result.physical_layout) || !isPlainObject(response.result.optimizer_result)) {
    return null;
  }
  const fingerprint = String(response.result.layout_fingerprint || "").trim().toLowerCase();
  if (!fingerprint || fingerprint !== String(expectedFingerprint || "").trim().toLowerCase()) {
    return null;
  }
  const requiredFalse = [
    response.production_release_allowed,
    response.physical_relocation_execution_allowed,
    response.installation_approval_allowed,
    response.capex_approval_allowed,
    response.result.production_authority,
    response.result.execution_authority,
    response.result.physical_relocation_authority,
    response.result.installation_approved,
    response.result.capex_approved,
    response.result.global_optimum_claim,
  ];
  if (requiredFalse.some((value) => value !== false)) return null;
  return response;
}

export function buildPlanogramScenarioPortfolio(result) {
  const optimizer = result?.physical_layout_optimizer;
  if (!isPlainObject(optimizer) || !Array.isArray(optimizer.candidates)) {
    return { available: false, reason: "candidate_portfolio_missing", frontier: [], plans: [] };
  }

  const candidates = uniqueByFingerprint(
    optimizer.candidates.filter((candidate) => (
      isPlainObject(candidate)
      && isPlainObject(candidate.objective)
      && candidate.production_authority === false
      && String(candidate.layout_fingerprint || "").trim()
    ))
  );
  if (!candidates.length) {
    return { available: false, reason: "candidate_portfolio_empty", frontier: [], plans: [] };
  }

  const frontier = candidates.filter(
    (candidate) => !candidates.some(
      (other) => other !== candidate && dominates(other, candidate)
    )
  );
  const pool = frontier.length ? frontier : candidates;
  const selectedFingerprint = String(optimizer.selected_layout_fingerprint || "").trim();
  const baselineFingerprint = String(optimizer.baseline_layout_fingerprint || "").trim();

  const choices = [
    {
      role: "baseline",
      candidate: candidates.find((candidate) => candidate.layout_fingerprint === baselineFingerprint)
        || candidates.find((candidate) => candidate.label === "baseline")
        || bestBy(pool, (candidate) => [numberOrInfinity(candidate.moved_module_count)]),
    },
    {
      role: "engineSelected",
      candidate: candidates.find((candidate) => candidate.layout_fingerprint === selectedFingerprint)
        || bestBy(pool, (candidate) => objectiveTuple(candidate, OBJECTIVE_FIELDS)),
    },
    {
      role: "fastestRoute",
      candidate: bestBy(pool, (candidate) => [
        metric(candidate, "tour_p95_m"),
        metric(candidate, "tour_average_m"),
        numberOrInfinity(candidate.moved_module_count),
      ]),
    },
    {
      role: "qualityFirst",
      candidate: bestBy(pool, (candidate) => [
        metric(candidate, "hard_violation_count"),
        metric(candidate, "weighted_unplaced_sales"),
        metric(candidate, "unplaced_sku_count"),
        metric(candidate, "tour_unsimulated_order_count"),
        metric(candidate, "coverage_shortfall"),
        numberOrInfinity(candidate.moved_module_count),
      ]),
    },
  ];

  const plans = [];
  const byFingerprint = new Map();
  for (const choice of choices) {
    if (!choice.candidate) continue;
    const fingerprint = choice.candidate.layout_fingerprint;
    const existing = byFingerprint.get(fingerprint);
    if (existing) {
      existing.roles.push(choice.role);
      continue;
    }
    const plan = {
      planId: `plan-${String.fromCharCode(65 + plans.length)}`,
      roles: [choice.role],
      candidate: choice.candidate,
      onFrontier: frontier.some((row) => row.layout_fingerprint === fingerprint),
      productionAuthority: false,
      executionAuthority: false,
    };
    plans.push(plan);
    byFingerprint.set(fingerprint, plan);
  }

  return {
    available: plans.length > 0,
    reason: plans.length ? null : "scenario_portfolio_unavailable",
    evaluatedCandidateCount: candidates.length,
    frontierCount: frontier.length,
    frontier,
    plans: plans.slice(0, 4),
    selectedLayoutFingerprint: selectedFingerprint || null,
    baselineLayoutFingerprint: baselineFingerprint || null,
    boundedSearch: true,
    globalOptimumClaim: false,
    capexCompared: false,
    productionAuthority: false,
    executionAuthority: false,
  };
}

export const PLANOGRAM_SCENARIO_OBJECTIVE_FIELDS = Object.freeze([...OBJECTIVE_FIELDS]);
