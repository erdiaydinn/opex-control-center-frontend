import React, { useCallback, useMemo, useState } from "react";
import { Activity, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramRetailIntelligence } from "../../platform/i18n/planogramRetailIntelligenceMessages.js";
import "./planogram-retail-intelligence.css";

const ACTION_MESSAGE_KEYS = Object.freeze({
  quarantine_and_quality_review: "actionQuarantine",
  replenish_or_substitute_review: "actionReplenish",
  assortment_replenishment_review: "actionAssortmentReplenishment",
  shelf_correction_review: "actionShelfCorrection",
  barcode_location_review: "actionBarcodeLocation",
  picker_route_review: "actionPickerRoute",
  facing_correction_review: "actionFacingCorrection",
  assortment_exception_review: "actionAssortmentException",
  refresh_shelf_evidence: "actionRefreshShelf",
  manual_review: "actionManualReview",
});

function metric(value, formatNumber) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? formatNumber(numeric) : "—";
}

function actionLabel(action, t) {
  const key = ACTION_MESSAGE_KEYS[action];
  return key ? t(key) : t("actionManualReview");
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
        order_baskets: candidate.order_baskets || [],
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
  const capacity = result?.convergence?.physical_capacity_v2 || {};
  const backtest = result?.shadow_backtest || {};
  const realogram = result?.realogram_v2 || {};
  const gate = result?.market_evidence_gate || {};
  const openActions = Array.isArray(realogram.action_queue) ? realogram.action_queue : [];
  const visibleActions = openActions.slice(0, 6);

  return (
    <section
      className="eay-planogram-retail"
      aria-busy={running ? "true" : "false"}
      data-capacity-v2-valid={capacity.valid === true ? "true" : "false"}
    >
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
        <>
          <div className="eay-planogram-retail-grid" role="status" aria-live="polite">
            <article>
              <h4>{t("convergence")}</h4>
              <dl>
                <dt>{t("selectedSku")}</dt>
                <dd>{metric(comparison.target_sku_count, formatNumber)}</dd>
                <dt>{t("placedSku")}</dt>
                <dd>{metric(comparison.physically_placed_target_sku_count, formatNumber)}</dd>
                <dt>{t("facingShortfall")}</dt>
                <dd>{metric(comparison.facing_shortfall_total, formatNumber)}</dd>
                <dt>{t("converged")}</dt>
                <dd>{comparison.converged ? t("pass") : t("blocked")}</dd>
                <dt>{t("fullDepthCapacity")}</dt>
                <dd>{capacity.valid ? t("pass") : t("blocked")}</dd>
                <dt>{t("capacityViolations")}</dt>
                <dd>{metric(capacity.violation_count, formatNumber)}</dd>
                <dt>{t("capacityWarnings")}</dt>
                <dd>{metric(capacity.warning_count, formatNumber)}</dd>
              </dl>
            </article>
            <article>
              <h4>{t("backtest")}</h4>
              <dl>
                <dt>{t("pairs")}</dt>
                <dd>{metric(backtest.usable_pair_count, formatNumber)}</dd>
                <dt>{t("evidenceComplete")}</dt>
                <dd>{backtest.evidence_complete ? t("complete") : t("incomplete")}</dd>
                <dt>{t("causalBlocked")}</dt>
                <dd>{backtest.causal_claim_allowed ? t("blocked") : t("pass")}</dd>
              </dl>
            </article>
            <article>
              <h4>{t("realogram")}</h4>
              <dl>
                <dt>{t("events")}</dt>
                <dd>{metric(realogram.accepted_event_count, formatNumber)}</dd>
                <dt>{t("openActions")}</dt>
                <dd>{metric(realogram.open_action_count, formatNumber)}</dd>
                <dt>{t("resolvedActions")}</dt>
                <dd>{metric(realogram.resolved_action_count, formatNumber)}</dd>
                <dt>{t("actionDedup")}</dt>
                <dd>{metric(realogram.action_dedup_count, formatNumber)}</dd>
                <dt>{t("duplicates")}</dt>
                <dd>{metric(realogram.duplicate_event_count, formatNumber)}</dd>
              </dl>
            </article>
            <article>
              <h4>{t("evidenceGate")}</h4>
              <dl>
                <dt>{t("repositoryReview")}</dt>
                <dd>{gate.repository_ready_for_independent_review ? t("pass") : t("blocked")}</dd>
                <dt>{t("marketClaim")}</dt>
                <dd>{gate.market_leadership_claim_allowed ? t("pass") : t("blocked")}</dd>
                <dt>{t("blockers")}</dt>
                <dd>{metric(gate.blockers?.length, formatNumber)}</dd>
                <dt>{t("previewPromotion")}</dt>
                <dd>{gate.production_promotion_allowed ? t("pass") : t("blocked")}</dd>
              </dl>
            </article>
          </div>

          <section className="eay-planogram-retail-action-queue" aria-label={t("actionQueue")}>
            <header>
              <div>
                <h4>{t("actionQueue")}</h4>
                <p>{t("actionQueueHint")}</p>
              </div>
              <strong>{metric(realogram.open_action_count, formatNumber)}</strong>
            </header>
            {visibleActions.length ? (
              <ol>
                {visibleActions.map((action) => (
                  <li key={action.action_id} data-priority={action.priority}>
                    <span className="eay-planogram-retail-priority">{action.priority}</span>
                    <div>
                      <strong>{actionLabel(action.action, t)}</strong>
                      <span>
                        {action.sku || t("noSku")} · {action.alert_code}
                      </span>
                    </div>
                    <code>{action.action_id}</code>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="eay-planogram-retail-empty">{t("noOpenActions")}</p>
            )}
          </section>
        </>
      ) : null}

      <div className="eay-planogram-retail-boundary">
        <ShieldCheck size={18} aria-hidden="true" />
        <span>{t("boundary")}</span>
      </div>
    </section>
  );
}
