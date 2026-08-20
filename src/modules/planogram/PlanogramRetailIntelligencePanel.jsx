import React, { useCallback, useMemo, useState } from "react";
import { Activity, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramRetailIntelligence } from "../../platform/i18n/planogramRetailIntelligenceMessages.js";
import "./planogram-retail-intelligence.css";

function metric(value, formatNumber) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? formatNumber(numeric) : "—";
}

export default function PlanogramRetailIntelligencePanel({
  candidate,
  locale,
  formatNumber,
  canCreate,
}) {
  const t = useMemo(
    () => (key) => translatePlanogramRetailIntelligence(locale, key),
    [locale]
  );
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const evidence = candidate?.retail_intelligence || null;
  const canRun = Boolean(candidate && evidence && canCreate && !running);

  const run = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const response = await apiPost("/v1/planogram/retail-intelligence-preview", {
        ...evidence,
        store_code: evidence.store_code,
        products: candidate.products,
        layout: candidate.layout,
        store_dna: candidate.store_dna,
        mode: candidate.mode,
      });
      if (response?.market_leadership_claim_allowed !== false) {
        throw new Error("authority_boundary_failed");
      }
      setResult(response);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [canRun, candidate, evidence, t]);

  const comparison = result?.convergence?.comparison || {};
  const backtest = result?.shadow_backtest || {};
  const realogram = result?.realogram_v2 || {};
  const gate = result?.market_evidence_gate || {};

  return (
    <section className="eay-planogram-retail" aria-busy={running ? "true" : "false"}>
      <header>
        <div>
          <Activity size={20} aria-hidden="true" />
          <div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div>
        </div>
        <span>{t("previewOnly")}</span>
      </header>

      <div className="eay-planogram-retail-actions">
        <button type="button" onClick={run} disabled={!canRun}>
          {running ? t("running") : t("run")}
        </button>
        {!evidence ? <span>{t("noEvidence")}</span> : null}
        {!canCreate ? <span>{t("permissionRequired")}</span> : null}
      </div>
      {error ? <p className="eay-planogram-retail-error" role="alert">{error}</p> : null}

      {result ? (
        <div className="eay-planogram-retail-grid" role="status" aria-live="polite">
          <article>
            <h4>{t("convergence")}</h4>
            <dl>
              <dt>{t("selectedSku")}</dt><dd>{metric(comparison.target_sku_count, formatNumber)}</dd>
              <dt>{t("placedSku")}</dt><dd>{metric(comparison.physically_placed_target_sku_count, formatNumber)}</dd>
              <dt>{t("facingShortfall")}</dt><dd>{metric(comparison.facing_shortfall_total, formatNumber)}</dd>
              <dt>{t("converged")}</dt><dd>{comparison.converged ? t("pass") : t("blocked")}</dd>
            </dl>
          </article>
          <article>
            <h4>{t("backtest")}</h4>
            <dl>
              <dt>{t("pairs")}</dt><dd>{metric(backtest.usable_pair_count, formatNumber)}</dd>
              <dt>{t("evidenceComplete")}</dt><dd>{backtest.evidence_complete ? t("complete") : t("incomplete")}</dd>
              <dt>{t("causalBlocked")}</dt><dd>{backtest.causal_claim_allowed ? t("blocked") : t("pass")}</dd>
            </dl>
          </article>
          <article>
            <h4>{t("realogram")}</h4>
            <dl>
              <dt>{t("events")}</dt><dd>{metric(realogram.accepted_event_count, formatNumber)}</dd>
              <dt>{t("actions")}</dt><dd>{metric(realogram.action_count, formatNumber)}</dd>
              <dt>{t("duplicates")}</dt><dd>{metric(realogram.duplicate_event_count, formatNumber)}</dd>
            </dl>
          </article>
          <article>
            <h4>{t("evidenceGate")}</h4>
            <dl>
              <dt>{t("repositoryReview")}</dt><dd>{gate.repository_ready_for_independent_review ? t("pass") : t("blocked")}</dd>
              <dt>{t("marketClaim")}</dt><dd>{gate.market_leadership_claim_allowed ? t("pass") : t("blocked")}</dd>
              <dt>{t("blockers")}</dt><dd>{metric(gate.blockers?.length, formatNumber)}</dd>
            </dl>
          </article>
        </div>
      ) : null}

      <div className="eay-planogram-retail-boundary">
        <ShieldCheck size={18} aria-hidden="true" />
        <span>{t("boundary")}</span>
      </div>
    </section>
  );
}
