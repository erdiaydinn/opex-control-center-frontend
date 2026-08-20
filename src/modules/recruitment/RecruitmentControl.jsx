import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft, BadgeCheck, BellRing, Building2, Check, ChevronRight, CircleAlert,
  FileCheck2, Mail, Moon, Plus, RefreshCw, Search, Settings2, Sun, UserPlus, Users, X,
} from "lucide-react";
import { useAuth } from "../../auth/AuthContext.jsx";
import {
  createRecruitmentRequest, decideRecruitmentRequest, downloadRecruitmentEvidence,
  evaluateRecruitment, loadRecruitment, retryRecruitmentEmail, saveRecruitmentNorm,
  saveRecruitmentSettings, uploadRecruitmentEvidence,
} from "./recruitmentApi.js";
import RecruitmentActualPanel from "./RecruitmentActualPanel.jsx";
import RecruitmentCandidateWorkspace from "./RecruitmentCandidateWorkspace.jsx";
import "./recruitment.css";

const POSITIONS = [
  ["STORE_STAFF", "Mağaza Görevlisi"], ["ASSISTANT_MANAGER", "Mağaza Müdür Yardımcısı"],
  ["STORE_SUPPORT", "Mağaza Destek Görevlisi"], ["STORE_MANAGER", "Mağaza Müdürü"],
];
const REASONS = [
  ["NORM_GAP", "Norm açığı"], ["PLANNED_DEPARTURE", "Planlı istifa / ayrılış"],
  ["NEW_WAREHOUSE", "Yeni depo / kapasite"], ["OTHER", "Diğer"],
];
const STATUS = {
  PENDING_APPROVAL: ["Onay bekliyor", "warning"], EVIDENCE_REQUIRED: ["Belge bekliyor", "danger"],
  APPROVED: ["Onaylandı", "success"], REJECTED: ["Reddedildi", "danger"], SOURCING: ["Aday aranıyor", "info"],
  PARTIALLY_FILLED: ["Kısmen doldu", "info"], FILLED: ["Dolduruldu", "success"],
};

function isoToday() { return new Date().toISOString().slice(0, 10); }
function addDays(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }
function splitEmails(value) { return [...new Set(value.split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean))]; }

function StatusPill({ value }) {
  const [label, tone] = STATUS[value] || [value, "neutral"];
  return <span className={`rec-status ${tone}`}>{label}</span>;
}

function Metric({ icon: Icon, label, value, detail, tone = "pink" }) {
  return <article className={`rec-metric tone-${tone}`}><span><Icon size={19} /></span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>;
}

export default function RecruitmentControl() {
  const navigate = useNavigate();
  const { user, canAction } = useAuth();
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

  const requests = useMemo(() => (data?.requests || []).filter((row) => [row.id, row.warehouseName, row.positionLabel, row.requestedByName].join(" ").toLocaleLowerCase("tr-TR").includes(query.toLocaleLowerCase("tr-TR"))), [data, query]);
  const canApprove = canAction("recruitment", "approveRecruitmentRequest");

  async function decide(decision) {
    if (!selected || !decisionNote.trim()) { setError("Karar açıklaması boş bırakılamaz."); return; }
    try { await decideRecruitmentRequest(selected.id, decision, decisionNote.trim()); setDecisionNote(""); flash(decision === "APPROVED" ? "Talep onaylandı ve e-posta kuyruğu oluşturuldu." : "Talep gerekçesiyle reddedildi."); await refreshSelected(); }
    catch (err) { setError(err.message); }
  }

  const decisionOpen = selected && ["PENDING_APPROVAL", "EVIDENCE_REQUIRED"].includes(selected.status);

  return (
    <main className={`rec-page ${dark ? "is-dark" : ""}`}>
      <div className="rec-grid-bg" />
      <section className="rec-shell">
        <header className="rec-topbar">
          <div className="rec-brand"><button onClick={() => navigate("/")}><ArrowLeft size={18} /></button><div className="rec-logo"><UserPlus size={21} /></div><div><span>PEOPLE OPERATIONS</span><strong>İşe Alım Talepleri</strong></div></div>
          <div className="rec-actions"><span className="rec-user"><strong>{user?.name || user?.email}</strong><small>{user?.role || "Yetkili kullanıcı"}</small></span><button onClick={toggleTheme}>{dark ? <Sun size={16} /> : <Moon size={16} />}{dark ? "Açık" : "Koyu"}</button><button onClick={refresh}><RefreshCw size={16} /> Yenile</button></div>
        </header>

        <section className="rec-hero">
          <div><span className="rec-eyebrow"><BadgeCheck size={15} /> Norm + HR Actual + lifecycle kontrollü işe alım</span><h1>Doğru depoya,<br /><em>doğru zamanda</em> doğru ekip.</h1><p>Resmi HR Actual, Employee Master, açık talep, planlı ayrılış ve adaydan ilk vardiyaya kadar yaşam döngüsünü tek kararda birleştirir.</p></div>
          <aside><span>Karar motoru</span><strong>Norm × Actual × Committed</strong><div><Check size={17} /> HR Actual mutabakatı görünür</div><div><Check size={17} /> Employee Master fail-safe authority</div><div><Check size={17} /> Hire → ilk vardiya atomik lifecycle</div></aside>
        </section>

        {error && <div className="rec-alert error"><CircleAlert size={18} />{error}<button onClick={() => setError("")}><X size={16} /></button></div>}
        {notice && <div className="rec-alert success"><Check size={18} />{notice}</div>}

        <nav className="rec-tabs">
          {[['overview','Genel Bakış'],['staffing','Norm & Actual'],['requests','Talepler'],['new','Yeni Talep'],['settings','Ayarlar ve Norm']].map(([key,label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}
        </nav>

        {loading ? <section className="rec-loading">İşe alım verileri hazırlanıyor…</section> : <>
          {tab === "overview" && <Overview data={data} setTab={setTab} />}
          {tab === "staffing" && <RecruitmentActualPanel data={data} refresh={refresh} flash={flash} setError={setError} />}
          {tab === "requests" && <Requests rows={requests} query={query} setQuery={setQuery} select={setSelected} outbox={data?.emailOutbox || []} retry={async (id) => { try { await retryRecruitmentEmail(id); await refresh(); } catch (err) { setError(err.message); } }} />}
          {tab === "new" && <NewRequest data={data} onDone={async () => { flash("Talep kaydedildi ve onay akışına gönderildi."); await refresh(); setTab("requests"); }} setError={setError} />}
          {tab === "settings" && <Settings data={data} refresh={refresh} flash={flash} setError={setError} />}
        </>}
      </section>

      {selected && <div className="rec-modal-backdrop" onMouseDown={() => setSelected(null)}><section className="rec-modal rec-modal-lifecycle" onMouseDown={(event) => event.stopPropagation()}><button className="rec-modal-close" onClick={() => setSelected(null)}><X /></button><span className="rec-kicker">VACANCY LIFECYCLE</span><h2>{selected.warehouseName}</h2><p className="rec-modal-lead">{selected.positionLabel} · {selected.quantity} kişi · {selected.id}</p><EvaluationCard evaluation={selected.currentStaffing || selected} />{selected.evidence && <button className="rec-secondary wide" onClick={() => downloadRecruitmentEvidence(selected.id, selected.evidence.originalName)}><FileCheck2 size={17} /> İstifa belgesini indir</button>}{decisionOpen ? <><label>Karar açıklaması <small>Karar audit kaydına gerekçesiyle yazılır</small><textarea value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} placeholder="Norm, HR Actual, Employee Master ve operasyon ihtiyacına göre karar gerekçesi…" /></label>{canApprove ? <div className="rec-decision-actions"><button className="reject" onClick={() => decide("REJECTED")}><X size={17} /> Reddet</button><button className="approve" onClick={() => decide("APPROVED")}><Check size={17} /> Onayla ve bildir</button></div> : <div className="rec-alert">Bu kullanıcı yalnızca talebi görüntüleyebilir.</div>}</> : <RecruitmentCandidateWorkspace request={selected} canApprove={canApprove} onChanged={refreshSelected} flash={flash} setError={setError} />}</section></div>}
    </main>
  );
}

function Overview({ data, setTab }) {
  const dash = data?.dashboard || {};
  const snapshot = data?.actualSnapshot;
  return <section className="rec-content"><div className="rec-metrics"><Metric icon={BellRing} label="Onay bekleyen" value={dash.pending || 0} detail="Karar kuyruğundaki talepler" /><Metric icon={FileCheck2} label="HR Actual" value={snapshot?.activeRows ?? "—"} detail={snapshot ? `${snapshot.activeFte} FTE · eşleşme %${snapshot.matchRate}` : "Resmi HR snapshot bekliyor"} tone="amber" /><Metric icon={BadgeCheck} label="Onaylanan" value={dash.approved || 0} detail="Aday arama sürecine hazır" tone="green" /><Metric icon={Building2} label="Norm açığı" value={dash.normGapWarehouses || 0} detail="Employee Master + açık talebe göre" tone="purple" /></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">HEADCOUNT SIGNAL</span><h2>En yüksek işe alım ihtiyacı</h2></div><button className="rec-secondary" onClick={() => setTab("staffing")}>Norm & Actual mutabakatı</button><button className="rec-primary" onClick={() => setTab("new")}><Plus size={17} /> Yeni talep</button></div><div className="rec-gap-grid">{(dash.warehouseRows || []).filter((row) => row.available > 0).slice(0, 8).map((row) => <article key={row.warehouseName}><div><strong>{row.warehouseName}</strong><span>{row.normRecord?.regionalExecutive || "BY eşleşmesi bekliyor"}</span></div><b>{row.available}</b><small>Norm {row.capacity} · HR {row.hrActual ?? "—"} · EM {row.active} · Açık {row.openPositions}</small></article>)}</div></div></section>;
}

function Requests({ rows, query, setQuery, select, outbox, retry }) {
  return <section className="rec-content"><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">APPROVAL FLOW</span><h2>İşe alım talepleri</h2></div><label className="rec-search"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Depo, talep no veya pozisyon ara…" /></label></div><div className="rec-table-wrap"><table><thead><tr><th>Talep / Depo</th><th>Pozisyon</th><th>Norm / Actual</th><th>İhtiyaç</th><th>Durum</th><th></th></tr></thead><tbody>{rows.map((row) => { const staffing = row.currentStaffing || row; return <tr key={row.id}><td><strong>{row.warehouseName}</strong><small>{row.id} · {row.requestedByName}</small></td><td>{row.positionLabel}<small>{row.quantity} kişi</small></td><td><strong>{staffing.active} / {staffing.capacity}</strong><small>HR {staffing.hrActual ?? "—"} · Açık {staffing.openPositions} · Proj. {staffing.projected}</small></td><td>{row.neededBy}<small>{row.reasonCode === "PLANNED_DEPARTURE" ? "Planlı ayrılış" : "Operasyon ihtiyacı"}</small></td><td><StatusPill value={row.status} /></td><td><button className="rec-row-action" onClick={() => select(row)}>İncele <ChevronRight size={16} /></button></td></tr>; })}</tbody></table>{!rows.length && <div className="rec-empty">Arama ölçütüne uygun talep yok.</div>}</div></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">DELIVERY OUTBOX</span><h2>İK ve partner bildirimleri</h2></div></div><div className="rec-outbox">{outbox.map((row) => <article key={row.id}><Mail size={18} /><div><strong>{row.recipientGroup} · {row.requestId}</strong><small>{row.payload?.recipients?.join(", ") || "Alıcı tanımlanmadı"}</small></div><StatusPill value={row.status} />{row.status !== "DELIVERED" && <button onClick={() => retry(row.id)}>Yeniden dene</button>}</article>)}{!outbox.length && <div className="rec-empty">Henüz e-posta kuyruğu kaydı yok.</div>}</div></div></section>;
}

function EvaluationCard({ evaluation }) {
  if (!evaluation) return null;
  const approved = evaluation.recommendation === "APPROVE";
  return <div className={`rec-evaluation ${approved ? "approve" : evaluation.recommendation === "REJECT" ? "reject" : "review"}`}><div><span>Karar önerisi</span><strong>{approved ? "Norm uygun" : evaluation.recommendation === "REJECT" ? "Norm üstü" : "Manuel inceleme"}</strong><p>{evaluation.recommendationReason}</p><small>{evaluation.hrActualAsOf ? `HR Actual ${evaluation.hrActualAsOf} · karar authority: Employee Master` : "HR Actual snapshot yüklenene kadar Employee Master authority"}</small></div><div className="rec-eval-numbers"><span><small>Kapasite</small><b>{evaluation.capacity}</b></span><span><small>HR Actual</small><b>{evaluation.hrActual ?? "—"}</b></span><span><small>EM Actual</small><b>{evaluation.active}</b></span><span><small>Açık</small><b>{evaluation.openPositions}</b></span><span><small>Boşluk</small><b>{evaluation.available}</b></span></div></div>;
}

function NewRequest({ data, onDone, setError }) {
  const firstWarehouse = data?.norms?.[0]?.warehouse || data?.warehouses?.[0]?.id || "";
  const [form, setForm] = useState({ warehouseId: firstWarehouse, positionCode: "STORE_STAFF", quantity: 1, employmentType: "FULL_TIME", reasonCode: "NORM_GAP", neededBy: addDays(21), justification: "" });
  const [departure, setDeparture] = useState({ employeeId: "", employeeName: "", lastWorkingDate: addDays(14), departureType: "RESIGNATION" });
  const [file, setFile] = useState(null); const [evaluation, setEvaluation] = useState(null); const [busy, setBusy] = useState(false);
  const warehousePeople = (data?.people || []).filter((person) => String(person.warehouseId || person.warehouse || "").toLocaleLowerCase("tr-TR").includes(String(form.warehouseId).replace(/^WH-[^-]+-/, "").toLocaleLowerCase("tr-TR")));
  function set(key, value) { setForm((current) => ({ ...current, [key]: value })); setEvaluation(null); }
  async function check() { try { setEvaluation(await evaluateRecruitment({ warehouse_id: form.warehouseId, position_code: form.positionCode, quantity: form.quantity })); } catch (err) { setError(err.message); } }
  async function submit(event) { event.preventDefault(); if (!form.justification.trim()) { setError("İş gerekçesi boş bırakılamaz."); return; } if (form.reasonCode === "PLANNED_DEPARTURE" && (!departure.employeeId || !file)) { setError("Planlı ayrılışta personel ve istifa belgesi zorunludur."); return; } setBusy(true); try { const payload = { warehouse_id: form.warehouseId, position_code: form.positionCode, quantity: Number(form.quantity), employment_type: form.employmentType, reason_code: form.reasonCode, needed_by: form.neededBy, justification: form.justification.trim(), planned_departure: form.reasonCode === "PLANNED_DEPARTURE" ? { employee_id: departure.employeeId, employee_name: departure.employeeName, last_working_date: departure.lastWorkingDate, departure_type: departure.departureType } : null }; let created = await createRecruitmentRequest(payload); if (file) created = await uploadRecruitmentEvidence(created.id, file); await onDone(created); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  return <section className="rec-content rec-form-layout"><form className="rec-panel rec-form" onSubmit={submit}><div className="rec-panel-head"><div><span className="rec-kicker">NEW HEADCOUNT REQUEST</span><h2>Yeni işe alım talebi</h2></div></div><div className="rec-form-grid"><label>Depo<select value={form.warehouseId} onChange={(e) => set("warehouseId", e.target.value)}>{(data?.norms || []).map((norm) => <option key={norm.id} value={norm.warehouse}>{norm.warehouse}</option>)}</select></label><label>Pozisyon<select value={form.positionCode} onChange={(e) => set("positionCode", e.target.value)}>{POSITIONS.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Talep adedi<input type="number" min="1" max="20" value={form.quantity} onChange={(e) => set("quantity", e.target.value)} /></label><label>Çalışma tipi<select value={form.employmentType} onChange={(e) => set("employmentType", e.target.value)}><option value="FULL_TIME">Tam zamanlı</option><option value="PART_TIME">Yarı zamanlı</option><option value="TEMPORARY">Geçici</option></select></label><label>Talep nedeni<select value={form.reasonCode} onChange={(e) => set("reasonCode", e.target.value)}>{REASONS.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>İhtiyaç tarihi<input type="date" min={isoToday()} value={form.neededBy} onChange={(e) => set("neededBy", e.target.value)} /></label></div>{form.reasonCode === "PLANNED_DEPARTURE" && <fieldset className="rec-departure"><legend>Planlı ayrılış ve istifa belgesi</legend><div className="rec-form-grid"><label>Ayrılacak çalışan<select value={departure.employeeId} onChange={(e) => { const person = warehousePeople.find((item) => item.employeeId === e.target.value); setDeparture((current) => ({ ...current, employeeId: e.target.value, employeeName: person?.fullName || person?.name || "" })); }}><option value="">Çalışan seçin</option>{warehousePeople.map((person) => <option key={person.employeeId} value={person.employeeId}>{person.fullName || person.name} · {person.employeeId}</option>)}</select></label><label>Son çalışma tarihi<input type="date" value={departure.lastWorkingDate} onChange={(e) => setDeparture((current) => ({ ...current, lastWorkingDate: e.target.value }))} /></label><label className="rec-file">İstifa belgesi (PDF/JPG/PNG)<input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] || null)} /><span>{file ? file.name : "Belge seçin · Maks. 10 MB"}</span></label></div></fieldset>}<label className="rec-full">İş gerekçesi <small>Karar kaydında saklanır</small><textarea value={form.justification} onChange={(e) => set("justification", e.target.value)} placeholder="Operasyon ihtiyacını ve pozisyon gerekçesini açıklayın…" /></label><div className="rec-form-actions"><button type="button" className="rec-secondary" onClick={check}>Norm + Actual kontrol et</button><button type="submit" className="rec-primary" disabled={busy}>{busy ? "Kaydediliyor…" : "Onaya gönder"}</button></div></form><aside>{evaluation ? <EvaluationCard evaluation={evaluation} /> : <div className="rec-info-card"><Users size={24} /><h3>Karar öncesi görünürlük</h3><p>Norm, HR Actual, Employee Master, müdür kapasitesi, açık talepler ve planlı ayrılış birlikte görünür.</p><ul><li>HR Actual kararın resmi mutabakat katmanıdır.</li><li>Mutabakat tamamlanana kadar Employee Master fail-safe authority kalır.</li><li>Önden talepte istifa belgesi zorunludur.</li></ul></div>}</aside></section>;
}

function Settings({ data, refresh, flash, setError }) {
  const settings = data?.settings || {}; const [hr, setHr] = useState((settings.hrRecipients || []).join("\n")); const [partners, setPartners] = useState((settings.partnerRecipients || []).join("\n")); const [normQuery, setNormQuery] = useState("");
  async function save() { try { await saveRecruitmentSettings({ hr_recipients: splitEmails(hr), partner_recipients: splitEmails(partners), default_manager_capacity: settings.defaultManagerCapacity || 1, warehouse_manager_capacity: settings.warehouseManagerCapacity || { "Fulya (İstanbul)": 2 }, counted_position_codes: settings.countedPositionCodes || ["STORE_STAFF","ASSISTANT_MANAGER","STORE_SUPPORT"] }); flash("İşe alım bildirim ayarları kaydedildi."); await refresh(); } catch (err) { setError(err.message); } }
  const norms = (data?.norms || []).filter((row) => row.warehouse.toLocaleLowerCase("tr-TR").includes(normQuery.toLocaleLowerCase("tr-TR")));
  return <section className="rec-content rec-settings-grid"><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">NOTIFICATION ROUTING</span><h2>İK ve partner alıcıları</h2></div></div><label>İK e-posta adresleri <small>Her satıra bir adres</small><textarea value={hr} onChange={(e) => setHr(e.target.value)} placeholder="ik@yemeksepeti.com" /></label><label>Third-party / işe alım partnerleri<textarea value={partners} onChange={(e) => setPartners(e.target.value)} placeholder="partner@example.com" /></label><button className="rec-primary" onClick={save}><Settings2 size={17} /> Ayarları kaydet</button><p className="rec-config-note">SMTP parolası bu ekrana yazılmaz; yalnızca sunucu `.env` ayarlarında saklanır.</p></div><div className="rec-panel"><div className="rec-panel-head"><div><span className="rec-kicker">STAFFING NORMS</span><h2>Depo normları</h2></div><label className="rec-search"><Search size={17} /><input value={normQuery} onChange={(e) => setNormQuery(e.target.value)} placeholder="Depo ara…" /></label></div><div className="rec-norm-list">{norms.slice(0, 30).map((row) => <NormRow key={row.id} row={row} done={async () => { flash(`${row.warehouse} normu güncellendi.`); await refresh(); }} error={setError} />)}</div></div></section>;
}

function NormRow({ row, done, error }) {
  const [value, setValue] = useState(row.norm); const [editing, setEditing] = useState(false);
  async function save() { try { await saveRecruitmentNorm({ warehouse: row.warehouse, norm: Number(value), regional_manager: row.regionalManager || "", regional_executive: row.regionalExecutive || "", active: row.active !== false }); setEditing(false); await done(); } catch (err) { error(err.message); } }
  return <article><div><strong>{row.warehouse}</strong><small>{row.regionalManager} · {row.regionalExecutive}</small></div>{editing ? <><input type="number" min="0" max="500" value={value} onChange={(e) => setValue(e.target.value)} /><button onClick={save}><Check size={15} /></button></> : <><b>{row.norm}</b><button onClick={() => setEditing(true)}>Düzenle</button></>}</article>;
}
