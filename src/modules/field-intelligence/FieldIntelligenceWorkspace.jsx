import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  BellRing,
  Camera,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  MapPin,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ScanLine,
  Send,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { translateField } from "./fieldMessages.js";
import "./field-intelligence.css";

const FIELD_TYPES = [
  "text",
  "number",
  "select",
  "barcode",
  "qr",
  "photo",
  "lot",
  "batch",
  "expiry",
  "quantity",
  "measurement",
  "gps",
  "yes_no",
  "multi_row",
];

const TYPE_MESSAGE_KEYS = Object.freeze({
  text: "typeText",
  number: "typeNumber",
  select: "typeSelect",
  barcode: "typeBarcode",
  qr: "typeQr",
  photo: "typePhoto",
  lot: "typeLot",
  batch: "typeBatch",
  expiry: "typeExpiry",
  quantity: "typeQuantity",
  measurement: "typeMeasurement",
  gps: "typeGps",
  yes_no: "typeYesNo",
  multi_row: "typeMultiRow",
});

const ACTIONABLE_TARGET_STATUSES = new Set([
  "unseen",
  "seen",
  "started",
  "partial",
  "rework",
  "overdue",
]);

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "";
}

function initialField() {
  return {
    key: "",
    label: "",
    type: "text",
    required: false,
    optionsText: "",
  };
}

function initialMissionForm() {
  return {
    templateKey: "",
    title: "",
    instructions: "",
    priority: "normal",
    assignedAt: "",
    deadlineAt: "",
    activate: false,
    allActive: false,
    locationIds: [],
  };
}

function initialTemplateForm() {
  return {
    templateId: "",
    version: 1,
    name: "",
    status: "draft",
    fields: [initialField()],
  };
}

function onlineNow() {
  return typeof navigator === "undefined" ? true : navigator.onLine !== false;
}

function buildTemplatePayload(form, locale) {
  return {
    template_id: form.templateId.trim(),
    version: Number(form.version),
    name: { values: { [locale]: form.name.trim() } },
    status: form.status,
    schema: {
      fields: form.fields.map((field) => ({
        key: field.key.trim(),
        type: field.type,
        label: { values: { [locale]: field.label.trim() } },
        required: Boolean(field.required),
        options:
          field.type === "select"
            ? field.optionsText.split(",").map((value) => value.trim()).filter(Boolean)
            : [],
        config: field.type === "multi_row" ? { max_rows: 50 } : {},
      })),
    },
  };
}

function FieldState({ state, children, action }) {
  return (
    <section
      className="eay-field-state"
      role={state === "error" ? "alert" : "status"}
      aria-live={state === "error" ? "assertive" : "polite"}
      aria-atomic="true"
      aria-busy={state === "loading" ? "true" : undefined}
      data-eay-product-state={state}
    >
      <span>{children}</span>
      {action}
    </section>
  );
}

export default function FieldIntelligenceWorkspace() {
  const navigate = useNavigate();
  const { locale, t } = usePlatformPreferences();
  const { canFeature, canAction } = useAuth();
  const f = useMemo(() => (key, params) => translateField(locale, key, params), [locale]);

  const [online, setOnline] = useState(onlineNow);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [bootstrap, setBootstrap] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [selectedTab, setSelectedTab] = useState("command");
  const [selectedMissionId, setSelectedMissionId] = useState("");
  const [missionDetail, setMissionDetail] = useState(null);
  const [missionForm, setMissionForm] = useState(initialMissionForm);
  const [templateForm, setTemplateForm] = useState(initialTemplateForm);
  const [captureMissionId, setCaptureMissionId] = useState("");
  const [captureLocationId, setCaptureLocationId] = useState("");
  const [captureDetail, setCaptureDetail] = useState(null);
  const [captureValues, setCaptureValues] = useState({});
  const [reviewReasons, setReviewReasons] = useState({});

  const canBuildMission = canFeature("field_intelligence", "missionBuilder") && canAction("field_intelligence", "createMission");
  const canManageTemplates = canFeature("field_intelligence", "templates") && canAction("field_intelligence", "manageTemplates");
  const canCapture = canFeature("field_intelligence", "capture") && canAction("field_intelligence", "submitEvidence");
  const canReview = canFeature("field_intelligence", "evidenceReview") && canAction("field_intelligence", "reviewEvidence") && canAction("field_intelligence", "viewEvidence");
  const canAnalytics = canFeature("field_intelligence", "analytics");
  const canActivate = canAction("field_intelligence", "activateMission");
  const canCancel = canAction("field_intelligence", "cancelMission");
  const canRemind = canAction("field_intelligence", "sendReminder");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const fieldBootstrap = await apiGet("/v1/field/bootstrap");
      setBootstrap(fieldBootstrap);

      const requests = [];
      if (canAnalytics) requests.push(apiGet("/v1/field/analytics").then(setAnalytics));
      else setAnalytics(null);
      if (canReview) requests.push(apiGet("/v1/field/evidence?limit=100").then((result) => setEvidence(result?.items || [])));
      else setEvidence([]);
      await Promise.all(requests);
    } catch {
      setError(f("loadError"));
    } finally {
      setLoading(false);
    }
  }, [canAnalytics, canReview, f]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  const locations = bootstrap?.locations || [];
  const templates = bootstrap?.templates || [];
  const missions = bootstrap?.missions || [];
  const activeTemplates = templates.filter((item) => item.status === "active");
  const activeMissions = missions.filter((item) => item.status === "active");

  const tabs = useMemo(() => {
    const items = [
      ["command", "commandCenter"],
      ["missions", "missions"],
    ];
    if (canBuildMission) items.push(["builder", "missionBuilder"]);
    if (canManageTemplates) items.push(["templates", "templates"]);
    if (canCapture) items.push(["capture", "capture"]);
    if (canReview) items.push(["review", "evidenceReview"]);
    if (canAnalytics) items.push(["analytics", "analytics"]);
    return items;
  }, [canAnalytics, canBuildMission, canCapture, canManageTemplates, canReview]);

  useEffect(() => {
    if (!tabs.some(([key]) => key === selectedTab)) setSelectedTab("command");
  }, [selectedTab, tabs]);

  const clearActionState = () => {
    setActionMessage("");
    setActionError("");
  };

  const runMutation = async (operation, successMessage) => {
    clearActionState();
    if (!online) {
      setActionError(f("offline"));
      return null;
    }
    setBusy(true);
    try {
      const result = await operation();
      setActionMessage(successMessage);
      await load();
      return result;
    } catch (mutationError) {
      setActionError(mutationError?.message || f("permissionDenied"));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const loadMissionDetail = async (missionId) => {
    setSelectedMissionId(missionId);
    setMissionDetail(null);
    if (!missionId) return;
    clearActionState();
    try {
      setMissionDetail(await apiGet(`/v1/field/missions/${encodeURIComponent(missionId)}`));
    } catch (detailError) {
      setActionError(detailError?.message || f("loadError"));
    }
  };

  const createMission = async (event) => {
    event.preventDefault();
    const template = activeTemplates.find((item) => `${item.template_id}:${item.version}` === missionForm.templateKey);
    if (!template) {
      setActionError(f("noTemplates"));
      return;
    }
    const targetSelector = missionForm.allActive
      ? { all_active_locations: true }
      : { include_location_ids: missionForm.locationIds };
    const result = await runMutation(
      () => apiPost("/v1/field/missions", {
        template_id: template.template_id,
        template_version: template.version,
        title: { values: { [locale]: missionForm.title.trim() } },
        instructions: missionForm.instructions.trim()
          ? { values: { [locale]: missionForm.instructions.trim() } }
          : null,
        priority: missionForm.priority,
        target_selector: targetSelector,
        assigned_at: new Date(missionForm.assignedAt).toISOString(),
        deadline_at: new Date(missionForm.deadlineAt).toISOString(),
        activate: Boolean(missionForm.activate),
      }),
      f("missionCreated")
    );
    if (result) {
      setMissionForm(initialMissionForm());
      setSelectedMissionId(result.id || "");
      setMissionDetail(result.id ? await apiGet(`/v1/field/missions/${encodeURIComponent(result.id)}`) : null);
      setSelectedTab("missions");
    }
  };

  const saveTemplate = async (event) => {
    event.preventDefault();
    const result = await runMutation(
      () => apiPost("/v1/field/templates", buildTemplatePayload(templateForm, locale)),
      f("templateCreated")
    );
    if (result) setTemplateForm(initialTemplateForm());
  };

  const updateTemplateField = (index, patch) => {
    setTemplateForm((current) => ({
      ...current,
      fields: current.fields.map((field, fieldIndex) => fieldIndex === index ? { ...field, ...patch } : field),
    }));
  };

  const selectTarget = (locationId, selected) => {
    setMissionForm((current) => ({
      ...current,
      locationIds: selected
        ? [...new Set([...current.locationIds, locationId])]
        : current.locationIds.filter((item) => item !== locationId),
    }));
  };

  const loadCaptureMission = async (missionId) => {
    setCaptureMissionId(missionId);
    setCaptureLocationId("");
    setCaptureValues({});
    setCaptureDetail(null);
    if (!missionId) return;
    try {
      setCaptureDetail(await apiGet(`/v1/field/missions/${encodeURIComponent(missionId)}`));
    } catch (captureError) {
      setActionError(captureError?.message || f("loadError"));
    }
  };

  const captureTargets = (captureDetail?.targets || []).filter((target) => ACTIONABLE_TARGET_STATUSES.has(target.status));
  const captureFields = captureDetail?.template_schema?.fields || [];
  const requiredPhotoBlocked = captureFields.some((field) => field.type === "photo" && field.required);

  const setCaptureValue = (key, value) => {
    setCaptureValues((current) => ({ ...current, [key]: value }));
  };

  const captureGps = (fieldKey) => {
    clearActionState();
    if (!navigator.geolocation) {
      setActionError(f("loadError"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCaptureValue(fieldKey, {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_m: position.coords.accuracy,
        });
        setActionMessage(f("gpsObserved"));
      },
      () => setActionError(f("loadError")),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  };

  const submitCapture = async (event) => {
    event.preventDefault();
    if (!captureMissionId || !captureLocationId || requiredPhotoBlocked) return;
    const payload = Object.fromEntries(
      Object.entries(captureValues).filter(([, value]) => value !== "" && value !== undefined)
    );
    const submissionId = globalThis.crypto?.randomUUID?.();
    if (!submissionId) {
      setActionError(f("loadError"));
      return;
    }
    const result = await runMutation(
      () => apiPost(
        `/v1/field/missions/${encodeURIComponent(captureMissionId)}/targets/${encodeURIComponent(captureLocationId)}/evidence`,
        {
          client_submission_id: submissionId,
          payload,
          observed_at: new Date().toISOString(),
        }
      ),
      f("evidenceSubmitted")
    );
    if (result) {
      setCaptureValues({});
      await loadCaptureMission(captureMissionId);
    }
  };

  const reviewEvidence = async (item, decision) => {
    const reason = reviewReasons[item.id] || "";
    const result = await runMutation(
      () => apiPost(`/v1/field/evidence/${encodeURIComponent(item.id)}/review`, {
        decision,
        reason: decision === "accept" ? null : reason,
      }),
      f("review")
    );
    if (result) setReviewReasons((current) => ({ ...current, [item.id]: "" }));
  };

  const queueNotification = async (missionId, kind) => {
    const result = await runMutation(
      () => apiPost(`/v1/field/missions/${encodeURIComponent(missionId)}/notification-intents`, {
        kind,
        reason_code: "manual_manager_followup",
        location_ids: [],
      }),
      f("queuedNotSent")
    );
    if (result) setActionMessage(f("queuedNotSent"));
  };

  const renderCaptureField = (field) => {
    const value = captureValues[field.key];
    const label = localized(field.label, locale) || field.key;
    const common = {
      id: `field-capture-${field.key}`,
      name: field.key,
      required: Boolean(field.required),
      disabled: busy || !online,
    };

    if (field.type === "photo") {
      return (
        <div className="eay-field-photo-boundary" role="note">
          <Camera aria-hidden="true" size={20} />
          <span>{f("photoUnavailable")}</span>
        </div>
      );
    }
    if (field.type === "yes_no") {
      return (
        <input
          {...common}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => setCaptureValue(field.key, event.target.checked)}
        />
      );
    }
    if (field.type === "gps") {
      return (
        <div className="eay-field-inline">
          <button type="button" className="eay-field-button secondary" onClick={() => captureGps(field.key)} disabled={busy || !online}>
            <MapPin aria-hidden="true" size={18} /> {f("gpsCapture")}
          </button>
          {value ? <output>{`${Number(value.latitude).toFixed(5)}, ${Number(value.longitude).toFixed(5)} · ±${Math.round(value.accuracy_m)}m`}</output> : null}
        </div>
      );
    }
    if (field.type === "multi_row") {
      const rows = Array.isArray(value) ? value : [];
      return (
        <div className="eay-field-rows">
          {rows.map((row, index) => (
            <div className="eay-field-inline" key={`${field.key}-${index}`}>
              <input
                type="text"
                value={row.value || ""}
                aria-label={`${label} ${index + 1}`}
                onChange={(event) => {
                  const nextRows = rows.map((candidate, rowIndex) => rowIndex === index ? { ...candidate, value: event.target.value } : candidate);
                  setCaptureValue(field.key, nextRows);
                }}
                disabled={busy || !online}
              />
              <button type="button" className="eay-field-icon-button" onClick={() => setCaptureValue(field.key, rows.filter((_, rowIndex) => rowIndex !== index))} aria-label={f("removeRow")}>
                <Trash2 aria-hidden="true" size={17} />
              </button>
            </div>
          ))}
          <button type="button" className="eay-field-button secondary" onClick={() => setCaptureValue(field.key, [...rows, { value: "" }])} disabled={busy || !online}>
            <Plus aria-hidden="true" size={17} /> {f("addRow")}
          </button>
        </div>
      );
    }
    if (field.type === "select") {
      return (
        <select {...common} value={value || ""} onChange={(event) => setCaptureValue(field.key, event.target.value)}>
          <option value="">—</option>
          {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      );
    }

    const inputType = field.type === "expiry" ? "date" : ["number", "quantity", "measurement"].includes(field.type) ? "number" : "text";
    return (
      <input
        {...common}
        type={inputType}
        inputMode={["number", "quantity", "measurement"].includes(field.type) ? "decimal" : undefined}
        value={value ?? ""}
        onChange={(event) => setCaptureValue(
          field.key,
          inputType === "number" && event.target.value !== "" ? Number(event.target.value) : event.target.value
        )}
      />
    );
  };

  return (
    <main className="eay-field-shell">
      <header className="eay-field-header">
        <div>
          <div className="eay-field-eyebrow"><ShieldCheck aria-hidden="true" size={20} />{f("commandCenter")}</div>
          <h1>{f("moduleTitle")}</h1>
          <p>{f("moduleDescription")}</p>
        </div>
        <div className="eay-field-header-actions">
          <button type="button" className="eay-field-button secondary" onClick={load} disabled={loading}>
            <RefreshCw aria-hidden="true" size={18} /> {f("refresh")}
          </button>
          <button type="button" className="eay-field-button secondary" onClick={() => navigate("/")}>
            <ArrowLeft aria-hidden="true" size={18} /> {t("back")}
          </button>
        </div>
      </header>

      {!online ? <FieldState state="offline">{f("offline")}</FieldState> : null}
      {loading ? <FieldState state="loading">{f("loading")}</FieldState> : null}
      {error && !loading ? <FieldState state="error" action={<button type="button" className="eay-field-button secondary" onClick={load}>{t("retry")}</button>}>{error}</FieldState> : null}
      {actionError ? <FieldState state="error">{actionError}</FieldState> : null}
      {actionMessage ? <FieldState state="success">{actionMessage}</FieldState> : null}

      {!loading && !error && bootstrap ? (
        <>
          <nav className="eay-field-tabs" aria-label={f("moduleTitle")}>
            {tabs.map(([key, labelKey]) => (
              <button key={key} type="button" className={selectedTab === key ? "is-active" : ""} onClick={() => setSelectedTab(key)} aria-current={selectedTab === key ? "page" : undefined}>
                {f(labelKey)}
              </button>
            ))}
          </nav>

          {missions.length === 0 && templates.length === 0 && selectedTab === "command" ? <FieldState state="empty">{f("empty")}</FieldState> : null}

          {selectedTab === "command" ? (
            <section className="eay-field-section" aria-labelledby="field-command-title">
              <div className="eay-field-section-heading">
                <div><span className="eay-field-kicker"><BarChart3 aria-hidden="true" size={18} />{f("analytics")}</span><h2 id="field-command-title">{f("commandCenter")}</h2></div>
              </div>
              <div className="eay-field-metric-grid">
                <article><strong>{activeMissions.length}</strong><span>{f("activeMissions")}</span></article>
                <article><strong>{analytics?.target_count ?? missions.reduce((sum, item) => sum + Number(item.target_count || 0), 0)}</strong><span>{f("targetCount")}</span></article>
                <article><strong>{analytics ? `${analytics.completion_percent}%` : "—"}</strong><span>{f("completion")}</span></article>
                <article><strong>{analytics?.deadline_overdue_targets ?? missions.filter((item) => item.is_deadline_overdue).length}</strong><span>{f("overdueTargets")}</span></article>
              </div>
              <div className="eay-field-card-grid">
                {missions.slice(0, 12).map((mission) => (
                  <article className="eay-field-card" key={mission.id}>
                    <div className="eay-field-card-head"><strong>{localized(mission.title_i18n, locale) || mission.template_id}</strong><span className={`eay-field-pill is-${mission.status}`}>{mission.status}</span></div>
                    <dl>
                      <dt>{f("targetCount")}</dt><dd>{mission.target_count}</dd>
                      <dt>{f("completion")}</dt><dd>{mission.target_count ? `${Math.round((Number(mission.verified || 0) + Number(mission.exempt || 0)) / Number(mission.target_count) * 100)}%` : "—"}</dd>
                      <dt>{f("deadlineAt")}</dt><dd>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(mission.deadline_at))}</dd>
                    </dl>
                    <div className="eay-field-inline wrap">
                      <button type="button" className="eay-field-button secondary" onClick={() => { setSelectedTab("missions"); loadMissionDetail(mission.id); }}><ClipboardList aria-hidden="true" size={17} />{f("missionDetail")}</button>
                      {canRemind && mission.status === "active" ? <button type="button" className="eay-field-button secondary" disabled={busy || !online} onClick={() => queueNotification(mission.id, "reminder")}><BellRing aria-hidden="true" size={17} />{f("sendReminder")}</button> : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {selectedTab === "missions" ? (
            <section className="eay-field-section" aria-labelledby="field-missions-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><ClipboardList aria-hidden="true" size={18} />{f("missions")}</span><h2 id="field-missions-title">{f("missions")}</h2></div></div>
              {missions.length === 0 ? <FieldState state="empty">{f("noMissions")}</FieldState> : (
                <div className="eay-field-split">
                  <div className="eay-field-list" role="list">
                    {missions.map((mission) => (
                      <button type="button" key={mission.id} className={`eay-field-list-row ${selectedMissionId === mission.id ? "is-selected" : ""}`} onClick={() => loadMissionDetail(mission.id)}>
                        <span><strong>{localized(mission.title_i18n, locale) || mission.template_id}</strong><small>{mission.status}</small></span>
                        <span>{mission.target_count}</span>
                      </button>
                    ))}
                  </div>
                  <div className="eay-field-detail">
                    {!missionDetail ? <FieldState state="empty">{f("missionDetail")}</FieldState> : (
                      <>
                        <div className="eay-field-card-head"><h3>{localized(missionDetail.title_i18n, locale) || missionDetail.template_id}</h3><span className={`eay-field-pill is-${missionDetail.status}`}>{missionDetail.status}</span></div>
                        <p>{localized(missionDetail.instructions_i18n, locale)}</p>
                        <dl className="eay-field-detail-grid">
                          <dt>{f("template")}</dt><dd>{missionDetail.template_id} v{missionDetail.template_version}</dd>
                          <dt>{f("targetFingerprint")}</dt><dd><code>{missionDetail.target_fingerprint}</code></dd>
                          <dt>{f("deadlineAt")}</dt><dd>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(missionDetail.deadline_at))}</dd>
                          <dt>{f("createdBy")}</dt><dd>{missionDetail.created_by}</dd>
                        </dl>
                        {missionDetail.is_deadline_overdue ? <FieldState state="error">{f("deadlineOverdue")}</FieldState> : null}
                        <div className="eay-field-inline wrap">
                          {canActivate && missionDetail.status === "draft" ? <button type="button" className="eay-field-button" disabled={busy || !online} onClick={async () => { const result = await runMutation(() => apiPost(`/v1/field/missions/${encodeURIComponent(missionDetail.id)}/activate`, {}), f("activateMission")); if (result) loadMissionDetail(missionDetail.id); }}><CheckCircle2 aria-hidden="true" size={17} />{f("activateMission")}</button> : null}
                          {canCancel && ["draft", "active"].includes(missionDetail.status) ? <button type="button" className="eay-field-button danger" disabled={busy || !online} onClick={async () => { const result = await runMutation(() => apiPost(`/v1/field/missions/${encodeURIComponent(missionDetail.id)}/cancel`, {}), f("cancelMission")); if (result) loadMissionDetail(missionDetail.id); }}><XCircle aria-hidden="true" size={17} />{f("cancelMission")}</button> : null}
                          {canRemind && missionDetail.status === "active" ? <><button type="button" className="eay-field-button secondary" disabled={busy || !online} onClick={() => queueNotification(missionDetail.id, "reminder")}><BellRing aria-hidden="true" size={17} />{f("sendReminder")}</button><button type="button" className="eay-field-button secondary" disabled={busy || !online} onClick={() => queueNotification(missionDetail.id, "escalation")}><AlertTriangle aria-hidden="true" size={17} />{f("escalate")}</button></> : null}
                        </div>
                        <div className="eay-field-target-list">
                          {(missionDetail.targets || []).map((target) => (
                            <div key={target.location_id} className="eay-field-target-row"><span><strong>{target.location_name}</strong><small>{target.region || target.city || target.location_id}</small></span><span className={`eay-field-pill is-${target.status}`}>{target.status}</span></div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </section>
          ) : null}

          {selectedTab === "builder" && canBuildMission ? (
            <section className="eay-field-section" aria-labelledby="field-builder-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><ClipboardCheck aria-hidden="true" size={18} />{f("missionBuilder")}</span><h2 id="field-builder-title">{f("missionBuilder")}</h2></div></div>
              {activeTemplates.length === 0 ? <FieldState state="empty">{f("noTemplates")}</FieldState> : (
                <form className="eay-field-form" onSubmit={createMission}>
                  <label><span>{f("template")}</span><select value={missionForm.templateKey} required onChange={(event) => setMissionForm((current) => ({ ...current, templateKey: event.target.value }))}><option value="">—</option>{activeTemplates.map((item) => <option key={`${item.template_id}:${item.version}`} value={`${item.template_id}:${item.version}`}>{localized(item.name_i18n, locale) || item.template_id} · v{item.version}</option>)}</select></label>
                  <label><span>{f("missionTitle")}</span><input required value={missionForm.title} onChange={(event) => setMissionForm((current) => ({ ...current, title: event.target.value }))} /></label>
                  <label className="span-2"><span>{f("instructions")}</span><textarea rows="3" value={missionForm.instructions} onChange={(event) => setMissionForm((current) => ({ ...current, instructions: event.target.value }))} /></label>
                  <label><span>{f("priority")}</span><select value={missionForm.priority} onChange={(event) => setMissionForm((current) => ({ ...current, priority: event.target.value }))}><option value="normal">{f("normal")}</option><option value="high">{f("high")}</option><option value="critical">{f("critical")}</option></select></label>
                  <label><span>{f("assignedAt")}</span><input type="datetime-local" required value={missionForm.assignedAt} onChange={(event) => setMissionForm((current) => ({ ...current, assignedAt: event.target.value }))} /></label>
                  <label><span>{f("deadlineAt")}</span><input type="datetime-local" required value={missionForm.deadlineAt} onChange={(event) => setMissionForm((current) => ({ ...current, deadlineAt: event.target.value }))} /></label>
                  <label className="eay-field-checkbox"><input type="checkbox" checked={missionForm.activate} onChange={(event) => setMissionForm((current) => ({ ...current, activate: event.target.checked }))} /><span>{f("activateImmediately")}</span></label>
                  <fieldset className="span-2 eay-field-fieldset"><legend>{f("targetingPreview")}</legend><label className="eay-field-checkbox"><input type="checkbox" checked={missionForm.allActive} onChange={(event) => setMissionForm((current) => ({ ...current, allActive: event.target.checked, locationIds: event.target.checked ? [] : current.locationIds }))} /><span>{f("allActiveLocations")}</span></label>{!missionForm.allActive ? <div className="eay-field-location-grid">{locations.filter((item) => item.active).map((location) => <label className="eay-field-checkbox" key={location.location_id}><input type="checkbox" checked={missionForm.locationIds.includes(location.location_id)} onChange={(event) => selectTarget(location.location_id, event.target.checked)} /><span>{location.name}</span></label>)}</div> : null}<p className="eay-field-boundary-note">{f("serverTargetAuthority")}</p><strong>{f("selectedTargets")}: {missionForm.allActive ? locations.filter((item) => item.active).length : missionForm.locationIds.length}</strong></fieldset>
                  <button type="submit" className="eay-field-button span-2" disabled={busy || !online || (!missionForm.allActive && missionForm.locationIds.length === 0)}><Send aria-hidden="true" size={18} />{f("createMission")}</button>
                </form>
              )}
            </section>
          ) : null}

          {selectedTab === "templates" && canManageTemplates ? (
            <section className="eay-field-section" aria-labelledby="field-template-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><Save aria-hidden="true" size={18} />{f("templateEditor")}</span><h2 id="field-template-title">{f("templateEditor")}</h2></div></div>
              <form className="eay-field-form" onSubmit={saveTemplate}>
                <label><span>{f("templateId")}</span><input required pattern="[a-z0-9][a-z0-9_.-]*" value={templateForm.templateId} onChange={(event) => setTemplateForm((current) => ({ ...current, templateId: event.target.value }))} /></label>
                <label><span>{f("version")}</span><input required type="number" min="1" value={templateForm.version} onChange={(event) => setTemplateForm((current) => ({ ...current, version: Number(event.target.value) }))} /></label>
                <label><span>{f("templateName")}</span><input required value={templateForm.name} onChange={(event) => setTemplateForm((current) => ({ ...current, name: event.target.value }))} /></label>
                <label><span>{f("templateStatus")}</span><select value={templateForm.status} onChange={(event) => setTemplateForm((current) => ({ ...current, status: event.target.value }))}><option value="draft">{f("draft")}</option><option value="active">{f("active")}</option></select></label>
                <div className="span-2 eay-field-builder-fields">
                  {templateForm.fields.map((field, index) => (
                    <fieldset className="eay-field-template-field" key={index}>
                      <legend>{`${f("fieldLabel")} ${index + 1}`}</legend>
                      <label><span>{f("fieldKey")}</span><input required value={field.key} onChange={(event) => updateTemplateField(index, { key: event.target.value })} /></label>
                      <label><span>{f("fieldLabel")}</span><input required value={field.label} onChange={(event) => updateTemplateField(index, { label: event.target.value })} /></label>
                      <label><span>{f("fieldType")}</span><select value={field.type} onChange={(event) => updateTemplateField(index, { type: event.target.value, optionsText: event.target.value === "select" ? field.optionsText : "" })}>{FIELD_TYPES.map((type) => <option key={type} value={type}>{f(TYPE_MESSAGE_KEYS[type])}</option>)}</select></label>
                      {field.type === "select" ? <label><span>{f("typeSelect")}</span><input required value={field.optionsText} onChange={(event) => updateTemplateField(index, { optionsText: event.target.value })} /></label> : null}
                      <label className="eay-field-checkbox"><input type="checkbox" checked={field.required} onChange={(event) => updateTemplateField(index, { required: event.target.checked })} /><span>{f("required")}</span></label>
                      {templateForm.fields.length > 1 ? <button type="button" className="eay-field-button danger" onClick={() => setTemplateForm((current) => ({ ...current, fields: current.fields.filter((_, fieldIndex) => fieldIndex !== index) }))}><Trash2 aria-hidden="true" size={17} />{f("removeField")}</button> : null}
                    </fieldset>
                  ))}
                  <button type="button" className="eay-field-button secondary" onClick={() => setTemplateForm((current) => ({ ...current, fields: [...current.fields, initialField()] }))}><Plus aria-hidden="true" size={17} />{f("addField")}</button>
                </div>
                <button type="submit" className="eay-field-button span-2" disabled={busy || !online}><Save aria-hidden="true" size={18} />{f("saveTemplate")}</button>
              </form>
            </section>
          ) : null}

          {selectedTab === "capture" && canCapture ? (
            <section className="eay-field-section eay-field-capture" aria-labelledby="field-capture-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><ScanLine aria-hidden="true" size={18} />{f("capture")}</span><h2 id="field-capture-title">{f("quickCapture")}</h2></div></div>
              {activeMissions.length === 0 ? <FieldState state="empty">{f("noCaptureTargets")}</FieldState> : (
                <form className="eay-field-capture-form" onSubmit={submitCapture}>
                  <label><span>{f("chooseMission")}</span><select value={captureMissionId} required onChange={(event) => loadCaptureMission(event.target.value)}><option value="">—</option>{activeMissions.map((mission) => <option key={mission.id} value={mission.id}>{localized(mission.title_i18n, locale) || mission.template_id}</option>)}</select></label>
                  {captureDetail ? <label><span>{f("chooseLocation")}</span><select value={captureLocationId} required onChange={(event) => { setCaptureLocationId(event.target.value); setCaptureValues({}); }}><option value="">—</option>{captureTargets.map((target) => <option key={target.location_id} value={target.location_id}>{target.location_name} · {target.status}</option>)}</select></label> : null}
                  {captureDetail && captureTargets.length === 0 ? <FieldState state="empty">{f("noCaptureTargets")}</FieldState> : null}
                  {captureLocationId ? <div className="eay-field-capture-fields">{captureFields.map((field) => <label key={field.key} className={field.type === "multi_row" || field.type === "photo" ? "span-2" : ""}><span>{localized(field.label, locale) || field.key}{field.required ? " *" : ""}</span>{renderCaptureField(field)}{field.helper ? <small>{localized(field.helper, locale)}</small> : null}</label>)}</div> : null}
                  <p className="eay-field-boundary-note"><ShieldCheck aria-hidden="true" size={16} />{f("clientDeviceUnverified")}</p>
                  <button type="submit" className="eay-field-button" disabled={busy || !online || !captureLocationId || requiredPhotoBlocked}><Send aria-hidden="true" size={18} />{f("submitEvidence")}</button>
                </form>
              )}
            </section>
          ) : null}

          {selectedTab === "review" && canReview ? (
            <section className="eay-field-section" aria-labelledby="field-review-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><ClipboardCheck aria-hidden="true" size={18} />{f("evidenceReview")}</span><h2 id="field-review-title">{f("evidenceReview")}</h2></div></div>
              {evidence.filter((item) => !item.review_decision).length === 0 ? <FieldState state="empty">{f("noEvidence")}</FieldState> : <div className="eay-field-card-grid">{evidence.filter((item) => !item.review_decision).map((item) => <article className="eay-field-card" key={item.id}><div className="eay-field-card-head"><strong>{item.location_name || item.location_id}</strong><span>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.submitted_at))}</span></div><dl><dt>{f("evidenceFingerprint")}</dt><dd><code>{item.fingerprint}</code></dd><dt>{f("location")}</dt><dd>{item.location_id}</dd></dl><pre className="eay-field-evidence-payload">{JSON.stringify(item.payload, null, 2)}</pre><label><span>{f("reason")}</span><textarea rows="2" value={reviewReasons[item.id] || ""} onChange={(event) => setReviewReasons((current) => ({ ...current, [item.id]: event.target.value }))} /></label><div className="eay-field-inline wrap"><button type="button" className="eay-field-button" disabled={busy || !online} onClick={() => reviewEvidence(item, "accept")}><CheckCircle2 aria-hidden="true" size={17} />{f("accept")}</button><button type="button" className="eay-field-button secondary" disabled={busy || !online || !(reviewReasons[item.id] || "").trim()} onClick={() => reviewEvidence(item, "rework")}><RotateCcw aria-hidden="true" size={17} />{f("rework")}</button><button type="button" className="eay-field-button danger" disabled={busy || !online || !(reviewReasons[item.id] || "").trim()} onClick={() => reviewEvidence(item, "reject")}><XCircle aria-hidden="true" size={17} />{f("reject")}</button></div></article>)}</div>}
            </section>
          ) : null}

          {selectedTab === "analytics" && canAnalytics ? (
            <section className="eay-field-section" aria-labelledby="field-analytics-title">
              <div className="eay-field-section-heading"><div><span className="eay-field-kicker"><BarChart3 aria-hidden="true" size={18} />{f("analytics")}</span><h2 id="field-analytics-title">{f("analytics")}</h2></div></div>
              {!analytics ? <FieldState state="empty">{f("empty")}</FieldState> : <><div className="eay-field-metric-grid"><article><strong>{analytics.mission_count}</strong><span>{f("missions")}</span></article><article><strong>{analytics.active_mission_count}</strong><span>{f("activeMissions")}</span></article><article><strong>{analytics.target_count}</strong><span>{f("targetCount")}</span></article><article><strong>{analytics.completion_percent}%</strong><span>{f("completion")}</span></article></div><div className="eay-field-status-grid" aria-label={f("statusDistribution")}>{Object.entries(analytics.status_counts || {}).map(([statusKey, count]) => <div key={statusKey}><span>{statusKey}</span><strong>{count}</strong></div>)}</div></>}
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
