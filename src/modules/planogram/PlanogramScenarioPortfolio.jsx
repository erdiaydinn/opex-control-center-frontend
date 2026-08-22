import React, { useCallback, useMemo, useState } from "react";
import { GitCompareArrows, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramScenario } from "../../platform/i18n/planogramScenarioMessages.js";
import PlanogramDigitalTwin from "./PlanogramDigitalTwin.jsx";
import PlanogramEconomicsPanel from "./PlanogramEconomicsPanel.jsx";
import {
  buildPlanogramScenarioPortfolio,
  safePhysicalLayoutCandidateReplayResponse,
  safePhysicalLayoutPortfolioResponse,
} from "./planogramScenarioPortfolio.js";
import "./planogram-scenario-portfolio.css";

function valueOrDash(value, formatNumber) {
  const number = Number(value);
  return Number.isFinite(number) ? formatNumber(number) : "—";
}

export default function PlanogramScenarioPortfolio({
  candidate,
  locale,
  formatNumber,
  canCreate,
  canApprove,
}) {
  const t = useMemo(() => (key) => translatePlanogramScenario(locale, key), [locale]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [portfolio, setPortfolio] = useState(null);
  const [replayingFingerprint, setReplayingFingerprint] = useState("");
  const [scenarioPreview, setScenarioPreview] = useState(null);
  const [scenarioPreviewError, setScenarioPreviewError] = useState("");
  const basketCount = candidate?.order_baskets?.length || 0;
  const canRun = Boolean(candidate && canCreate && basketCount > 0 && !running);

  const run = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError("");
    setPortfolio(null);
    setScenarioPreview(null);
    setScenarioPreviewError("");
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

  const openTwin = useCallback(async (plan) => {
    const fingerprint = String(plan?.candidate?.layout_fingerprint || "").trim().toLowerCase();
    if (!candidate || !canCreate || !basketCount || !fingerprint || replayingFingerprint) return;
    setReplayingFingerprint(fingerprint);
    setScenarioPreview(null);
    setScenarioPreviewError("");
    try {
      const raw = await apiPost("/v1/planogram/physical-layout-candidate-preview", {
        ...candidate,
        layout_fingerprint: fingerprint,
      });
      const safe = safePhysicalLayoutCandidateReplayResponse(raw, fingerprint);
      if (!safe) throw new Error("scenario_replay_authority_boundary_failed");
      setScenarioPreview({
        planId: plan.planId,
        fingerprint,
        engineResult: safe.result.optimizer_result,
        candidate: {
          ...candidate,
          layout: safe.result.physical_layout,
        },
      });
    } catch {
      setScenarioPreviewError(t("twinUnavailable"));
    } finally {
      setReplayingFingerprint("");
    }
  }, [basketCount, canCreate, candidate, replayingFingerprint, t]);

  return (
    <section className="eay-planogram-scenario" aria-busy={running || Boolean(replayingFingerprint) ? "true" : "false"}>
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
        <button type="button" onClick={run} disabled={!canRun || Boolean(replayingFingerprint)}>
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
              const fingerprint = String(candidateRow.layout_fingerprint || "").toLowerCase();
              const replaying = replayingFingerprint === fingerprint;
              return (
                <article key={plan.planId} data-frontier={plan.onFrontier ? "true" : "false"}>
                  <header>
                    <strong>{t("plan")} {plan.planId.slice(-1).toUpperCase()}</strong>
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
                  <button
                    type="button"
                    className="eay-planogram-scenario-twin-button"
                    onClick={() => openTwin(plan)}
                    disabled={!canCreate || !basketCount || Boolean(replayingFingerprint)}
                  >
                    {replaying ? t("openingTwin") : t("openTwin")}
                  </button>
                </article>
              );
            })}
          </div>

          {scenarioPreviewError ? (
            <p className="eay-planogram-scenario-error" role="alert">{scenarioPreviewError}</p>
          ) : null}

          {scenarioPreview ? (
            <div className="eay-planogram-scenario-twin" role="status" aria-live="polite">
              <header>
                <div>
                  <strong>{t("twinTitle")}</strong>
                  <span>{t("plan")} {scenarioPreview.planId.slice(-1).toUpperCase()}</span>
                </div>
                <div>
                  <span>{t("selectedFingerprint")}</span>
                  <code>{scenarioPreview.fingerprint}</code>
                </div>
              </header>
              <p>{t("twinBoundary")}</p>
              <PlanogramDigitalTwin
                engineResult={scenarioPreview.engineResult}
                candidate={scenarioPreview.candidate}
                locale={locale}
                formatNumber={formatNumber}
              />
              <PlanogramEconomicsPanel
                candidate={candidate}
                locale={locale}
                formatNumber={formatNumber}
                canCreate={canCreate}
                canApprove={canApprove}
                layoutFingerprint={scenarioPreview.fingerprint}
              />
            </div>
          ) : null}

          <div className="eay-planogram-scenario-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>{t("boundary")}</strong><span>{t("capexBoundary")}</span></div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
