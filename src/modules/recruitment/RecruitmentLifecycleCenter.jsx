import React, { useEffect, useMemo, useState } from "react";
import {
  BellRing,
  BriefcaseBusiness,
  CheckCircle2,
  Clipboard,
  DoorOpen,
  RefreshCw,
  Send,
  ShieldCheck,
  UserRoundCheck,
  UsersRound,
  X,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { loadRecruitment } from "./recruitmentApi.js";
import {
  addCandidateToTalentPool,
  closeOffboardingCase,
  createOffboardingCase,
  decideOfferApproval,
  issueApprovedOfferCapability,
  listLifecycleCommunications,
  listOffboardingCases,
  listOfferApprovals,
  listTalentPool,
  queueCandidateCommunication,
  updateOffboardingTask,
  withdrawTalentMembership,
} from "./recruitmentLifecycleApi.js";
import "./recruitmentLifecycleCenter.css";

const COPY = {
  tr: {
    open: "Lifecycle Center", title: "İşe alım yaşam döngüsü", desc: "Teklif onayı, aday iletişimi, talent pool ve offboarding tek yönetim yüzeyinde.",
    approvals: "Teklif onayları", communications: "Aday iletişimi", talent: "Talent pool", offboarding: "Offboarding", refresh: "Yenile", close: "Kapat",
    pending: "Bekliyor", approved: "Onaylandı", rejected: "Reddedildi", sent: "Gönderildi", failed: "Başarısız", queued: "Kuyrukta", claimed: "İşleniyor",
    approve: "Onayla", reject: "Reddet", reason: "Karar gerekçesi", issue: "Güvenli aday linki üret", copy: "Linki kopyala", copied: "Aday linki panoya kopyalandı.",
    quorum: "Onay", creator: "Hazırlayan", expires: "Geçerlilik", noApprovals: "Onay bekleyen teklif yok.", noCommunications: "İletişim kaydı yok.", noTalent: "Talent pool kaydı yok.", noOffboarding: "Offboarding kaydı yok.",
    queueReminder: "Hatırlatma kuyruğa al", candidate: "Aday", messageType: "Mesaj tipi", channel: "Kanal", template: "Template", selectCandidate: "Aday seçin",
    addTalent: "Talent pool'a ekle", pool: "Pool", tags: "Etiketler", consentRef: "Consent kayıt referansı", consentDays: "Consent gün", withdraw: "Consent'i geri çek",
    newOffboarding: "Offboarding başlat", employee: "Çalışan ID", effective: "Ayrılış zamanı", reasonCode: "Ayrılış nedeni", note: "Not", create: "Oluştur", owner: "Sahip", complete: "Tamamla", block: "Bloke et", waive: "Waive", closeCase: "Case kapat", readyToClose: "Kapatmaya hazır",
    secure: "PII-minimized projection", error: "İşlem tamamlanamadı.", requiredReason: "Ret/waive/blokaj için gerekçe girin.",
  },
  en: {
    open: "Lifecycle Center", title: "Hiring lifecycle", desc: "Offer approvals, candidate communications, talent pools and offboarding in one governed workspace.",
    approvals: "Offer approvals", communications: "Candidate communications", talent: "Talent pool", offboarding: "Offboarding", refresh: "Refresh", close: "Close",
    pending: "Pending", approved: "Approved", rejected: "Rejected", sent: "Sent", failed: "Failed", queued: "Queued", claimed: "Processing",
    approve: "Approve", reject: "Reject", reason: "Decision rationale", issue: "Generate secure candidate link", copy: "Copy link", copied: "Candidate link copied.",
    quorum: "Approvals", creator: "Creator", expires: "Expires", noApprovals: "No offers awaiting approval.", noCommunications: "No communication records.", noTalent: "No talent pool records.", noOffboarding: "No offboarding cases.",
    queueReminder: "Queue reminder", candidate: "Candidate", messageType: "Message type", channel: "Channel", template: "Template", selectCandidate: "Select candidate",
    addTalent: "Add to talent pool", pool: "Pool", tags: "Tags", consentRef: "Consent record reference", consentDays: "Consent days", withdraw: "Withdraw consent",
    newOffboarding: "Start offboarding", employee: "Employee ID", effective: "Effective at", reasonCode: "Reason", note: "Note", create: "Create", owner: "Owner", complete: "Complete", block: "Block", waive: "Waive", closeCase: "Close case", readyToClose: "Ready to close",
    secure: "PII-minimized projection", error: "Operation failed.", requiredReason: "Provide a rationale for reject/waive/block.",
  },
  de: {
    open: "Lifecycle Center", title: "Recruiting-Lebenszyklus", desc: "Angebotsfreigaben, Kandidatenkommunikation, Talent Pool und Offboarding in einem gesteuerten Bereich.",
    approvals: "Angebotsfreigaben", communications: "Kandidatenkommunikation", talent: "Talent Pool", offboarding: "Offboarding", refresh: "Aktualisieren", close: "Schließen",
    pending: "Offen", approved: "Freigegeben", rejected: "Abgelehnt", sent: "Gesendet", failed: "Fehlgeschlagen", queued: "Warteschlange", claimed: "In Bearbeitung",
    approve: "Freigeben", reject: "Ablehnen", reason: "Begründung", issue: "Sicheren Kandidatenlink erzeugen", copy: "Link kopieren", copied: "Kandidatenlink kopiert.",
    quorum: "Freigaben", creator: "Erstellt von", expires: "Gültig bis", noApprovals: "Keine offenen Angebote.", noCommunications: "Keine Kommunikation.", noTalent: "Keine Talent-Pool-Einträge.", noOffboarding: "Keine Offboarding-Fälle.",
    queueReminder: "Erinnerung einreihen", candidate: "Kandidat", messageType: "Nachrichtentyp", channel: "Kanal", template: "Vorlage", selectCandidate: "Kandidat wählen",
    addTalent: "Zum Talent Pool", pool: "Pool", tags: "Tags", consentRef: "Consent-Referenz", consentDays: "Consent-Tage", withdraw: "Consent widerrufen",
    newOffboarding: "Offboarding starten", employee: "Mitarbeiter-ID", effective: "Wirksam ab", reasonCode: "Grund", note: "Notiz", create: "Erstellen", owner: "Verantwortlich", complete: "Abschließen", block: "Blockieren", waive: "Erlassen", closeCase: "Fall schließen", readyToClose: "Bereit zum Schließen",
    secure: "PII-minimierte Ansicht", error: "Vorgang fehlgeschlagen.", requiredReason: "Begründung für Ablehnung/Erlass/Blockierung erforderlich.",
  },
  ar: {
    open: "مركز دورة الحياة", title: "دورة حياة التوظيف", desc: "موافقات العروض وتواصل المرشحين ومجموعة المواهب وإنهاء الخدمة في مساحة محكومة واحدة.",
    approvals: "موافقات العرض", communications: "تواصل المرشح", talent: "مجموعة المواهب", offboarding: "إنهاء الخدمة", refresh: "تحديث", close: "إغلاق",
    pending: "قيد الانتظار", approved: "موافق", rejected: "مرفوض", sent: "مرسل", failed: "فشل", queued: "في الانتظار", claimed: "قيد المعالجة",
    approve: "موافقة", reject: "رفض", reason: "سبب القرار", issue: "إنشاء رابط مرشح آمن", copy: "نسخ الرابط", copied: "تم نسخ رابط المرشح.",
    quorum: "الموافقات", creator: "المنشئ", expires: "ينتهي", noApprovals: "لا توجد عروض بانتظار الموافقة.", noCommunications: "لا توجد سجلات تواصل.", noTalent: "لا توجد سجلات مواهب.", noOffboarding: "لا توجد حالات إنهاء خدمة.",
    queueReminder: "إضافة تذكير", candidate: "المرشح", messageType: "نوع الرسالة", channel: "القناة", template: "القالب", selectCandidate: "اختر المرشح",
    addTalent: "إضافة إلى مجموعة المواهب", pool: "المجموعة", tags: "الوسوم", consentRef: "مرجع الموافقة", consentDays: "أيام الموافقة", withdraw: "سحب الموافقة",
    newOffboarding: "بدء إنهاء الخدمة", employee: "معرف الموظف", effective: "تاريخ السريان", reasonCode: "السبب", note: "ملاحظة", create: "إنشاء", owner: "المالك", complete: "إكمال", block: "حظر", waive: "إعفاء", closeCase: "إغلاق الحالة", readyToClose: "جاهز للإغلاق",
    secure: "عرض بدون بيانات شخصية", error: "تعذر إكمال العملية.", requiredReason: "أدخل سبب الرفض/الإعفاء/الحظر.",
  },
};

const TABS = ["approvals", "communications", "talent", "offboarding"];
const STATUS_CLASS = { PENDING: "neutral", QUEUED: "neutral", CLAIMED: "info", APPROVED: "success", SENT: "success", CLOSED: "success", READY_TO_CLOSE: "success", FAILED: "danger", REJECTED: "danger", BLOCKED: "danger", WITHDRAWN: "muted", EXPIRED: "muted" };
function stateLabel(value, c) { return c[String(value || "").toLowerCase()] || value || "—"; }
function formatDate(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString(); }
function localDateTime(days = 1) { const d = new Date(Date.now() + days * 86400000); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); }

export default function RecruitmentLifecycleCenter() {
  const { canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const c = COPY[locale] || COPY.en;
  const canView = canAction("recruitment", "viewRecruitment");
  const canApproveOffer = canAction("recruitment", "approveRecruitmentOffer");
  const canIssueOffer = canAction("recruitment", "approveRecruitmentRequest");
  const canCommunicate = canAction("recruitment", "manageRecruitmentCommunications");
  const canTalent = canAction("recruitment", "manageRecruitmentTalentPool");
  const canOffboard = canAction("recruitment", "manageRecruitmentOffboarding");
  const canWaive = canAction("recruitment", "waiveRecruitmentOffboarding");
  const canCloseOffboard = canAction("recruitment", "closeRecruitmentOffboarding");

  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("approvals");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [bootstrap, setBootstrap] = useState(null);
  const [approvals, setApprovals] = useState([]);
  const [communications, setCommunications] = useState([]);
  const [talent, setTalent] = useState([]);
  const [offboarding, setOffboarding] = useState([]);
  const [decisionNotes, setDecisionNotes] = useState({});
  const [taskNotes, setTaskNotes] = useState({});
  const [secureLinks, setSecureLinks] = useState({});
  const [communicationForm, setCommunicationForm] = useState({ candidateKey: "", messageType: "PROCESS_UPDATE", channel: "EMAIL", templateKey: "candidate-process-update-v1" });
  const [talentForm, setTalentForm] = useState({ candidateKey: "", poolKey: "STORE_STAFF_TR", tags: "", consentRef: "", consentDays: 365 });
  const [offboardForm, setOffboardForm] = useState({ employeeId: "", effectiveAt: localDateTime(1), reasonCode: "RESIGNATION", note: "" });

  const candidates = useMemo(() => (bootstrap?.requests || []).flatMap((request) => (request.candidates || []).map((candidate) => ({
    key: `${request.id}::${candidate.id}`, requestId: request.id, candidateId: candidate.id,
    label: `${candidate.fullName || candidate.id} · ${request.warehouseName || request.warehouseId || ""} · ${request.positionLabel || request.positionCode || ""}`,
    stage: candidate.status || request.status || "ACTIVE",
  }))), [bootstrap]);
  const candidateMap = useMemo(() => new Map(candidates.map((item) => [item.key, item])), [candidates]);
  const displayCandidate = (requestId, candidateId) => candidateMap.get(`${requestId}::${candidateId}`)?.label || `${requestId} · ${candidateId}`;

  async function refresh() {
    setLoading(true); setError("");
    try {
      const [snapshot, offerRows, messageRows, talentRows, offboardRows] = await Promise.all([
        loadRecruitment(), listOfferApprovals("", 150), listLifecycleCommunications("", 150), listTalentPool(), listOffboardingCases(),
      ]);
      setBootstrap(snapshot); setApprovals(offerRows || []); setCommunications(messageRows || []); setTalent(talentRows || []); setOffboarding(offboardRows || []);
    } catch (err) { setError(err.message || c.error); }
    finally { setLoading(false); }
  }

  useEffect(() => { if (open) refresh(); }, [open]);

  async function act(key, fn, success = "") {
    setBusy(key); setError(""); setNotice("");
    try { const result = await fn(); if (success) setNotice(success); await refresh(); return result; }
    catch (err) { setError(err.message || c.error); return null; }
    finally { setBusy(""); }
  }

  async function decide(row, decision) {
    const reason = String(decisionNotes[row.offerId] || "").trim();
    if (decision === "REJECTED" && !reason) { setError(c.requiredReason); return; }
    await act(`approval-${row.offerId}`, () => decideOfferApproval(row.offerId, decision, reason));
  }
  async function issue(row) {
    setBusy(`issue-${row.offerId}`); setError(""); setNotice("");
    try {
      const result = await issueApprovedOfferCapability(row.offerId, 168);
      setSecureLinks((current) => ({ ...current, [row.offerId]: `${window.location.origin}/candidate/offer#offer=${encodeURIComponent(result.capability)}` }));
    } catch (err) { setError(err.message || c.error); }
    finally { setBusy(""); }
  }
  async function copyLink(offerId) {
    const value = secureLinks[offerId]; if (!value) return;
    try { await navigator.clipboard.writeText(value); setNotice(c.copied); } catch { setNotice(value); }
  }

  async function queueReminder(event) {
    event.preventDefault();
    const candidate = candidateMap.get(communicationForm.candidateKey); if (!candidate) return;
    const key = `ui:${communicationForm.messageType}:${candidate.requestId}:${candidate.candidateId}:${crypto.randomUUID()}`;
    await act("communication-create", () => queueCandidateCommunication(candidate.requestId, candidate.candidateId, {
      message_type: communicationForm.messageType,
      channel: communicationForm.channel,
      locale: locale === "tr" ? "tr-TR" : locale,
      template_key: communicationForm.templateKey,
      payload: { stage: candidate.stage, source: "LIFECYCLE_CENTER" },
      idempotency_key: key,
      available_at: null,
    }));
  }

  async function addTalent(event) {
    event.preventDefault();
    const candidate = candidateMap.get(talentForm.candidateKey); if (!candidate || !talentForm.consentRef.trim()) return;
    await act("talent-create", () => addCandidateToTalentPool(candidate.requestId, candidate.candidateId, {
      pool_key: talentForm.poolKey,
      tags: talentForm.tags.split(",").map((value) => value.trim()).filter(Boolean),
      consent_basis: "EXPLICIT_CANDIDATE_CONSENT",
      consent_record_ref: talentForm.consentRef.trim(),
      consent_days: Number(talentForm.consentDays),
    }));
  }

  async function createOffboard(event) {
    event.preventDefault();
    if (!offboardForm.employeeId.trim()) return;
    const effective = new Date(offboardForm.effectiveAt);
    await act("offboard-create", () => createOffboardingCase({
      employee_id: offboardForm.employeeId.trim(), effective_at: effective.toISOString(), reason_code: offboardForm.reasonCode, note: offboardForm.note.trim(),
    }), "Offboarding case oluşturuldu.");
  }
  function canCompleteTask(task) { return canOffboard || canAction("recruitment", `completeRecruitmentOffboarding:${task.ownerRole}`); }
  async function mutateTask(task, status) {
    const note = String(taskNotes[task.taskId] || "").trim();
    if (["WAIVED", "BLOCKED"].includes(status) && !note) { setError(c.requiredReason); return; }
    await act(`task-${task.taskId}`, () => updateOffboardingTask(task.taskId, status, note));
  }

  if (!canView) return null;
  return <>
    <button type="button" className="rec-life-launcher" onClick={() => setOpen(true)}><ShieldCheck size={17} />{c.open}</button>
    {open ? <div className="rec-life-backdrop" onMouseDown={() => setOpen(false)}>
      <section className="rec-life" role="dialog" aria-modal="true" aria-label={c.title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="rec-life-head"><div><span>{c.open}</span><h2>{c.title}</h2><p>{c.desc}</p></div><div className="rec-life-head-actions"><button type="button" onClick={refresh} disabled={loading} title={c.refresh}><RefreshCw size={17} /></button><button type="button" onClick={() => setOpen(false)} title={c.close}><X size={18} /></button></div></header>
        <nav className="rec-life-tabs" aria-label={c.title}>{TABS.map((key) => <button type="button" key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{key === "approvals" ? <UserRoundCheck size={16} /> : key === "communications" ? <BellRing size={16} /> : key === "talent" ? <UsersRound size={16} /> : <DoorOpen size={16} />}{c[key]}</button>)}</nav>
        {error ? <div className="rec-life-alert danger" role="alert">{error}</div> : null}{notice ? <div className="rec-life-alert success" role="status"><CheckCircle2 size={16} />{notice}</div> : null}
        {loading ? <div className="rec-life-loading" role="status"><RefreshCw size={17} />{c.refresh}…</div> : null}

        {!loading && tab === "approvals" ? <section className="rec-life-pane"><div className="rec-life-pane-title"><div><h3>{c.approvals}</h3><small><ShieldCheck size={13} />{c.secure}</small></div><strong>{approvals.filter((row) => row.status === "PENDING").length}</strong></div>
          <div className="rec-life-list">{approvals.length ? approvals.map((row) => <article className="rec-life-card" key={row.offerId}><div className="rec-life-card-main"><div><strong>{displayCandidate(row.requestId,row.candidateId)}</strong><small>{c.creator}: {row.requestedBy} · v{row.version}</small><small>{c.expires}: {formatDate(row.expiresAt)}</small></div><span className={`rec-life-status ${STATUS_CLASS[row.status] || "neutral"}`}>{stateLabel(row.status,c)}</span></div><div className="rec-life-progress"><span>{c.quorum}: {row.approvalCount}/{row.requiredApprovals}</span><progress max={row.requiredApprovals} value={row.approvalCount} /></div>{row.status === "PENDING" && canApproveOffer ? <div className="rec-life-actions"><input value={decisionNotes[row.offerId] || ""} onChange={(event) => setDecisionNotes((current) => ({ ...current, [row.offerId]: event.target.value }))} placeholder={c.reason} /><button type="button" onClick={() => decide(row,"APPROVED")} disabled={busy === `approval-${row.offerId}`}><CheckCircle2 size={14} />{c.approve}</button><button type="button" className="danger" onClick={() => decide(row,"REJECTED")} disabled={busy === `approval-${row.offerId}`}><X size={14} />{c.reject}</button></div> : null}{row.status === "APPROVED" && canIssueOffer ? <div className="rec-life-actions"><button type="button" onClick={() => issue(row)} disabled={busy === `issue-${row.offerId}`}><Send size={14} />{c.issue}</button>{secureLinks[row.offerId] ? <><input readOnly value={secureLinks[row.offerId]} aria-label={c.issue} /><button type="button" onClick={() => copyLink(row.offerId)}><Clipboard size={14} />{c.copy}</button></> : null}</div> : null}</article>) : <div className="rec-life-empty">{c.noApprovals}</div>}</div>
        </section> : null}

        {!loading && tab === "communications" ? <section className="rec-life-pane"><div className="rec-life-pane-title"><div><h3>{c.communications}</h3><small><ShieldCheck size={13} />{c.secure}</small></div><strong>{communications.filter((row) => ["QUEUED","FAILED"].includes(row.status)).length}</strong></div>{canCommunicate ? <form className="rec-life-form" onSubmit={queueReminder}><label>{c.candidate}<select value={communicationForm.candidateKey} onChange={(e) => setCommunicationForm({ ...communicationForm, candidateKey: e.target.value })}><option value="">{c.selectCandidate}</option>{candidates.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}</select></label><label>{c.messageType}<select value={communicationForm.messageType} onChange={(e) => setCommunicationForm({ ...communicationForm, messageType: e.target.value })}><option>PROCESS_UPDATE</option><option>INTERVIEW_REMINDER</option><option>OFFER_REMINDER</option><option>ONBOARDING_REMINDER</option><option>TALENT_POOL_REENGAGE</option></select></label><label>{c.channel}<select value={communicationForm.channel} onChange={(e) => setCommunicationForm({ ...communicationForm, channel: e.target.value })}><option>EMAIL</option><option>SMS</option><option>IN_APP</option></select></label><label>{c.template}<input value={communicationForm.templateKey} onChange={(e) => setCommunicationForm({ ...communicationForm, templateKey: e.target.value })} /></label><button type="submit" disabled={!communicationForm.candidateKey || busy === "communication-create"}><BellRing size={14} />{c.queueReminder}</button></form> : null}<div className="rec-life-list compact">{communications.length ? communications.map((row) => <article className="rec-life-card" key={row.messageId}><div className="rec-life-card-main"><div><strong>{displayCandidate(row.requestId,row.candidateId)}</strong><small>{row.messageType} · {row.channel} · {row.templateKey}</small><small>{formatDate(row.availableAt)} · attempts {row.attempts}</small></div><span className={`rec-life-status ${STATUS_CLASS[row.status] || "neutral"}`}>{stateLabel(row.status,c)}</span></div>{row.failureCode ? <small className="rec-life-failure">{row.failureCode}</small> : null}</article>) : <div className="rec-life-empty">{c.noCommunications}</div>}</div></section> : null}

        {!loading && tab === "talent" ? <section className="rec-life-pane"><div className="rec-life-pane-title"><div><h3>{c.talent}</h3><small><ShieldCheck size={13} />{c.secure}</small></div><strong>{talent.filter((row) => row.status === "ACTIVE").length}</strong></div>{canTalent ? <form className="rec-life-form" onSubmit={addTalent}><label>{c.candidate}<select value={talentForm.candidateKey} onChange={(e) => setTalentForm({ ...talentForm, candidateKey: e.target.value })}><option value="">{c.selectCandidate}</option>{candidates.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}</select></label><label>{c.pool}<input value={talentForm.poolKey} onChange={(e) => setTalentForm({ ...talentForm, poolKey: e.target.value.toUpperCase() })} /></label><label>{c.tags}<input value={talentForm.tags} onChange={(e) => setTalentForm({ ...talentForm, tags: e.target.value })} placeholder="ISTANBUL, DARKSTORE" /></label><label>{c.consentRef}<input value={talentForm.consentRef} onChange={(e) => setTalentForm({ ...talentForm, consentRef: e.target.value })} /></label><label>{c.consentDays}<input type="number" min="1" max="730" value={talentForm.consentDays} onChange={(e) => setTalentForm({ ...talentForm, consentDays: e.target.value })} /></label><button type="submit" disabled={!talentForm.candidateKey || !talentForm.consentRef.trim() || busy === "talent-create"}><UsersRound size={14} />{c.addTalent}</button></form> : null}<div className="rec-life-list compact">{talent.length ? talent.map((row) => <article className="rec-life-card" key={row.membershipId}><div className="rec-life-card-main"><div><strong>{displayCandidate(row.sourceRequestId,row.sourceCandidateId)}</strong><small>{row.poolKey} · {(row.tags || []).join(", ") || "—"}</small><small>{row.consentBasis} · {c.expires}: {formatDate(row.consentExpiresAt)}</small></div><span className={`rec-life-status ${STATUS_CLASS[row.status] || "neutral"}`}>{stateLabel(row.status,c)}</span></div>{row.status === "ACTIVE" && canTalent ? <div className="rec-life-actions"><button type="button" className="danger" onClick={() => act(`withdraw-${row.membershipId}`, () => withdrawTalentMembership(row.membershipId))} disabled={busy === `withdraw-${row.membershipId}`}>{c.withdraw}</button></div> : null}</article>) : <div className="rec-life-empty">{c.noTalent}</div>}</div></section> : null}

        {!loading && tab === "offboarding" ? <section className="rec-life-pane"><div className="rec-life-pane-title"><div><h3>{c.offboarding}</h3><small><ShieldCheck size={13} />governed task ownership</small></div><strong>{offboarding.filter((row) => !["CLOSED","CANCELLED"].includes(row.status)).length}</strong></div>{canOffboard ? <form className="rec-life-form" onSubmit={createOffboard}><label>{c.employee}<input value={offboardForm.employeeId} onChange={(e) => setOffboardForm({ ...offboardForm, employeeId: e.target.value })} /></label><label>{c.effective}<input type="datetime-local" value={offboardForm.effectiveAt} onChange={(e) => setOffboardForm({ ...offboardForm, effectiveAt: e.target.value })} /></label><label>{c.reasonCode}<select value={offboardForm.reasonCode} onChange={(e) => setOffboardForm({ ...offboardForm, reasonCode: e.target.value })}><option>RESIGNATION</option><option>TERMINATION</option><option>TRANSFER</option><option>CONTRACT_END</option><option>OTHER</option></select></label><label>{c.note}<input value={offboardForm.note} onChange={(e) => setOffboardForm({ ...offboardForm, note: e.target.value })} /></label><button type="submit" disabled={!offboardForm.employeeId.trim() || busy === "offboard-create"}><DoorOpen size={14} />{c.newOffboarding}</button></form> : null}<div className="rec-life-list">{offboarding.length ? offboarding.map((row) => <article className="rec-life-card offboard" key={row.caseId}><div className="rec-life-card-main"><div><strong>{row.employeeId}</strong><small>{row.reasonCode} · {formatDate(row.effectiveAt)}</small></div><span className={`rec-life-status ${STATUS_CLASS[row.status] || "neutral"}`}>{row.status === "READY_TO_CLOSE" ? c.readyToClose : stateLabel(row.status,c)}</span></div><div className="rec-life-tasks">{(row.tasks || []).map((task) => <div key={task.taskId} className="rec-life-task"><div><strong>{task.title}</strong><small>{c.owner}: {task.ownerRole}{task.dependencies?.length ? ` · deps: ${task.dependencies.join(", ")}` : ""}</small></div><span className={`rec-life-status ${STATUS_CLASS[task.status] || "neutral"}`}>{stateLabel(task.status,c)}</span>{!["COMPLETED","WAIVED"].includes(task.status) && (canCompleteTask(task) || canWaive) ? <div className="rec-life-task-actions"><input value={taskNotes[task.taskId] || ""} onChange={(e) => setTaskNotes((current) => ({ ...current, [task.taskId]: e.target.value }))} placeholder={c.note} />{canCompleteTask(task) ? <><button type="button" onClick={() => mutateTask(task,"COMPLETED")} disabled={busy === `task-${task.taskId}`}>{c.complete}</button><button type="button" onClick={() => mutateTask(task,"BLOCKED")} disabled={busy === `task-${task.taskId}`}>{c.block}</button></> : null}{canWaive ? <button type="button" className="danger" onClick={() => mutateTask(task,"WAIVED")} disabled={busy === `task-${task.taskId}`}>{c.waive}</button> : null}</div> : null}</div>)}</div>{row.closeAllowed && canCloseOffboard ? <div className="rec-life-actions"><button type="button" onClick={() => act(`close-${row.caseId}`, () => closeOffboardingCase(row.caseId))} disabled={busy === `close-${row.caseId}`}><CheckCircle2 size={14} />{c.closeCase}</button></div> : null}</article>) : <div className="rec-life-empty">{c.noOffboarding}</div>}</div></section> : null}
      </section>
    </div> : null}
  </>;
}
