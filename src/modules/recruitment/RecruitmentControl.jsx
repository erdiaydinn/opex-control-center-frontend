import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, BadgeCheck, BellRing, Building2, Check, ChevronRight, CircleAlert,
  FileCheck2, Mail, Moon, Plus, RefreshCw, Search, Settings2, Sun, UserPlus, Users, X,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { recruitmentMessage } from "../../platform/i18n/recruitmentMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  createRecruitmentRequest, decideRecruitmentRequest, downloadRecruitmentEvidence,
  evaluateRecruitment, loadRecruitment, retryRecruitmentEmail, saveRecruitmentNorm,
  saveRecruitmentSettings, uploadRecruitmentEvidence,
} from "./recruitmentApi.js";
import RecruitmentActualPanel from "./RecruitmentActualPanel.jsx";
import RecruitmentCandidateWorkspace from "./RecruitmentCandidateWorkspace.jsx";
import "./recruitment.css";

const POSITIONS = [
  ["STORE_STAFF", "positionStoreStaff"], ["ASSISTANT_MANAGER", "positionAssistantManager"],
  ["STORE_SUPPORT", "positionSupport"], ["STORE_MANAGER", "positionManager"],
];
const REASONS = [
  ["NORM_GAP", "reasonNormGap"], ["PLANNED_DEPARTURE", "reasonPlannedDeparture"],
  ["NEW_WAREHOUSE", "reasonNewWarehouse"], ["OTHER", "reasonOther"],
];
const STATUS = {
  PENDING_APPROVAL: ["statusPendingApproval", "warning"], EVIDENCE_REQUIRED: ["statusEvidenceRequired", "danger"],
  APPROVED: ["statusApproved", "success"], REJECTED: ["statusRejected", "danger"], SOURCING: ["statusSourcing", "info"],
  PARTIALLY_FILLED: ["statusPartiallyFilled", "info"], FILLED: ["statusFilled", "success"],
};
const HR_EMAIL_EXAMPLE = "hr@example.com";
const PARTNER_EMAIL_EXAMPLE = "partner@example.com";

function isoToday() { return new Date().toISOString().slice(0, 10); }
function addDays(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }
function splitEmails(value) { return [...new Set(value.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean))]; }

function StatusPill({ value, m }) {
  const [labelKey, tone] = STATUS[value] || ["statusReviewPending", "neutral"];
  return <span className={`rec-status ${tone}`}>{m(labelKey)}</span>;
}

function Metric({ icon: Icon, label, value, detail, tone = "pink" }) {
  return <article className={`rec-metric tone-${tone}`}><span><Icon size={19} /></span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>;
}

export default function RecruitmentControl() {
  const navigate = useNavigate();
  const { user, canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const m = (key, params) => recruitmentMessage(locale, key, params);
  const [dark, setDark] = useState(() => localStorage.getItem("opex_theme") === "dark");
  const [tab, setTab] = useState("overview");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const [decisionNote, setDecisionNote] = useState("");

  async function refresh() {
    setLoading(true); setError("");
    try { const next = await loadRecruitment(); setData(next); return next; }
    catch (err) { setError(err.message); return null; }
    finally { setLoading(false); }
  }
  async function refreshSelected() {
    const selectedId = selected?.id;
    try {
      const next = await loadRecruitment();
      setData(next);
      if (selectedId) setSelected((next?.requests || []).find((row) => row.id === selectedId) || null);
    } catch (err) { setError(err.message); }
  }
  useEffect(() => { refresh(); }, []);
  function flash(message) { setNotice(message); window.setTimeout(() => setNotice(""), 3800); }
  function toggleTheme() { setDark((value) => { localStorage.setItem("opex_theme", value ? "light" : "dark"); return !value; }); }

  const requests = useMemo(() => (data?.requests || []).filter((row) => [row.id, row.warehouseName, row.positionLabel, row.requestedByName].join(" ").toLocaleLowerCase(locale).includes(query.toLocaleLowerCase(locale))), [data, query, locale]);
  const canApprove = canAction("recruitment", "approveRecruitmentRequest");
  const canManageActuals = canAction("recruitment", "manageRecruitmentActuals");

  async function decide(decision) {
    if (!selected || !decisionNote.trim()) { setError(m("decisionRequired")); return; }
    try {
      await decideRecruitmentRequest(selected.id, decision, decisionNote.trim());
      setDecisionNote("");
      flash(decision === "APPROVED" ? m("requestApproved") : m("requestRejected"));
      await refreshSelected();
    } catch (err) { setError(err.message); }
  }

  const decisionOpen = selected && ["PENDING_APPROVAL", "EVIDENCE_REQUIRED"].includes(selected.status);
  const tabs = [
    ["overview", m("tabOverview")], ["staffing", m("tabStaffing")], ["requests", m("tabRequests")],
    ["new", m("tabNew")], ["settings", m("tabSettings")],
  ];

  return (
    <main className={`rec-page ${dark ? "is-dark" : ""}`}>
      <div className="rec-grid-bg" />
      <section className="rec-shell">
        <header className="rec-topbar">
          <div className="rec-brand"><button onClick={() => navigate("/")}><ArrowLeft size={18} /></button><div className="rec-logo"><UserPlus size={21} /></div><div><span>{m("peopleOperations")}</span><strong>{m("recruitmentRequests")}</strong></div></div>
          <div className="rec-actions"><span className="rec-user"><strong>{user?.name || user?.email}</strong><small>{user?.role || m("authorizedUser")}</small></span><button onClick={toggleTheme}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? m("light") : m("dark")}</button><button onClick={refresh}><RefreshCw size={16} /> {m("refresh")}</button></div>
        </header>

        <section className="rec-hero">
          <div><span className="rec-eyebrow"><BadgeCheck size={15} /> {m("heroEyebrow")}</span><h1>{m("heroLine1")}<br /><em>{m("heroLine2")}</em>{m("heroLine3")}</h1><p>{m("heroDesc")}</p></div>
          <aside><span>{m("decisionEngine")}</span><strong>{m("engineTitle")}</strong><div><Check size={17} /> {m("engineActual")}</div><div><Check size={17} /> {m("engineMaster")}</div><div><Check size={17} /> {m("engineLifecycle")}</div></aside>
        </section>

        {error && <div className="rec-alert error"><CircleAlert size={18} />{error}<button onClick={() => setError("")}><X size={16} /></button></div>}
        {notice && <div className="rec-alert success"><Check size={18} />{notice}</div>}

        <nav className="rec-tabs">
          {tabs.map(([key, label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}
        </nav>

        {loading ? <section className="rec-loading">{m("loading")}</section> : <>
          {tab === "overview" && <Overview data={data} setTab={setTab} m={m} />}
          {tab === "staffing" && <RecruitmentActualPanel data={data} refresh={refresh} flash={flash} setError={setError} canManage={canManageActuals} />}
          {tab === "requests" && <Requests rows={requests} query={query} setQuery={setQuery} select={setSelected} outbox={data?.emailOutbox || []} retry={async (id) => { try { await retryRecruitmentEmail(id); await refresh(); } catch (err) { setError(err.message); } }} m={m} />}
          {tab === "new" && <NewRequest data={data} onDone={async () => { flash(m("requestSaved")); await refresh(); setTab("requests"); }} setError={setError} m={m} />}
          {tab === "settings" && <Settings data={data} refresh={refresh} flash={flash} setError={setError} m={m} locale={locale} />}
        </>}
      </section>

      {selected && <div className="rec-modal-backdrop" onMouseDown={() => setSelected(null)}><section className="rec-modal rec-modal-lifecycle" onMouseDown={(event) => event.stopPropagation()}><button className="rec-modal-close" onClick={() => setSelected(null)}><X /></button><span className="rec-kicker">{m("vacancyLifecycle")}</span><h2>{selected.warehouseName}</h2><p className="rec-modal-lead">{selected.positionLabel} · {m("peopleCount", { count: selected.quantity })} · {selected.id}</p><EvaluationCard evaluation={selected.currentStaffing || selected} m={m} />{selected.evidence && <button className="rec-secondary wide" onClick={() => downloadRecruitmentEvidence(selected.id, selected.evidence.originalName)}><FileCheck2 size={17} /> {m("resignationDownload")}</button>}{decisionOpen ? <><label>{m("decisionNote")} <small>{m("decisionAudit")}</small><textarea value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} placeholder={m("decisionPlaceholder")} /></label>{canApprove ? <div className="rec-decision-actions"><button className="reject" onClick={() => decide("REJECTED")}><X size={17} /> {m("reject")}</button><button className="approve" onClick={() => decide("APPROVED")}><Check size={17} /> {m("approveNotify")}</button></div> : <div className="rec-alert">{m("readOnly")}</div>}</> : <RecruitmentCandidateWorkspace request={selected} canApprove={canApprove} onChanged={refreshSelected} flash={flash} setError={setError} />}</section></div>}
    </main>
  );
}

function Overview({ data, setTab, m }) {
  const dash = data?.dashboard || {};
  const snapshot = data?.actualSnapshot;
  return <section className="rec-content"><div className="rec-metrics"><Metric icon={BellRing} label={m("pendingApproval")} value={dash.pending || 0} detail={m("pendingDetail")} /><Metric icon={FileCheck2} label={m("hrActual")} value={snapshot?.activeRows ?? "—"} detail={snapshot ? m("activeFteMatch", { fte: snapshot.activeFte, match: snapshot.matchRate }) : m("officialSnapshotWaiting")} tone="amber" /><Metric icon={BadgeCheck} label={m("approved")} value={dash.approved || 0} detail={m("sourcingReady")} tone="green" /><Metric icon={Building2} label={m("normGap")} value={dash.normGapWarehouses || 0} detail={m("masterOpenReqDetail")} tone="purple" /></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">{m("headcountSignal")}</span><h2>{m("highestNeed")}</h2></div><button className="rec-secondary" onClick={() => setTab("staffing")}>{m("staffingReconciliation")}</button><button className="rec-primary" onClick={() => setTab("new")}><Plus size={17} /> {m("newRequest")}</button></div><div className="rec-gap-grid">{(dash.warehouseRows || []).filter((row) => row.available > 0).slice(0, 8).map((row) => <article key={row.warehouseName}><div><strong>{row.warehouseName}</strong><span>{row.normRecord?.regionalExecutive || m("byPending")}</span></div><b>{row.available}</b><small>{m("gapSummary", { norm: row.capacity, hr: row.hrActual ?? "—", em: row.active, open: row.openPositions })}</small></article>)}</div></div></section>;
}

function Requests({ rows, query, setQuery, select, outbox, retry, m }) {
  return <section className="rec-content"><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">{m("approvalFlow")}</span><h2>{m("requestTable")}</h2></div><label className="rec-search"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={m("searchPlaceholder")} /></label></div><div className="rec-table-wrap"><table><thead><tr><th>{m("requestDepot")}</th><th>{m("position")}</th><th>{m("normActual")}</th><th>{m("need")}</th><th>{m("status")}</th><th /></tr></thead><tbody>{rows.map((row) => { const staffing = row.currentStaffing || row; return <tr key={row.id}><td><strong>{row.warehouseName}</strong><small>{row.id} · {row.requestedByName}</small></td><td>{row.positionLabel}<small>{m("peopleCount", { count: row.quantity })}</small></td><td><strong>{staffing.active} / {staffing.capacity}</strong><small>{m("hrOpenProjected", { hr: staffing.hrActual ?? "—", open: staffing.openPositions, projected: staffing.projected })}</small></td><td>{row.neededBy}<small>{row.reasonCode === "PLANNED_DEPARTURE" ? m("plannedDeparture") : m("operationalNeed")}</small></td><td><StatusPill value={row.status} m={m} /></td><td><button className="rec-row-action" onClick={() => select(row)}>{m("inspect")} <ChevronRight size={16} /></button></td></tr>; })}</tbody></table>{!rows.length && <div className="rec-empty">{m("noMatchingRequest")}</div>}</div></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">{m("deliveryOutbox")}</span><h2>{m("hrPartnerNotifications")}</h2></div></div><div className="rec-outbox">{outbox.map((row) => <article key={row.id}><Mail size={18} /><div><strong>{row.recipientGroup} · {row.requestId}</strong><small>{row.payload?.recipients?.join(", ") || m("recipientsUndefined")}</small></div><StatusPill value={row.status} m={m} />{row.status !== "DELIVERED" && <button onClick={() => retry(row.id)}>{m("retry")}</button>}</article>)}{!outbox.length && <div className="rec-empty">{m("noEmailQueue")}</div>}</div></div></section>;
}

function EvaluationCard({ evaluation, m }) {
  if (!evaluation) return null;
  const approved = evaluation.recommendation === "APPROVE";
  const label = approved ? m("normSuitable") : evaluation.recommendation === "REJECT" ? m("normOver") : m("manualReview");
  return <div className={`rec-evaluation ${approved ? "approve" : evaluation.recommendation === "REJECT" ? "reject" : "review"}`}><div><span>{m("recommendation")}</span><strong>{label}</strong><p>{evaluation.recommendationReason}</p><small>{evaluation.hrActualAsOf ? m("actualAuthorityDate", { date: evaluation.hrActualAsOf }) : m("masterAuthorityFallback")}</small></div><div className="rec-eval-numbers"><span><small>{m("capacity")}</small><b>{evaluation.capacity}</b></span><span><small>{m("hrActual")}</small><b>{evaluation.hrActual ?? "—"}</b></span><span><small>{m("emActual")}</small><b>{evaluation.active}</b></span><span><small>{m("open")}</small><b>{evaluation.openPositions}</b></span><span><small>{m("gap")}</small><b>{evaluation.available}</b></span></div></div>;
}

function NewRequest({ data, onDone, setError, m }) {
  const firstWarehouse = data?.norms?.[0]?.warehouse || data?.warehouses?.[0]?.id || "";
  const [form, setForm] = useState({ warehouseId: firstWarehouse, positionCode: "STORE_STAFF", quantity: 1, employmentType: "FULL_TIME", reasonCode: "NORM_GAP", neededBy: addDays(21), justification: "" });
  const [departure, setDeparture] = useState({ employeeId: "", employeeName: "", lastWorkingDate: addDays(14), departureType: "RESIGNATION" });
  const [file, setFile] = useState(null); const [evaluation, setEvaluation] = useState(null); const [busy, setBusy] = useState(false);
  const warehousePeople = (data?.people || []).filter((person) => String(person.warehouseId || person.warehouse || "").toLocaleLowerCase("tr-TR").includes(String(form.warehouseId).replace(/^WH-[^-]+-/, "").toLocaleLowerCase("tr-TR")));
  function set(key, value) { setForm((current) => ({ ...current, [key]: value })); setEvaluation(null); }
  async function check() { try { setEvaluation(await evaluateRecruitment({ warehouse_id: form.warehouseId, position_code: form.positionCode, quantity: form.quantity })); } catch (err) { setError(err.message); } }
  async function submit(event) {
    event.preventDefault();
    if (!form.justification.trim()) { setError(m("workJustificationRequired")); return; }
    if (form.reasonCode === "PLANNED_DEPARTURE" && (!departure.employeeId || !file)) { setError(m("plannedDepartureEvidenceRequired")); return; }
    setBusy(true);
    try {
      const payload = { warehouse_id: form.warehouseId, position_code: form.positionCode, quantity: Number(form.quantity), employment_type: form.employmentType, reason_code: form.reasonCode, needed_by: form.neededBy, justification: form.justification.trim(), planned_departure: form.reasonCode === "PLANNED_DEPARTURE" ? { employee_id: departure.employeeId, employee_name: departure.employeeName, last_working_date: departure.lastWorkingDate, departure_type: departure.departureType } : null };
      let created = await createRecruitmentRequest(payload);
      if (file) created = await uploadRecruitmentEvidence(created.id, file);
      await onDone(created);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <section className="rec-content rec-form-layout"><form className="rec-panel rec-form" onSubmit={submit}><div className="rec-panel-head"><div><span className="rec-kicker">{m("headcountSignal")}</span><h2>{m("newHeadcount")}</h2></div></div><div className="rec-form-grid"><label>{m("depot")}<select value={form.warehouseId} onChange={(e) => set("warehouseId", e.target.value)}>{(data?.norms || []).map((norm) => <option key={norm.id} value={norm.warehouse}>{norm.warehouse}</option>)}</select></label><label>{m("position")}<select value={form.positionCode} onChange={(e) => set("positionCode", e.target.value)}>{POSITIONS.map(([value, labelKey]) => <option key={value} value={value}>{m(labelKey)}</option>)}</select></label><label>{m("requestQty")}<input type="number" min="1" max="20" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} /></label><label>{m("employmentType")}<select value={form.employmentType} onChange={(e) => set("employmentType", e.target.value)}><option value="FULL_TIME">{m("fullTime")}</option><option value="PART_TIME">{m("partTime")}</option><option value="TEMPORARY">{m("temporary")}</option></select></label><label>{m("requestReason")}<select value={form.reasonCode} onChange={(e) => set("reasonCode", e.target.value)}>{REASONS.map(([value, labelKey]) => <option key={value} value={value}>{m(labelKey)}</option>)}</select></label><label>{m("neededBy")}<input type="date" min={isoToday()} value={form.neededBy} onChange={(e) => set("neededBy", e.target.value)} /></label></div>{form.reasonCode === "PLANNED_DEPARTURE" && <fieldset className="rec-departure"><legend>{m("plannedDepartureEvidence")}</legend><div className="rec-form-grid"><label>{m("departingEmployee")}<select value={departure.employeeId} onChange={(e) => { const person = warehousePeople.find((item) => item.employeeId === e.target.value); setDeparture((current) => ({ ...current, employeeId: e.target.value, employeeName: person?.fullName || person?.name || "" })); }}><option value="">{m("selectEmployee")}</option>{warehousePeople.map((person) => <option key={person.employeeId} value={person.employeeId}>{person.fullName || person.name} · {person.employeeId}</option>)}</select></label><label>{m("lastWorkingDate")}<input type="date" value={departure.lastWorkingDate} onChange={(e) => setDeparture((current) => ({ ...current, lastWorkingDate: e.target.value }))} /></label><label className="rec-file">{m("resignationEvidence")}<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] || null)} /><span>{file ? file.name : m("chooseFile")}</span></label></div></fieldset>}<label className="rec-full">{m("workJustification")} <small>{m("auditStored")}</small><textarea value={form.justification} onChange={(e) => set("justification", e.target.value)} placeholder={m("justificationPlaceholder")} /></label><div className="rec-form-actions"><button type="button" className="rec-secondary" onClick={check}>{m("checkNormActual")}</button><button type="submit" className="rec-primary" disabled={busy}>{busy ? m("saving") : m("sendApproval")}</button></div></form><aside>{evaluation ? <EvaluationCard evaluation={evaluation} m={m} /> : <div className="rec-info-card"><Users size={24} /><h3>{m("decisionVisibility")}</h3><p>{m("decisionVisibilityDesc")}</p><ul><li>{m("actualLayer")}</li><li>{m("masterFallback")}</li><li>{m("evidenceMandatory")}</li></ul></div>}</aside></section>;
}

function Settings({ data, refresh, flash, setError, m, locale }) {
  const settings = data?.settings || {}; const [hr, setHr] = useState((settings.hrRecipients || []).join("\n")); const [partners, setPartners] = useState((settings.partnerRecipients || []).join("\n")); const [normQuery, setNormQuery] = useState("");
  async function save() {
    try {
      await saveRecruitmentSettings({ hr_recipients: splitEmails(hr), partner_recipients: splitEmails(partners), default_manager_capacity: settings.defaultManagerCapacity || 1, warehouse_manager_capacity: settings.warehouseManagerCapacity || { "Fulya (İstanbul)": 2 }, counted_position_codes: settings.countedPositionCodes || ["STORE_STAFF", "ASSISTANT_MANAGER", "STORE_SUPPORT"] });
      flash(m("settingsSaved")); await refresh();
    } catch (err) { setError(err.message); }
  }
  const norms = (data?.norms || []).filter((row) => row.warehouse.toLocaleLowerCase(locale).includes(normQuery.toLocaleLowerCase(locale)));
  return <section className="rec-content rec-settings-grid"><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">{m("notificationRouting")}</span><h2>{m("hrPartnerRecipients")}</h2></div></div><label>{m("hrEmails")} <small>{m("onePerLine")}</small><textarea value={hr} onChange={(e) => setHr(e.target.value)} placeholder={HR_EMAIL_EXAMPLE} /></label><label>{m("partnerRecruiters")}<textarea value={partners} onChange={(e) => setPartners(e.target.value)} placeholder={PARTNER_EMAIL_EXAMPLE} /></label><button className="rec-primary" onClick={save}><Settings2 size={17} /> {m("saveSettings")}</button><p className="rec-config-note">{m("smtpNote")}</p></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">{m("staffingNorms")}</span><h2>{m("depotNorms")}</h2></div><label className="rec-search"><Search size={17} /><input value={normQuery} onChange={(e) => setNormQuery(e.target.value)} placeholder={m("searchDepot")} /></label></div><div className="rec-norm-list">{norms.slice(0, 30).map((row) => <NormRow key={row.id} row={row} done={async () => { flash(m("normUpdated", { warehouse: row.warehouse })); await refresh(); }} error={setError} m={m} />)}</div></div></section>;
}

function NormRow({ row, done, error, m }) {
  const [value, setValue] = useState(row.norm); const [editing, setEditing] = useState(false);
  async function save() { try { await saveRecruitmentNorm({ warehouse: row.warehouse, norm: Number(value), regional_manager: row.regionalManager || "", regional_executive: row.regionalExecutive || "", active: row.active !== false }); setEditing(false); await done(); } catch (err) { error(err.message); } }
  return <article><div><strong>{row.warehouse}</strong><small>{row.regionalManager} · {row.regionalExecutive}</small></div>{editing ? <><input type="number" min="0" max="500" value={value} onChange={(e) => setValue(e.target.value)} /><button onClick={save}><Check size={15} /></button></> : <><b>{row.norm}</b><button onClick={() => setEditing(true)}>{m("edit")}</button></>}</article>;
}