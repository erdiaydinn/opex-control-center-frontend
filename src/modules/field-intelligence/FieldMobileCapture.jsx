import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Camera, MapPin, RefreshCw, Send, ShieldCheck, Wifi, WifiOff } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiFetch, apiGet, apiPost } from "../../api/client.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { translateField } from "./fieldMessages.js";
import { translateFieldMobile } from "./fieldMobileMessages.js";
import {
  drainFieldOfflineQueue,
  enqueueFieldOfflineEvidence,
  listFieldOfflineQueue,
  retryBlockedFieldOfflineEvent,
} from "./fieldOfflineQueue.js";
import "./field-mobile.css";

const ACTIONABLE = new Set(["unseen", "seen", "started", "partial", "rework", "overdue"]);

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "";
}

function queueStateLabel(t, state) {
  if (state === "awaiting_attachment") return t("awaitingAttachment");
  if (state === "blocked") return t("blocked");
  if (state === "conflict") return t("conflict");
  if (state === "stale_assignment") return t("staleAssignment");
  return t("queued");
}

async function uploadPrivateFieldAttachment({
  blob,
  fingerprint,
  fieldKey,
  clientSubmissionId,
  missionId,
  locationId,
}) {
  const query = new URLSearchParams({
    mission_id: missionId,
    location_id: locationId,
    client_submission_id: clientSubmissionId,
  });
  return apiFetch(`/v1/field/evidence-objects/${encodeURIComponent(fieldKey)}?${query.toString()}`, {
    method: "POST",
    headers: {
      "Content-Type": blob.type,
      "X-EAY-Content-SHA256": fingerprint,
    },
    body: blob,
  });
}

export default function FieldMobileCapture() {
  const navigate = useNavigate();
  const { locale } = usePlatformPreferences();
  const f = useMemo(() => (key) => translateField(locale, key), [locale]);
  const m = useMemo(() => (key) => translateFieldMobile(locale, key), [locale]);
  const [online, setOnline] = useState(() => navigator.onLine !== false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [bootstrap, setBootstrap] = useState(null);
  const [missionId, setMissionId] = useState("");
  const [mission, setMission] = useState(null);
  const [locationId, setLocationId] = useState("");
  const [values, setValues] = useState({});
  const [photos, setPhotos] = useState({});
  const [queue, setQueue] = useState([]);

  const refreshQueue = useCallback(async () => {
    try {
      setQueue(await listFieldOfflineQueue());
    } catch (queueError) {
      setError(queueError?.message || f("loadError"));
    }
  }, [f]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBootstrap(await apiGet("/v1/field/bootstrap"));
      await refreshQueue();
    } catch (loadError) {
      setError(loadError?.message || f("loadError"));
    } finally {
      setLoading(false);
    }
  }, [f, refreshQueue]);

  const sync = useCallback(async () => {
    if (navigator.onLine === false) return;
    setBusy(true);
    setError("");
    try {
      await drainFieldOfflineQueue({
        syncBatch: (body) => apiPost("/v1/field/offline-sync", body),
        uploadAttachment: uploadPrivateFieldAttachment,
      });
      await refreshQueue();
    } catch (syncError) {
      setError(syncError?.message || f("loadError"));
    } finally {
      setBusy(false);
    }
  }, [f, refreshQueue]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      sync();
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [sync]);

  const missions = (bootstrap?.missions || []).filter((item) => item.status === "active");
  const targets = (mission?.targets || []).filter((item) => ACTIONABLE.has(item.status));
  const fields = mission?.template_schema?.fields || [];

  async function chooseMission(nextMissionId) {
    setMissionId(nextMissionId);
    setLocationId("");
    setValues({});
    setPhotos({});
    setMission(null);
    if (!nextMissionId) return;
    try {
      setMission(await apiGet(`/v1/field/missions/${encodeURIComponent(nextMissionId)}`));
    } catch (missionError) {
      setError(missionError?.message || f("loadError"));
    }
  }

  function setValue(key, value) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function captureGps(key) {
    if (!navigator.geolocation) {
      setError(f("loadError"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => setValue(key, {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_m: position.coords.accuracy,
      }),
      () => setError(f("loadError")),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }

  function renderField(field) {
    const label = localized(field.label, locale) || field.key;
    const value = values[field.key];
    if (field.type === "photo") {
      return (
        <label key={field.key} className="eay-field-mobile-field">
          <span>{label}{field.required ? " *" : ""}</span>
          <div className="eay-field-mobile-photo">
            <Camera aria-hidden="true" size={20} />
            <input
              type="file"
              accept="image/*"
              capture="environment"
              required={Boolean(field.required)}
              onChange={(event) => setPhotos((current) => ({ ...current, [field.key]: event.target.files?.[0] || null }))}
            />
          </div>
        </label>
      );
    }
    if (field.type === "gps") {
      return (
        <label key={field.key} className="eay-field-mobile-field">
          <span>{label}{field.required ? " *" : ""}</span>
          <button type="button" className="eay-field-mobile-secondary" onClick={() => captureGps(field.key)}>
            <MapPin aria-hidden="true" size={18} /> {f("gpsCapture")}
          </button>
          {value ? <output>{`${Number(value.latitude).toFixed(5)}, ${Number(value.longitude).toFixed(5)} · ±${Math.round(value.accuracy_m)}m`}</output> : null}
        </label>
      );
    }
    if (field.type === "yes_no") {
      return (
        <label key={field.key} className="eay-field-mobile-check">
          <input type="checkbox" checked={Boolean(value)} onChange={(event) => setValue(field.key, event.target.checked)} />
          <span>{label}</span>
        </label>
      );
    }
    if (field.type === "select") {
      return (
        <label key={field.key} className="eay-field-mobile-field">
          <span>{label}{field.required ? " *" : ""}</span>
          <select required={Boolean(field.required)} value={value || ""} onChange={(event) => setValue(field.key, event.target.value)}>
            <option value="">—</option>
            {(field.options || []).map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
      );
    }
    if (field.type === "multi_row") {
      return (
        <label key={field.key} className="eay-field-mobile-field">
          <span>{label}{field.required ? " *" : ""}</span>
          <textarea
            rows="4"
            required={Boolean(field.required)}
            value={(Array.isArray(value) ? value : []).map((row) => row.value || "").join("\n")}
            onChange={(event) => setValue(field.key, event.target.value.split("\n").filter(Boolean).map((row) => ({ value: row })))}
          />
        </label>
      );
    }
    const inputType = field.type === "expiry" ? "date" : ["number", "quantity", "measurement"].includes(field.type) ? "number" : "text";
    return (
      <label key={field.key} className="eay-field-mobile-field">
        <span>{label}{field.required ? " *" : ""}</span>
        <input
          type={inputType}
          required={Boolean(field.required)}
          inputMode={inputType === "number" ? "decimal" : undefined}
          value={value ?? ""}
          onChange={(event) => setValue(field.key, inputType === "number" && event.target.value !== "" ? Number(event.target.value) : event.target.value)}
        />
      </label>
    );
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (!mission || !locationId) return;
    const attachments = Object.entries(photos)
      .filter(([, file]) => file)
      .map(([fieldKey, file]) => ({ fieldKey, file, captureSource: "camera_claim" }));
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== "" && value !== undefined),
    );
    try {
      await enqueueFieldOfflineEvidence({
        missionId: mission.id,
        locationId,
        targetFingerprint: mission.target_fingerprint,
        payload,
        attachments,
      });
      setValues({});
      setPhotos({});
      setMessage(online ? m("capturedOnline") : m("capturedOffline"));
      await refreshQueue();
      if (online) await sync();
    } catch (submitError) {
      setError(submitError?.message || f("loadError"));
    }
  }

  async function retryItem(item) {
    await retryBlockedFieldOfflineEvent(item.clientSubmissionId);
    await refreshQueue();
    if (online) await sync();
  }

  return (
    <main className="eay-field-mobile-shell">
      <header className="eay-field-mobile-header">
        <div>
          <span className="eay-field-mobile-eyebrow"><ShieldCheck aria-hidden="true" size={18} />{m("title")}</span>
          <h1>{m("title")}</h1>
          <p>{m("subtitle")}</p>
        </div>
        <button type="button" className="eay-field-mobile-secondary" onClick={() => navigate("/field-intelligence")}>
          <ArrowLeft aria-hidden="true" size={18} /> {m("back")}
        </button>
      </header>

      <section className={`eay-field-mobile-network ${online ? "is-online" : "is-offline"}`} role="status" aria-live="polite">
        {online ? <Wifi aria-hidden="true" size={18} /> : <WifiOff aria-hidden="true" size={18} />}
        <span>{online ? m("syncNow") : m("reconnect")}</span>
      </section>

      <p className="eay-field-mobile-boundary">{m("deviceTrustBoundary")}</p>
      <p className="eay-field-mobile-boundary">{m("cameraTrustBoundary")}</p>
      {loading ? <section role="status" aria-busy="true">{f("loading")}</section> : null}
      {error ? <section role="alert" className="eay-field-mobile-error">{error}</section> : null}
      {message ? <section role="status" className="eay-field-mobile-success">{message}</section> : null}

      {!loading ? (
        <section className="eay-field-mobile-card">
          <h2>{f("quickCapture")}</h2>
          {missions.length === 0 ? <p>{m("noAssignments")}</p> : (
            <form className="eay-field-mobile-form" onSubmit={submit}>
              <label className="eay-field-mobile-field">
                <span>{m("chooseMission")}</span>
                <select value={missionId} required onChange={(event) => chooseMission(event.target.value)}>
                  <option value="">—</option>
                  {missions.map((item) => <option key={item.id} value={item.id}>{localized(item.title_i18n, locale) || item.template_id}</option>)}
                </select>
              </label>
              {mission ? (
                <label className="eay-field-mobile-field">
                  <span>{m("chooseLocation")}</span>
                  <select value={locationId} required onChange={(event) => setLocationId(event.target.value)}>
                    <option value="">—</option>
                    {targets.map((target) => <option key={target.location_id} value={target.location_id}>{target.location_name} · {target.status}</option>)}
                  </select>
                </label>
              ) : null}
              {locationId ? fields.map(renderField) : null}
              <button type="submit" className="eay-field-mobile-primary" disabled={!locationId || busy}>
                <Send aria-hidden="true" size={18} /> {m("submit")}
              </button>
            </form>
          )}
        </section>
      ) : null}

      <section className="eay-field-mobile-card">
        <div className="eay-field-mobile-queue-head">
          <h2>{m("queue")}</h2>
          <button type="button" className="eay-field-mobile-secondary" onClick={sync} disabled={!online || busy || queue.length === 0}>
            <RefreshCw aria-hidden="true" size={18} /> {busy ? m("syncing") : m("syncNow")}
          </button>
        </div>
        {queue.length === 0 ? <p>{m("queueEmpty")}</p> : (
          <div className="eay-field-mobile-queue">
            {queue.map((item) => (
              <article key={item.clientSubmissionId} className={`eay-field-mobile-queue-item is-${item.state}`}>
                <strong>{queueStateLabel(m, item.state)}</strong>
                <dl>
                  <dt>{m("sequence")}</dt><dd>{item.deviceSequence}</dd>
                  <dt>{m("status")}</dt><dd>{item.state}</dd>
                  {item.lastError ? <><dt>{m("lastError")}</dt><dd>{item.lastError}</dd></> : null}
                </dl>
                {item.state === "blocked" ? <button type="button" className="eay-field-mobile-secondary" onClick={() => retryItem(item)}>{m("retry")}</button> : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
