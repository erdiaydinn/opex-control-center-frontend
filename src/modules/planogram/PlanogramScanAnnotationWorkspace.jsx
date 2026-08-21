import React, { useCallback, useMemo, useRef, useState } from "react";
import { Crosshair, Ruler, ShieldCheck, Trash2 } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramAuthoring } from "../../platform/i18n/planogramAuthoringMessages.js";
import { translatePlanogramScanAnnotation } from "../../platform/i18n/planogramScanAnnotationMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import PlanogramFixtureBindingPanel from "./PlanogramFixtureBindingPanel.jsx";
import {
  annotationToolDefaults,
  PLANOGRAM_SCAN_ANNOTATION_TOOLS,
  safePlanogramScanAnnotationPreview,
} from "./planogramScanAnnotation.js";
import PlanogramScannedDigitalTwin from "./PlanogramScannedDigitalTwin.jsx";
import "./planogram-scan-annotation.css";

const SVG_WIDTH = 920;
const SVG_HEIGHT = 520;
const KEYBOARD_STEP_M = 0.25;

function projectionFor(architecture) {
  const padding = 38;
  const scale = Math.min(
    (SVG_WIDTH - padding * 2) / architecture.floor_width_m,
    (SVG_HEIGHT - padding * 2) / architecture.floor_depth_m
  );
  return {
    offsetX: (SVG_WIDTH - architecture.floor_width_m * scale) / 2,
    offsetY: (SVG_HEIGHT - architecture.floor_depth_m * scale) / 2,
    floorDepthM: architecture.floor_depth_m,
    scale,
  };
}

function pointFromClick(event, projection, architecture) {
  const rect = event.currentTarget.getBoundingClientRect();
  const svgX = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * SVG_WIDTH;
  const svgY = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * SVG_HEIGHT;
  const xM = (svgX - projection.offsetX) / projection.scale;
  const yM = architecture.floor_depth_m - (svgY - projection.offsetY) / projection.scale;
  if (xM < 0 || yM < 0 || xM > architecture.floor_width_m || yM > architecture.floor_depth_m) {
    return null;
  }
  return [xM, yM];
}

function clampPoint(point, architecture) {
  return [
    Math.max(0, Math.min(point[0], architecture.floor_width_m)),
    Math.max(0, Math.min(point[1], architecture.floor_depth_m)),
  ];
}

export default function PlanogramScanAnnotationWorkspace({
  scanBundle,
  scanResponse,
  locale,
  formatNumber,
  canCreate,
  optimizationCandidate,
  onOpenEditableModel,
}) {
  const t = useMemo(() => (key) => translatePlanogramScanAnnotation(locale, key), [locale]);
  const authoringT = useMemo(() => (key) => translatePlanogramAuthoring(locale, key), [locale]);
  const scan = scanResponse?.store_scan || null;
  const architecture = scan?.architecture_v2_preview || null;
  const openings = useMemo(
    () => (architecture?.elements || []).filter((row) => row.element_type === "opening"),
    [architecture]
  );
  const sequenceRef = useRef(0);
  const [classifications, setClassifications] = useState({});
  const [tool, setTool] = useState("picker_entry");
  const [widthM, setWidthM] = useState(annotationToolDefaults("picker_entry").widthM);
  const [depthM, setDepthM] = useState(annotationToolDefaults("picker_entry").depthM);
  const [rotationDeg, setRotationDeg] = useState(0);
  const [annotations, setAnnotations] = useState([]);
  const [keyboardPoint, setKeyboardPoint] = useState(null);
  const [reviewNote, setReviewNote] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(null);

  const projection = useMemo(
    () => (architecture ? projectionFor(architecture) : null),
    [architecture]
  );
  const classificationRows = useMemo(
    () => openings
      .map((opening) => {
        const value = classifications[opening.element_id];
        return value
          ? {
              element_id: opening.element_id,
              classified_type: value,
              clearance_m: value === "emergency_exit" ? 1 : 0,
            }
          : null;
      })
      .filter(Boolean),
    [classifications, openings]
  );

  const changeTool = useCallback((nextTool) => {
    setTool(nextTool);
    const defaults = annotationToolDefaults(nextTool);
    setWidthM(defaults.widthM);
    setDepthM(defaults.depthM);
  }, []);

  const addAtPoint = useCallback((point) => {
    if (!architecture || !canCreate || !point) return;
    const bounded = clampPoint(point, architecture);
    const boundedWidth = Math.max(0.05, Math.min(Number(widthM) || 0.05, architecture.floor_width_m));
    const boundedDepth = Math.max(0.05, Math.min(Number(depthM) || 0.05, architecture.floor_depth_m));
    sequenceRef.current += 1;
    const next = {
      element_id: `human-${tool}-${sequenceRef.current}`,
      element_type: tool,
      center_x_m: Number(bounded[0].toFixed(3)),
      center_y_m: Number(bounded[1].toFixed(3)),
      width_m: Number(boundedWidth.toFixed(3)),
      depth_m: Number(boundedDepth.toFixed(3)),
      rotation_deg: Number(rotationDeg) || 0,
      clearance_m: tool === "emergency_exit" ? 1 : 0,
    };
    setReviewed(null);
    setError("");
    setAnnotations((current) => {
      const withoutUnique = tool === "picker_entry"
        ? current.filter((row) => row.element_type !== "picker_entry")
        : current;
      return [...withoutUnique, next];
    });
  }, [architecture, canCreate, depthM, rotationDeg, tool, widthM]);

  const placeAnnotation = useCallback((event) => {
    if (!architecture || !projection || !canCreate) return;
    const point = pointFromClick(event, projection, architecture);
    if (!point) return;
    setKeyboardPoint(point);
    addAtPoint(point);
  }, [addAtPoint, architecture, canCreate, projection]);

  const handleMapKeyDown = useCallback((event) => {
    if (!architecture || !canCreate) return;
    const current = keyboardPoint || [architecture.floor_width_m / 2, architecture.floor_depth_m / 2];
    let next = current;
    if (event.key === "ArrowLeft") next = [current[0] - KEYBOARD_STEP_M, current[1]];
    else if (event.key === "ArrowRight") next = [current[0] + KEYBOARD_STEP_M, current[1]];
    else if (event.key === "ArrowUp") next = [current[0], current[1] + KEYBOARD_STEP_M];
    else if (event.key === "ArrowDown") next = [current[0], current[1] - KEYBOARD_STEP_M];
    else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      addAtPoint(current);
      return;
    } else return;
    event.preventDefault();
    setKeyboardPoint(clampPoint(next, architecture));
  }, [addAtPoint, architecture, canCreate, keyboardPoint]);

  const runReview = useCallback(async () => {
    if (!scanBundle || !scan?.scan_fingerprint || running || !canCreate) return;
    setRunning(true);
    setReviewed(null);
    setError("");
    try {
      const raw = await apiPost("/v1/planogram/store-scan/annotate-preview", {
        scan: scanBundle,
        expected_scan_fingerprint: scan.scan_fingerprint,
        classifications: classificationRows,
        operational_elements: annotations,
        review_note: reviewNote.trim() || null,
      });
      const safe = safePlanogramScanAnnotationPreview(raw, scan.scan_fingerprint);
      if (!safe) throw new Error("scan_annotation_truth_boundary_failed");
      setReviewed(safe);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [annotations, canCreate, classificationRows, reviewNote, running, scan?.scan_fingerprint, scanBundle, t]);

  if (!scanBundle || !scan || !architecture || !projection) return null;
  const reviewedResult = reviewed?.result || null;
  const keyboardCircle = keyboardPoint
    ? {
        cx: projection.offsetX + keyboardPoint[0] * projection.scale,
        cy: projection.offsetY + (architecture.floor_depth_m - keyboardPoint[1]) * projection.scale,
      }
    : null;

  return (
    <section className="eay-scan-annotation">
      <header>
        <div><Crosshair size={20} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <span>{t("authority")}</span>
      </header>

      {openings.length ? (
        <div className="eay-scan-opening-list">
          {openings.map((opening) => (
            <label key={opening.element_id}>
              <span>{t("opening")} · <code>{opening.element_id}</code></span>
              <select
                value={classifications[opening.element_id] || ""}
                onChange={(event) => {
                  setClassifications((current) => ({ ...current, [opening.element_id]: event.target.value }));
                  setReviewed(null);
                }}
              >
                <option value="">{t("unclassified")}</option>
                <option value="door">{t("door")}</option>
                <option value="emergency_exit">{t("emergency_exit")}</option>
              </select>
            </label>
          ))}
        </div>
      ) : null}

      <div className="eay-scan-annotation-tools">
        <label><span>{t("tool")}</span><select value={tool} onChange={(event) => changeTool(event.target.value)}>{PLANOGRAM_SCAN_ANNOTATION_TOOLS.map((row) => <option key={row} value={row}>{t(row)}</option>)}</select></label>
        <label><span>{t("width")}</span><input type="number" min="0.05" max="500" step="0.05" value={widthM} onChange={(event) => setWidthM(event.target.value)} /></label>
        <label><span>{t("depth")}</span><input type="number" min="0.05" max="500" step="0.05" value={depthM} onChange={(event) => setDepthM(event.target.value)} /></label>
        <label><span>{t("rotation")}</span><input type="number" min="-360" max="360" step="1" value={rotationDeg} onChange={(event) => setRotationDeg(event.target.value)} /></label>
      </div>
      <p className="eay-scan-annotation-hint">{t("placeHint")}</p>

      <svg
        className="eay-scan-annotation-map"
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        role="button"
        tabIndex={0}
        aria-label={t("placeHint")}
        onClick={placeAnnotation}
        onKeyDown={handleMapKeyDown}
      >
        <rect x={projection.offsetX} y={projection.offsetY} width={architecture.floor_width_m * projection.scale} height={architecture.floor_depth_m * projection.scale} className="eay-scan-annotation-floor" />
        {(architecture.elements || []).map((element) => (
          <polygon
            key={element.element_id}
            points={svgPointString(rotatedRectSvgPoints({ centerXM: element.center_x_m, centerYM: element.center_y_m, widthM: element.width_m, depthM: element.depth_m, rotationDeg: element.rotation_deg }, projection))}
            className={`eay-scan-annotation-existing eay-scan-annotation-existing--${element.element_type}`}
          />
        ))}
        {annotations.map((element) => (
          <polygon
            key={element.element_id}
            points={svgPointString(rotatedRectSvgPoints({ centerXM: element.center_x_m, centerYM: element.center_y_m, widthM: element.width_m, depthM: element.depth_m, rotationDeg: element.rotation_deg }, projection))}
            className={`eay-scan-annotation-human eay-scan-annotation-human--${element.element_type}`}
          ><title>{t(element.element_type)}</title></polygon>
        ))}
        {keyboardCircle ? <circle cx={keyboardCircle.cx} cy={keyboardCircle.cy} r="7" className="eay-scan-annotation-cursor" /> : null}
      </svg>

      <div className="eay-scan-annotation-list">
        <strong>{t("annotations")}</strong>
        {annotations.map((row) => (
          <div key={row.element_id}>
            <span>{t(row.element_type)} · {row.center_x_m} / {row.center_y_m} m</span>
            <button type="button" onClick={() => { setAnnotations((current) => current.filter((item) => item.element_id !== row.element_id)); setReviewed(null); }}><Trash2 size={15} aria-hidden="true" />{t("remove")}</button>
          </div>
        ))}
      </div>

      <label className="eay-scan-annotation-note"><span>{t("reviewNote")}</span><textarea maxLength={1000} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} /></label>
      <button type="button" className="eay-scan-annotation-run" onClick={runReview} disabled={!canCreate || running}>{running ? t("running") : t("run")}</button>
      {!canCreate ? <p>{t("permissionRequired")}</p> : null}
      {error ? <p className="eay-scan-annotation-error" role="alert">{error}</p> : null}

      {reviewedResult ? (
        <div className="eay-scan-annotation-result">
          <div><ShieldCheck size={18} aria-hidden="true" /><strong>{reviewedResult.reviewed_draft_ready ? t("ready") : t("blocked")}</strong></div>
          <span>{t("authority")}</span>
          <div><span>{t("fingerprint")}</span><code>{reviewedResult.reviewed_draft_fingerprint}</code></div>
          {reviewedResult.blockers?.length ? <ul>{reviewedResult.blockers.map((row) => <li key={row}><code>{row}</code></li>)}</ul> : null}
        </div>
      ) : null}

      {reviewedResult?.reviewed_draft_ready && typeof onOpenEditableModel === "function" ? (
        <button
          type="button"
          className="eay-scan-annotation-run"
          onClick={() => onOpenEditableModel(reviewedResult)}
        >
          <Ruler size={16} aria-hidden="true" />{authoringT("title")}
        </button>
      ) : null}

      {reviewedResult?.reviewed_draft_ready ? (
        <PlanogramScannedDigitalTwin reviewedResult={reviewedResult} scan={scan} locale={locale} formatNumber={formatNumber} />
      ) : null}

      {reviewedResult?.reviewed_draft_ready ? (
        <PlanogramFixtureBindingPanel
          scanBundle={scanBundle}
          scanResponse={scanResponse}
          classifications={classificationRows}
          operationalElements={annotations}
          reviewNote={reviewNote.trim()}
          locale={locale}
          formatNumber={formatNumber}
          canCreate={canCreate}
          optimizationCandidate={optimizationCandidate}
        />
      ) : null}
    </section>
  );
}
