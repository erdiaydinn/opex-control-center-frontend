import React, { useMemo } from "react";
import { CircleAlert } from "lucide-react";

import { translatePlanogramScanUncertainty } from "../../platform/i18n/planogramScanUncertaintyMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import {
  defaultPlanogramUncertaintyType,
  PLANOGRAM_SCAN_UNCERTAINTY_TYPES,
} from "./planogramScanUncertainty.js";
import "./planogram-scan-uncertainty.css";

export function PlanogramScanUncertaintyLayer({ regions, projection, choices, locale }) {
  const u = (key) => translatePlanogramScanUncertainty(locale, key);
  if (!projection || !Array.isArray(regions) || !regions.length) return null;
  return regions.map((region) => {
    const choice = choices?.[region.element_id] || {};
    const decision = String(choice.decision || "pending");
    const sourceType = String(region.source_element_type || "unknown");
    const statusKey = decision === "confirm" ? "confirm" : decision === "reject" ? "reject" : "pending";
    return (
      <polygon
        key={`uncertain-${region.element_id}`}
        points={svgPointString(rotatedRectSvgPoints({
          centerXM: region.center_x_m,
          centerYM: region.center_y_m,
          widthM: region.width_m,
          depthM: region.depth_m,
          rotationDeg: region.rotation_deg,
        }, projection))}
        className={`eay-scan-uncertainty-shape eay-scan-uncertainty-shape--${decision}`}
        data-uncertainty-element-id={region.element_id}
        data-uncertainty-decision={decision}
      >
        <title>{`${u(statusKey)} · ${region.element_id} · ${u(sourceType)} · ${Math.round(Number(region.confidence || 0) * 100)}%`}</title>
      </polygon>
    );
  });
}

export default function PlanogramScanUncertaintyReview({
  regions,
  choices,
  onChange,
  locale,
  formatNumber,
}) {
  const u = useMemo(
    () => (key) => translatePlanogramScanUncertainty(locale, key),
    [locale]
  );
  const numberFormat = typeof formatNumber === "function"
    ? formatNumber
    : (value) => new Intl.NumberFormat(locale || "en").format(Number(value || 0));
  if (!Array.isArray(regions) || !regions.length) return null;
  const unresolved = regions.filter((region) => {
    const decision = String(choices?.[region.element_id]?.decision || "");
    if (decision === "reject") return false;
    if (decision !== "confirm") return true;
    const type = String(
      choices?.[region.element_id]?.classified_type || defaultPlanogramUncertaintyType(region)
    );
    return !PLANOGRAM_SCAN_UNCERTAINTY_TYPES.includes(type);
  }).length;

  return (
    <section className="eay-scan-uncertainty-review" aria-label={u("title")}>
      <header>
        <div><CircleAlert size={18} aria-hidden="true" /><div><strong>{u("title")}</strong><p>{u("subtitle")}</p></div></div>
        <span>{u("unresolved")}: {numberFormat(unresolved)}</span>
      </header>
      <div className="eay-scan-uncertainty-grid">
        {regions.map((region) => {
          const current = choices?.[region.element_id] || {};
          const decision = String(current.decision || "");
          const sourceType = String(region.source_element_type || "unknown");
          const defaultType = defaultPlanogramUncertaintyType(region);
          const selectedType = String(current.classified_type || defaultType || "");
          const reasonKey = region.reason === "unknown_type_requires_classification"
            ? "reasonUnknown"
            : "reasonLow";
          return (
            <article key={region.element_id} data-decision={decision || "pending"}>
              <header><code>{region.element_id}</code><span>{u("confidence")}: {numberFormat(Number(region.confidence || 0) * 100)}%</span></header>
              <div className="eay-scan-uncertainty-meta">
                <span>{u("sourceType")}: {u(sourceType)}</span>
                <span>{u("required")}: {numberFormat(Number(region.required_confidence || 0) * 100)}%</span>
                <span>{u("reason")}: {u(reasonKey)}</span>
              </div>
              <label>
                <span>{u("decision")}</span>
                <select
                  value={decision}
                  onChange={(event) => {
                    const nextDecision = event.target.value;
                    onChange(region.element_id, {
                      decision: nextDecision,
                      classified_type: nextDecision === "confirm" ? selectedType : "",
                    });
                  }}
                >
                  <option value="">{u("selectDecision")}</option>
                  <option value="confirm">{u("confirm")}</option>
                  <option value="reject">{u("reject")}</option>
                </select>
              </label>
              {decision === "confirm" ? (
                <label>
                  <span>{u("type")}</span>
                  <select
                    value={selectedType}
                    onChange={(event) => onChange(region.element_id, { classified_type: event.target.value })}
                  >
                    <option value="">{u("selectType")}</option>
                    {PLANOGRAM_SCAN_UNCERTAINTY_TYPES.map((type) => <option key={type} value={type}>{u(type)}</option>)}
                  </select>
                  {!selectedType ? <small>{u("typeRequired")}</small> : null}
                </label>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
