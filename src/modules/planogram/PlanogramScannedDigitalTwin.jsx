import React, { useMemo, useState } from "react";
import { Box, ScanSearch } from "lucide-react";

import { translatePlanogramScannedTwin } from "../../platform/i18n/planogramScannedTwinMessages.js";
import PlanogramTwinSceneRenderer from "./PlanogramTwinSceneRenderer.jsx";
import { PLANOGRAM_THREE_ASSET_RUNTIME } from "./planogramThreeAssetRuntime.js";
import { buildPlanogramUnifiedTwinScene } from "./planogramUnifiedTwinScene.js";
import "./planogram-scanned-twin.css";

const OPERATIONAL_TYPES = new Set([
  "picker_entry",
  "picker_exit",
  "inbound",
  "dispatch",
  "no_go",
  "technical",
]);

export default function PlanogramScannedDigitalTwin({ reviewedResult, scan, locale, formatNumber }) {
  const t = useMemo(() => (key) => translatePlanogramScannedTwin(locale, key), [locale]);
  const numberFormat = useMemo(() => {
    if (typeof formatNumber === "function") return formatNumber;
    const formatter = new Intl.NumberFormat(locale || "en");
    return (value) => formatter.format(Number(value || 0));
  }, [formatNumber, locale]);
  const [preset, setPreset] = useState("overview");
  const architecture = reviewedResult?.reviewed_store_dna_v2_preview?.architecture || null;
  const recognizedFixtures = scan?.recognized_fixtures || [];
  const sceneModel = useMemo(
    () => buildPlanogramUnifiedTwinScene({
      reviewedArchitecture: architecture,
      recognizedFixtures,
    }),
    [architecture, recognizedFixtures]
  );

  if (!architecture?.elements?.length || !sceneModel) return null;
  const operationalCount = architecture.elements.filter((row) => OPERATIONAL_TYPES.has(row.element_type)).length;
  const measuredCount = architecture.elements.length - operationalCount;
  const fixtureCount = recognizedFixtures.length;

  return (
    <section
      className="eay-scanned-twin"
      data-scene-contract={sceneModel.contract}
      data-geometry-authority={sceneModel.geometryAuthority}
      data-asset-runtime-contract={PLANOGRAM_THREE_ASSET_RUNTIME.contract}
    >
      <header>
        <div><ScanSearch size={21} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <span>{t("previewOnly")}</span>
      </header>
      <div className="eay-scanned-twin-metrics">
        <div><Box size={16} aria-hidden="true" /><span>{t("measuredElements")}</span><strong>{numberFormat(measuredCount)}</strong></div>
        <div><span>{t("operationalZones")}</span><strong>{numberFormat(operationalCount)}</strong></div>
        <div><span>{t("fixtures")}</span><strong>{numberFormat(fixtureCount)}</strong></div>
      </div>
      <div className="eay-scanned-twin-presets">
        <button type="button" aria-pressed={preset === "overview"} onClick={() => setPreset("overview")}>{t("overview")}</button>
        <button type="button" aria-pressed={preset === "picker"} onClick={() => setPreset("picker")}>{t("pickerView")}</button>
      </div>
      <PlanogramTwinSceneRenderer
        sceneModel={sceneModel}
        preset={preset}
        ariaLabel={t("title")}
        loadingLabel={t("loading")}
        errorLabel={t("error")}
      />
      <p className="eay-scanned-twin-boundary">{t("boundary")}</p>
    </section>
  );
}
