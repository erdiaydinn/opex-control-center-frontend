import React, { useCallback, useMemo, useState } from "react";
import { GitCompareArrows, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramScenario } from "../../platform/i18n/planogramScenarioMessages.js";
import {
  buildPlanogramScenarioPortfolio,
  safePhysicalLayoutPortfolioResponse,
} from "./planogramScenarioPortfolio.js";
import "./planogram-scenario-portfolio.css";

function valueOrDash(value, formatNumber) {
  const number = Number(value);
  return Number.isFinite(number) ? formatNumber(number) : "—";
}

export default function PlanogramScenarioPortfolio({ candidate, locale, formatNumber, canCreate }) {
  const t = useMemo(() => (key) => translatePlanogramScenario(locale, key), [locale]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [portfolio, setPortfolio] = useState(null);
  const basketCount = candidate?.order_baskets?.length || 0;
  const canRun = Boolean(candidate && canCreate && basketCount > 0 && !running);

  const run = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError("");
    setPortfolio(null);
    try {
      const raw = await apiPost("/v1/planogram/physical-layout-search-preview", candidate);
      const safe = safePhysicalLayoutPortfolioResponse(raw);
      if (!safe) throw new Error("scenario_authority_boundary_failed");
      const next = buildPlanogramScenarioPortfolio(safe.result);
      if (!next.available) throw new Error(next.reason || "scenario_portfolio_unavailable");
      setPortfolio(next);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [canRun, candidate, t]);

  return (
    <section className="eay-planogram-scenario" aria-busy={running ? "true" : "false"}>
      <header>
        <div>
          <GitCompareArrows size={20} aria-hidden="true" />
          <div>
            <h3>{t("title")}</h3>
            <p>{t("subtitle")}</p>
          </div>
        </div>
        <span>{t("previewOnly")}</span>
      </header>

      <div className="eay-planogram-scenario-actions">
        <button type="button" onClick={run} disabled={!canRun}>
          {running ? t("running") : t("run")}
        </button>
        {!canCreate ? <span>{t("permissionRequired")}</span> : null}
        {!basketCount ? <span>{t("basketsRequired")}</span> : null}
      </div>
      {error ? <p className="eay-planogram-scenario-error" role="alert">{error}</p> : null}

      {portfolio ? (
        <div className="eay-planogram-scenario-result">
          <div className="eay-planogram-scenario-summary">
            <div><span>{t("evaluated")}</span><strong>{formatNumber(portfolio.evaluatedCandidateCount)}</strong></div>
            <div><span>{t("frontierCount")}</span><strong>{formatNumber(portfolio.frontierCount)}</strong></div>
            <div><span>{t("frontier")}</span><strong>{portfolio.frontierCount ? "✓" : "—"}</strong></div>
          </div>

          <div className="eay-planogram-scenario-grid">
            {portfolio.plans.map((plan) => {
              const candidateRow = plan.candidate;
              const objective = candidateRow.objective || {};
              return (
                <article key={plan.planId} data-frontier={plan.onFrontier ? "true" : "false"}>
                  <header>
                    <strong>{plan.planId.replace("plan-", "Plan ")}</strong>
                    {plan.onFrontier ? <span>{t("frontier")}</span> : null}
                  </header>
                  <div className="eay-planogram-scenario-roles">
                    <span>{t("roles")}</span>
                    <strong>{plan.roles.map((role) => t(role)).join(" · ")}</strong>
                  </div>
                  <dl>
                    <dt>{t("movedModules")}</dt>
                    <dd>{valueOrDash(candidateRow.moved_module_count, formatNumber)}</dd>
                    <dt>{t("p95Route")}</dt>
                    <dd>{valueOrDash(candidateRow.tour_p95_m ?? objective.tour_p95_m, formatNumber)} m</dd>
                    <dt>{t("avgRoute")}</dt>
                    <dd>{valueOrDash(candidateRow.tour_average_m ?? objective.tour_average_m, formatNumber)} m</dd>
                    <dt>{t("unplacedSales")}</dt>
                    <dd>{valueOrDash(objective.weighted_unplaced_sales, formatNumber)}</dd>
                    <dt>{t("coverageShortfall")}</dt>
                    <dd>{valueOrDash(objective.coverage_shortfall, formatNumber)}</dd>
                  </dl>
                  <div className="eay-planogram-scenario-fingerprint">
                    <span>{t("fingerprint")}</span>
                    <code>{candidateRow.layout_fingerprint}</code>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="eay-planogram-scenario-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>{t("boundary")}</strong><span>{t("capexBoundary")}</span></div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
