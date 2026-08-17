import React, { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch, apiGet } from "../../api/client.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./budget-planning.css";

function idempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = new Uint32Array(4);
  globalThis.crypto?.getRandomValues?.(bytes);
  return `budget-${Date.now()}-${Array.from(bytes).join("-")}`;
}

function statusKey(status) {
  const value = String(status || "").toUpperCase();
  if (value === "ACTIVE") return "budgetStatusActive";
  if (value === "OPEN") return "budgetStatusOpen";
  if (value === "CLOSED") return "budgetStatusClosed";
  return "budgetStatusDraft";
}

function safeDate(value) {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return `${value}T12:00:00`;
  return value;
}

async function command(path, payload = {}) {
  return apiFetch(path, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey() },
    body: JSON.stringify(payload),
  });
}

export default function BudgetPlanningWorkspace() {
  const { t, formatCurrency, formatDate } = usePlatformPreferences();
  const [plans, setPlans] = useState([]);
  const [costCenters, setCostCenters] = useState([]);
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const [planForm, setPlanForm] = useState({
    name: "",
    fiscal_year: new Date().getFullYear(),
    base_currency: "TRY",
  });
  const [periodForm, setPeriodForm] = useState({ code: "", starts_on: "", ends_on: "" });
  const [centerForm, setCenterForm] = useState({ code: "", name: "", store_code: "" });
  const [lineForm, setLineForm] = useState({
    fiscal_period_id: "",
    cost_center_id: "",
    category: "",
    budget_base_amount: "",
  });
  const [forecastForm, setForecastForm] = useState({
    budget_line_id: "",
    forecast_base_amount: "",
    as_of: new Date().toISOString().slice(0, 10),
  });

  const loadCatalog = useCallback(async () => {
    const [planPayload, centerPayload] = await Promise.all([
      apiGet("/v1/budget/plans"),
      apiGet("/v1/budget/cost-centers"),
    ]);
    const nextPlans = Array.isArray(planPayload?.items) ? planPayload.items : [];
    const nextCenters = Array.isArray(centerPayload?.items) ? centerPayload.items : [];
    setPlans(nextPlans);
    setCostCenters(nextCenters);
    setSelectedPlanId((current) => {
      if (current && nextPlans.some((item) => item.id === current)) return current;
      return nextPlans[0]?.id || "";
    });
    return { plans: nextPlans, costCenters: nextCenters };
  }, []);

  const loadWorkspace = useCallback(async (planId) => {
    if (!planId) {
      setWorkspace(null);
      return null;
    }
    const payload = await apiGet(`/v1/budget/plans/${planId}/workspace`);
    setWorkspace(payload);
    return payload;
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    loadCatalog()
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadCatalog, reloadKey]);

  useEffect(() => {
    let active = true;
    setError(false);
    loadWorkspace(selectedPlanId).catch(() => {
      if (active) setError(true);
    });
    return () => {
      active = false;
    };
  }, [loadWorkspace, selectedPlanId, reloadKey]);

  const selectedPlan = workspace?.plan || plans.find((item) => item.id === selectedPlanId) || null;
  const periods = workspace?.periods || [];
  const lines = workspace?.lines || [];
  const isDraft = selectedPlan?.status === "DRAFT";
  const canActivate = isDraft && periods.length > 0 && lines.length > 0;

  const selectedForecastLine = useMemo(
    () => lines.find((item) => item.id === forecastForm.budget_line_id) || null,
    [forecastForm.budget_line_id, lines]
  );

  const refreshCurrent = useCallback(async () => {
    await loadCatalog();
    if (selectedPlanId) await loadWorkspace(selectedPlanId);
  }, [loadCatalog, loadWorkspace, selectedPlanId]);

  async function runMutation(action) {
    setSaving(true);
    setError(false);
    try {
      await action();
      await refreshCurrent();
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  }

  async function createPlan(event) {
    event.preventDefault();
    setSaving(true);
    setError(false);
    try {
      const created = await command("/v1/budget/plans", {
        ...planForm,
        fiscal_year: Number(planForm.fiscal_year),
      });
      await loadCatalog();
      setSelectedPlanId(created.id);
      await loadWorkspace(created.id);
      setPlanForm((current) => ({ ...current, name: "" }));
    } catch {
      setError(true);
    } finally {
      setSaving(false);
    }
  }

  async function createPeriod(event) {
    event.preventDefault();
    if (!selectedPlanId) return;
    await runMutation(async () => {
      await command("/v1/budget/periods", { plan_id: selectedPlanId, ...periodForm });
      setPeriodForm({ code: "", starts_on: "", ends_on: "" });
    });
  }

  async function createCostCenter(event) {
    event.preventDefault();
    await runMutation(async () => {
      await command("/v1/budget/cost-centers", {
        code: centerForm.code,
        name: centerForm.name,
        store_code: centerForm.store_code || null,
      });
      setCenterForm({ code: "", name: "", store_code: "" });
    });
  }

  async function createLine(event) {
    event.preventDefault();
    if (!selectedPlanId) return;
    await runMutation(async () => {
      await command("/v1/budget/lines", {
        plan_id: selectedPlanId,
        fiscal_period_id: lineForm.fiscal_period_id,
        cost_center_id: lineForm.cost_center_id,
        category: lineForm.category,
        supplier_id: null,
        supplier_name: null,
        store_code: null,
        budget_base_amount: lineForm.budget_base_amount,
      });
      setLineForm((current) => ({ ...current, category: "", budget_base_amount: "" }));
    });
  }

  async function activatePlan() {
    if (!selectedPlanId || !canActivate) return;
    await runMutation(() => command(`/v1/budget/plans/${selectedPlanId}/activate`, {}));
  }

  async function createForecast(event) {
    event.preventDefault();
    if (!selectedForecastLine) return;
    await runMutation(async () => {
      await command("/v1/budget/forecasts", {
        budget_line_id: selectedForecastLine.id,
        fiscal_period_id: selectedForecastLine.fiscal_period_id,
        cost_center_id: selectedForecastLine.cost_center_id,
        forecast_base_amount: forecastForm.forecast_base_amount,
        as_of: forecastForm.as_of,
      });
      setForecastForm((current) => ({ ...current, forecast_base_amount: "" }));
    });
  }

  return (
    <section className="budget-planning" aria-labelledby="budget-planning-title" data-roadmap-item="28">
      <header className="budget-planning__header">
        <div>
          <h1 id="budget-planning-title">{t("budgetPlanning")}</h1>
          <p>{t("budgetPlanningSubtitle")}</p>
        </div>
        <button type="button" onClick={() => setReloadKey((value) => value + 1)} disabled={loading || saving}>
          {t("refresh")}
        </button>
      </header>

      {loading && (
        <div role="status" aria-live="polite" aria-busy="true" data-eay-product-state="loading">
          {t("loading")}
        </div>
      )}
      {!loading && error && (
        <div role="alert" data-eay-product-state="error">
          <strong>{t("errorTitle")}</strong>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>{t("retry")}</button>
        </div>
      )}

      {!loading && (
        <div className="budget-planning__grid" data-eay-product-state="ready">
          <aside className="budget-planning__rail" aria-label={t("budgetPlans")}>
            <h2>{t("budgetPlans")}</h2>
            {plans.length === 0 && <p>{t("budgetNoPlans")}</p>}
            {plans.map((plan) => (
              <button
                key={plan.id}
                type="button"
                className={plan.id === selectedPlanId ? "is-selected" : ""}
                onClick={() => setSelectedPlanId(plan.id)}
              >
                <strong>{plan.name}</strong>
                <span>{plan.fiscal_year} · {plan.base_currency}</span>
                <small>{t(statusKey(plan.status))}</small>
              </button>
            ))}

            <form onSubmit={createPlan} className="budget-planning__form">
              <h3>{t("budgetNewPlan")}</h3>
              <label>{t("budgetPlanName")}<input required value={planForm.name} onChange={(event) => setPlanForm({ ...planForm, name: event.target.value })} /></label>
              <label>{t("budgetFiscalYear")}<input required type="number" min="2000" max="2200" value={planForm.fiscal_year} onChange={(event) => setPlanForm({ ...planForm, fiscal_year: event.target.value })} /></label>
              <label>{t("budgetCurrency")}<select value={planForm.base_currency} onChange={(event) => setPlanForm({ ...planForm, base_currency: event.target.value })}><option value="TRY">TRY</option><option value="EUR">EUR</option><option value="USD">USD</option><option value="GBP">GBP</option></select></label>
              <button type="submit" disabled={saving}>{t("create")}</button>
            </form>
          </aside>

          <div className="budget-planning__main">
            {!selectedPlan && <div role="status">{t("budgetSelectPlan")}</div>}
            {selectedPlan && (
              <>
                <section className="budget-planning__plan-summary">
                  <div>
                    <h2>{selectedPlan.name}</h2>
                    <p>{selectedPlan.fiscal_year} · {selectedPlan.base_currency} · {t(statusKey(selectedPlan.status))}</p>
                  </div>
                  {isDraft && (
                    <div>
                      <button type="button" onClick={activatePlan} disabled={!canActivate || saving}>{t("budgetActivatePlan")}</button>
                      <p>{t("budgetMakerChecker")}</p>
                    </div>
                  )}
                </section>

                {selectedPlan.status === "ACTIVE" && (
                  <section className="budget-planning__evidence" aria-labelledby="budget-activation-evidence">
                    <h3 id="budget-activation-evidence">{t("budgetActivationEvidence")}</h3>
                    <dl>
                      <div><dt>{t("budgetSnapshotHash")}</dt><dd><code>{selectedPlan.planning_fingerprint}</code></dd></div>
                      <div><dt>{t("budgetSnapshotProvenance")}</dt><dd>{selectedPlan.activation_snapshot_attested ? t("budgetActivationAttested") : t("budgetLegacyReconstruction")}</dd></div>
                    </dl>
                  </section>
                )}

                <div className="budget-planning__columns">
                  <section>
                    <h3>{t("budgetPeriods")}</h3>
                    <ul className="budget-planning__list">
                      {periods.map((period) => <li key={period.id}><strong>{period.code}</strong><span>{formatDate(safeDate(period.starts_on))} — {formatDate(safeDate(period.ends_on))}</span><small>{t(statusKey(period.status))}</small></li>)}
                    </ul>
                    {isDraft && <form onSubmit={createPeriod} className="budget-planning__form compact"><label>{t("budgetPeriodCode")}<input required value={periodForm.code} onChange={(event) => setPeriodForm({ ...periodForm, code: event.target.value })} /></label><label>{t("budgetStartDate")}<input required type="date" value={periodForm.starts_on} onChange={(event) => setPeriodForm({ ...periodForm, starts_on: event.target.value })} /></label><label>{t("budgetEndDate")}<input required type="date" value={periodForm.ends_on} onChange={(event) => setPeriodForm({ ...periodForm, ends_on: event.target.value })} /></label><button type="submit" disabled={saving}>{t("budgetNewPeriod")}</button></form>}
                  </section>

                  <section>
                    <h3>{t("budgetCostCenters")}</h3>
                    <ul className="budget-planning__list">
                      {costCenters.map((center) => <li key={center.id}><strong>{center.code}</strong><span>{center.name}</span><small>{center.store_code || "—"}</small></li>)}
                    </ul>
                    <form onSubmit={createCostCenter} className="budget-planning__form compact"><label>{t("budgetCode")}<input required value={centerForm.code} onChange={(event) => setCenterForm({ ...centerForm, code: event.target.value })} /></label><label>{t("budgetName")}<input required value={centerForm.name} onChange={(event) => setCenterForm({ ...centerForm, name: event.target.value })} /></label><label>{t("budgetStore")}<input value={centerForm.store_code} onChange={(event) => setCenterForm({ ...centerForm, store_code: event.target.value })} /></label><button type="submit" disabled={saving}>{t("budgetNewCostCenter")}</button></form>
                  </section>
                </div>

                <section>
                  <h3>{t("budgetLines")}</h3>
                  <div className="budget-planning__table-wrap">
                    <table>
                      <thead><tr><th>{t("budgetPeriodCode")}</th><th>{t("budgetCostCenters")}</th><th>{t("budgetCategory")}</th><th>{t("budgetAmount")}</th><th>{t("budgetForecast")}</th></tr></thead>
                      <tbody>{lines.map((line) => <tr key={line.id}><td>{line.fiscal_period_code}</td><td>{line.cost_center_code}</td><td>{line.category}</td><td>{formatCurrency(line.budget_base_amount, selectedPlan.base_currency)}</td><td>{line.latest_forecast_base_amount == null ? "—" : formatCurrency(line.latest_forecast_base_amount, selectedPlan.base_currency)}</td></tr>)}</tbody>
                    </table>
                  </div>

                  {isDraft && <form onSubmit={createLine} className="budget-planning__inline-form"><label>{t("budgetSelectPeriod")}<select required value={lineForm.fiscal_period_id} onChange={(event) => setLineForm({ ...lineForm, fiscal_period_id: event.target.value })}><option value="">{t("budgetSelectPeriod")}</option>{periods.map((period) => <option key={period.id} value={period.id}>{period.code}</option>)}</select></label><label>{t("budgetSelectCostCenter")}<select required value={lineForm.cost_center_id} onChange={(event) => setLineForm({ ...lineForm, cost_center_id: event.target.value })}><option value="">{t("budgetSelectCostCenter")}</option>{costCenters.map((center) => <option key={center.id} value={center.id}>{center.code} · {center.name}</option>)}</select></label><label>{t("budgetCategory")}<input required value={lineForm.category} onChange={(event) => setLineForm({ ...lineForm, category: event.target.value })} /></label><label>{t("budgetAmount")}<input required inputMode="decimal" value={lineForm.budget_base_amount} onChange={(event) => setLineForm({ ...lineForm, budget_base_amount: event.target.value })} /></label><button type="submit" disabled={saving}>{t("budgetNewLine")}</button></form>}
                </section>

                {selectedPlan.status === "ACTIVE" && lines.length > 0 && (
                  <section>
                    <h3>{t("budgetForecast")}</h3>
                    <form onSubmit={createForecast} className="budget-planning__inline-form">
                      <label>{t("budgetSelectLine")}<select required value={forecastForm.budget_line_id} onChange={(event) => setForecastForm({ ...forecastForm, budget_line_id: event.target.value })}><option value="">{t("budgetSelectLine")}</option>{lines.map((line) => <option key={line.id} value={line.id}>{line.fiscal_period_code} · {line.cost_center_code} · {line.category}</option>)}</select></label>
                      <label>{t("budgetForecastAmount")}<input required inputMode="decimal" value={forecastForm.forecast_base_amount} onChange={(event) => setForecastForm({ ...forecastForm, forecast_base_amount: event.target.value })} /></label>
                      <label>{t("budgetAsOf")}<input required type="date" value={forecastForm.as_of} onChange={(event) => setForecastForm({ ...forecastForm, as_of: event.target.value })} /></label>
                      <button type="submit" disabled={saving}>{t("budgetCreateForecast")}</button>
                    </form>
                  </section>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
