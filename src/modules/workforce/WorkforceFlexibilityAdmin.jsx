import React, { useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckCircle2, ShieldCheck, Users } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { workforceFlexibilityAdminMessage } from "../../platform/i18n/workforceFlexibilityAdminMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { createWorkforceOpenShift, loadAdminWorkforce } from "./workforceApi.js";
import "./workforceFlexibilityAdmin.css";


function nextDay() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date.toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
}

export default function WorkforceFlexibilityAdmin() {
  const { canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const m = (key, params) => workforceFlexibilityAdminMessage(locale, key, params);
  const allowed = canAction("workforce", "createShift");
  const [warehouses, setWarehouses] = useState([]);
  const [form, setForm] = useState({ warehouseId: "", date: nextDay(), start: "09:00", end: "18:00", breakMinutes: 60, role: "Picker", capacity: 1, note: "" });
  const [created, setCreated] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!allowed) return;
    let active = true;
    loadAdminWorkforce().then((data) => {
      if (!active) return;
      const rows = data.warehouses || [];
      setWarehouses(rows);
      setForm((current) => ({ ...current, warehouseId: current.warehouseId || rows[0]?.id || "" }));
    }).catch((requestError) => { if (active) setError(requestError.message || m("loadError")); });
    return () => { active = false; };
  }, [allowed]);

  const selectedWarehouse = useMemo(
    () => warehouses.find((row) => String(row.id) === String(form.warehouseId)),
    [form.warehouseId, warehouses],
  );

  async function publish(event) {
    event.preventDefault();
    if (!allowed || !form.warehouseId) return;
    setBusy(true); setError(""); setCreated(null);
    try {
      const result = await createWorkforceOpenShift(form);
      setCreated(result);
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(false); }
  }

  if (!allowed) return <section className="wfx-panel wfx-flex-admin-denied"><ShieldCheck size={20} /><span>{m("permission")}</span></section>;

  return <section className="wfx-panel wfx-flex-admin">
    <header><div><span>{m("eyebrow")}</span><h3>{m("title")}</h3><p>{m("detail")}</p></div><CalendarClock size={24} /></header>
    {error ? <div className="wfx-flex-admin-message error">{error}</div> : null}
    {created ? <div className="wfx-flex-admin-message success"><CheckCircle2 size={16} /><div><strong>{m("published")}</strong><small>{created.warehouse} · {created.date} · {created.start}–{created.end} · {m("remaining", { count: created.capacity })}</small></div></div> : null}
    <form onSubmit={publish}>
      <label>{m("warehouse")}<select value={form.warehouseId} onChange={(event) => setForm({ ...form, warehouseId: event.target.value })}>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></label>
      <label>{m("date")}<input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
      <label>{m("start")}<input type="time" value={form.start} onChange={(event) => setForm({ ...form, start: event.target.value })} /></label>
      <label>{m("end")}<input type="time" value={form.end} onChange={(event) => setForm({ ...form, end: event.target.value })} /></label>
      <label>{m("breakMinutes")}<input type="number" min="0" max="180" value={form.breakMinutes} onChange={(event) => setForm({ ...form, breakMinutes: event.target.value })} /></label>
      <label>{m("capacity")}<input type="number" min="1" max="50" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></label>
      <label>{m("role")}<input value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} /></label>
      <label className="wide">{m("note")}<input value={form.note} maxLength={500} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
      <button disabled={busy || !selectedWarehouse}><Users size={17} />{busy ? m("publishing") : m("publish")}</button>
    </form>
    <p className="wfx-flex-admin-rule"><ShieldCheck size={15} />{m("rule")}</p>
  </section>;
}
