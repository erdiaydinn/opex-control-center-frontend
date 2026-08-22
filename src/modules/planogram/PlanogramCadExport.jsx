import React, { useCallback, useMemo, useState } from "react";
import { Download, FileCode2, ShieldAlert } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramCad } from "../../platform/i18n/planogramCadMessages.js";
import "./planogram-cad-export.css";

function safeFileStem(candidate) {
  const storeCode = String(candidate?.store_dna?.store_code || candidate?.layout?.store_code || "preview")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return `eay-planogram-${storeCode || "preview"}`;
}

function saveTextFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

function assertCadAuthorityBoundary(response, includeDxf) {
  const drawing = response?.drawing;
  if (
    response?.preview_only !== true ||
    response?.production_release_allowed !== false ||
    response?.installation_approval_allowed !== false ||
    !drawing ||
    drawing.available !== true ||
    drawing.preview_only !== true ||
    drawing.production_authority !== false ||
    drawing.production_evidence !== false ||
    drawing.installation_approved !== false ||
    typeof drawing.svg !== "string" ||
    !drawing.svg.startsWith("<svg") ||
    (includeDxf && (drawing.dxf_included !== true || typeof drawing.dxf !== "string"))
  ) {
    throw new Error("cad_authority_boundary_invalid");
  }
  return drawing;
}

export default function PlanogramCadExport({ candidate, optimizerMeta, locale, canExport }) {
  const [runningFormat, setRunningFormat] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const t = useMemo(() => (key, params) => translatePlanogramCad(locale, key, params), [locale]);
  const available = Boolean(candidate && optimizerMeta);

  const exportDrawing = useCallback(async (format) => {
    if (!available || !canExport || runningFormat) return;
    const includeDxf = format === "dxf";
    setRunningFormat(format);
    setError("");
    setSuccess("");
    try {
      const response = await apiPost(
        `/v1/planogram/cad-preview?include_dxf=${includeDxf ? "true" : "false"}`,
        candidate
      );
      const drawing = assertCadAuthorityBoundary(response, includeDxf);
      const stem = safeFileStem(candidate);
      if (includeDxf) {
        saveTextFile(drawing.dxf, `${stem}.dxf`, "application/dxf;charset=utf-8");
      } else {
        saveTextFile(drawing.svg, `${stem}.svg`, "image/svg+xml;charset=utf-8");
      }
      setSuccess(t("ready", { fingerprint: String(drawing.fingerprint || "").slice(0, 12) || "—" }));
    } catch {
      setError(t("error"));
    } finally {
      setRunningFormat("");
    }
  }, [available, canExport, candidate, runningFormat, t]);

  if (!available) return null;

  return (
    <section className="eay-planogram-cad" data-preview-only="true">
      <header>
        <div><FileCode2 size={20} aria-hidden="true" /><div><strong>{t("title")}</strong><span>{t("hint")}</span></div></div>
        <span className="eay-planogram-cad-badge"><ShieldAlert size={15} aria-hidden="true" />{t("review")}</span>
      </header>
      <p>{t("authority")}</p>
      <div className="eay-planogram-cad-actions">
        <button
          type="button"
          onClick={() => exportDrawing("svg")}
          disabled={!canExport || Boolean(runningFormat)}
        >
          <Download size={16} aria-hidden="true" />
          {runningFormat === "svg" ? t("preparing") : t("svg")}
        </button>
        <button
          type="button"
          onClick={() => exportDrawing("dxf")}
          disabled={!canExport || Boolean(runningFormat)}
        >
          <Download size={16} aria-hidden="true" />
          {runningFormat === "dxf" ? t("preparing") : t("dxf")}
        </button>
      </div>
      {!canExport ? <p className="eay-planogram-cad-note">{t("permission")}</p> : null}
      {error ? <p className="eay-planogram-cad-error" role="alert">{error}</p> : null}
      {success ? <p className="eay-planogram-cad-success" role="status">{success}</p> : null}
    </section>
  );
}

export { assertCadAuthorityBoundary, safeFileStem };
