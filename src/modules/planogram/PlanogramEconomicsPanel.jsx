import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileSpreadsheet, ShieldCheck, TrendingUp } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramEconomics } from "../../platform/i18n/planogramEconomicsMessages.js";
import {
  normalizePlanogramEconomicsAssumptions,
  safePlanogramCandidateEconomicsPreview,
  safePlanogramEconomicsPreview,
} from "./planogramEconomicsAssumptions.js";
import "./planogram-economics.css";

const MAX_ECONOMICS_FILE_BYTES = 2 * 1024 * 1024;

function moneyFormatter(locale, currency) {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      currencyDisplay: "code",
      maximumFractionDigits: 2,
    });
  } catch {
    return new Intl.NumberFormat("en", { maximumFractionDigits: 2 });
  }
}

export default function PlanogramEconomicsPanel({
  candidate,
  locale,
  formatNumber,
  canCreate,
  canApprove,
  layoutFingerprint = "",
}) {
  const inputRef = useRef(null);
  const t = useMemo(
    () => (key, params) => translatePlanogramEconomics(locale, key, params),
    [locale]
  );
  const [assumptions, setAssumptions] = useState(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState(null);

  const fingerprint = String(layoutFingerprint || "").trim().toLowerCase();
  const fingerprintReady = !fingerprint || /^[0-9a-f]{64}$/.test(fingerprint);
  const basketCount = candidate?.order_baskets?.length || 0;
  const permissionReady = Boolean(canCreate && canApprove);
  const canRun = Boolean(
    candidate
    && assumptions
    && basketCount > 0
    && permissionReady
    && fingerprintReady
    && !running
  );
  const economics = response?.result?.economics || null;
  const scenarios = Array.isArray(economics?.scenarios) ? economics.scenarios : [];
  const sourceManifest = economics?.source_manifest || {};
  const formatMoney = useMemo(
    () => (value) => moneyFormatter(locale, assumptions?.currency || "EUR").format(Number(value || 0)),
    [assumptions?.currency, locale]
  );

  useEffect(() => {
    setResponse(null);
    setError("");
  }, [fingerprint]);

  const readAssumptions = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setAssumptions(null);
    setFileName("");
    setResponse(null);
    setError("");
    if (!file) return;
    if (file.size > MAX_ECONOMICS_FILE_BYTES) {
      setError(t("invalidAssumptions"));
      event.target.value = "";
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      const normalized = normalizePlanogramEconomicsAssumptions(parsed);
      if (!normalized) throw new Error("invalid_economics_assumptions");
      setAssumptions(normalized);
      setFileName(file.name);
    } catch {
      setError(t("invalidAssumptions"));
      event.target.value = "";
    }
  }, [t]);

  const runEconomics = useCallback(async () => {
    if (!canRun) return;
    setRunning(true);
    setResponse(null);
    setError("");
    try {
      const endpoint = fingerprint
        ? "/v1/planogram/physical-layout-candidate-economics-preview"
        : "/v1/planogram/physical-layout-economics-preview";
      const payload = {
        ...candidate,
        ...(fingerprint ? { layout_fingerprint: fingerprint } : {}),
        economics: assumptions,
      };
      const raw = await apiPost(endpoint, payload);
      const safe = fingerprint
        ? safePlanogramCandidateEconomicsPreview(raw, fingerprint)
        : safePlanogramEconomicsPreview(raw);
      if (!safe) throw new Error("economics_authority_boundary_failed");
      setResponse(safe);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [assumptions, canRun, candidate, fingerprint, t]);

  return (
    <section className="eay-planogram-economics" aria-busy={running ? "true" : "false"}>
      <header>
        <div>
          <TrendingUp size={20} aria-hidden="true" />
          <div>
            <h3>{t("title")}</h3>
            <p>{t("subtitle")}</p>
          </div>
        </div>
        <span>{t("previewOnly")}</span>
      </header>

      <div className="eay-planogram-economics-controls">
        <label>
          <FileSpreadsheet size={17} aria-hidden="true" />
          <span>{t("chooseAssumptions")}</span>
          <input
            ref={inputRef}
            type="file"
            accept="application/json,.json"
            onChange={readAssumptions}
          />
        </label>
        <div role="status" aria-live="polite">
          {assumptions
            ? t("assumptionsLoaded", { name: fileName, currency: assumptions.currency })
            : t("noAssumptions")}
        </div>
        <button type="button" onClick={runEconomics} disabled={!canRun}>
          {running ? t("running") : t("run")}
        </button>
      </div>

      {!permissionReady ? <p className="eay-planogram-economics-note">{t("permissionRequired")}</p> : null}
      {!basketCount ? <p className="eay-planogram-economics-note">{t("basketsRequired")}</p> : null}
      {error ? <p className="eay-planogram-economics-error" role="alert">{error}</p> : null}

      {response ? (
        <div className="eay-planogram-economics-result">
          <div className="eay-planogram-economics-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div>
              <strong>{t("authorityBlocked")}</strong>
              <span>{t("sourceClaimsUnverified")}</span>
              <span>{t("boundary")}</span>
            </div>
          </div>

          {economics?.available && scenarios.length ? (
            <div className="eay-planogram-economics-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t("scenario")}</th>
                    <th>{t("annualValue")}</th>
                    <th>{t("capex")}</th>
                    <th>{t("netValue")}</th>
                    <th>{t("paybackDays")}</th>
                    <th>{t("roi")}</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.map((scenario) => (
                    <tr key={scenario.scenario}>
                      <th>{t(scenario.scenario)}</th>
                      <td>{formatMoney(scenario.annual_labor_value)}</td>
                      <td>{formatMoney(scenario.capex)}</td>
                      <td>{formatMoney(scenario.first_year_net_value)}</td>
                      <td>{scenario.payback_operating_days == null ? "—" : formatNumber(scenario.payback_operating_days)}</td>
                      <td>{scenario.first_year_roi_pct == null ? "—" : `${formatNumber(scenario.first_year_roi_pct)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="eay-planogram-economics-blockers">
              <strong>{t("unavailable")}</strong>
              {(economics?.blockers || []).map((blocker) => <code key={blocker}>{blocker}</code>)}
            </div>
          )}

          {economics?.available ? (
            <div className="eay-planogram-economics-provenance">
              <div>
                <strong>{t("sourceManifest")}</strong>
                <dl>
                  {Object.entries(sourceManifest).map(([key, value]) => (
                    <React.Fragment key={key}>
                      <dt><code>{key}</code></dt>
                      <dd><code>{Array.isArray(value) ? value.join(" · ") : String(value)}</code></dd>
                    </React.Fragment>
                  ))}
                </dl>
              </div>
              <div>
                <strong>{t("fingerprint")}</strong>
                <code>{economics.economics_fingerprint}</code>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
