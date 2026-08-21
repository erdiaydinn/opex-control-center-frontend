import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, BriefcaseBusiness, CheckCircle2, Clipboard, Clock3, FileSignature, ListChecks, RefreshCw, Send, ShieldCheck, Users } from "lucide-react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  assignRecruitmentPipeline,
  createRecruitmentOffer,
  issueRecruitmentOfferCapability,
  listRecruitmentPipelines,
  loadCandidateOrchestration,
  submitRecruitmentScorecard,
  transitionRecruitmentStage,
  updateRecruitmentOnboardingTask,
} from "./recruitmentApi.js";
import "./recruitmentOrchestration.css";

const COPY = {
  tr: {
    title: "İşe alım orkestrasyonu", desc: "Pipeline, mülakat, teklif, onboarding ve işe giriş hazırlığını tek akışta yönetin.", loading: "Orkestrasyon yükleniyor…", retry: "Tekrar dene",
    noPipeline: "Pipeline atanmadı", choosePipeline: "Pipeline seç", assign: "Ata", stage: "Aşama", sla: "SLA", breached: "SLA aşıldı", withinSla: "SLA içinde", nextStage: "Sonraki aşama", move: "İlerle", reason: "Geçiş gerekçesi",
    scorecards: "Mülakat scorecard", scorecardCount: "{count} scorecard", roleFit: "Rol uyumu", communication: "İletişim", problemSolving: "Problem çözme", operations: "Operasyon", recommendation: "Öneri", submitScorecard: "Scorecard kaydet", conflict: "Çıkar çatışması var",
    offer: "Teklif", createOffer: "Teklif oluştur", country: "Ülke", currency: "Para birimi", amount: "Ücret", period: "Periyot", start: "Başlangıç", employment: "Çalışma tipi", benefits: "Yan haklar", probation: "Deneme süresi / koşullar", issueLink: "Güvenli aday linki üret", copyLink: "Linki kopyala", linkCopied: "Güvenli aday linki panoya kopyalandı. Link tek kullanımlıktır.",
    onboarding: "Onboarding görevleri", owner: "Sahip", due: "Termin", deps: "Bağımlılık", complete: "Tamamla", startTask: "Başlat", block: "Bloke et", waive: "Waive", waiverNote: "Waive/blokaj gerekçesi", ready: "İşe girişe hazır", blocked: "İşe giriş henüz hazır değil", readyDetail: "Pipeline READY_TO_HIRE ve zorunlu onboarding görevleri tamamlandı.", blockedDetail: "Eksik adımları tamamlayın; server son aktivasyonda authority’yi tekrar doğrular.", noTasks: "Teklif kabul edilince onboarding görevleri otomatik oluşur.", noOffer: "Henüz teklif yok.", refresh: "Yenile", candidatePortal: "Aday portalı", secureLinkWarning: "Capability linkini yalnız adayla güvenli kanaldan paylaşın. Sistem tokenı sonradan tekrar göstermez.",
    accepted: "Kabul edildi", declined: "Reddedildi", issued: "Gönderildi", expired: "Süresi doldu", pending: "Bekliyor", completed: "Tamamlandı", waived: "Waive edildi", inProgress: "Devam ediyor", taskBlocked: "Bloke",
  },
  en: {
    title: "Hiring orchestration", desc: "Manage pipeline, interviews, offer, onboarding and hire readiness in one governed flow.", loading: "Loading orchestration…", retry: "Retry",
    noPipeline: "No pipeline assigned", choosePipeline: "Choose pipeline", assign: "Assign", stage: "Stage", sla: "SLA", breached: "SLA breached", withinSla: "Within SLA", nextStage: "Next stage", move: "Advance", reason: "Transition rationale",
    scorecards: "Interview scorecards", scorecardCount: "{count} scorecard(s)", roleFit: "Role fit", communication: "Communication", problemSolving: "Problem solving", operations: "Operations", recommendation: "Recommendation", submitScorecard: "Submit scorecard", conflict: "Conflict of interest declared",
    offer: "Offer", createOffer: "Create offer", country: "Country", currency: "Currency", amount: "Compensation", period: "Period", start: "Start date", employment: "Employment type", benefits: "Benefits", probation: "Probation / conditions", issueLink: "Generate secure candidate link", copyLink: "Copy link", linkCopied: "Secure candidate link copied. The link is single-use.",
    onboarding: "Onboarding tasks", owner: "Owner", due: "Due", deps: "Dependencies", complete: "Complete", startTask: "Start", block: "Block", waive: "Waive", waiverNote: "Waiver/block rationale", ready: "Ready to hire", blocked: "Not ready to hire yet", readyDetail: "Pipeline is READY_TO_HIRE and required onboarding tasks are complete.", blockedDetail: "Complete the missing steps; the server re-validates authority during final activation.", noTasks: "Onboarding tasks are created automatically after offer acceptance.", noOffer: "No offer yet.", refresh: "Refresh", candidatePortal: "Candidate portal", secureLinkWarning: "Share the capability link with the candidate through a secure channel only. The token is not shown again later.",
    accepted: "Accepted", declined: "Declined", issued: "Issued", expired: "Expired", pending: "Pending", completed: "Completed", waived: "Waived", inProgress: "In progress", taskBlocked: "Blocked",
  },
  de: {
    title: "Recruiting-Orchestrierung", desc: "Pipeline, Interviews, Angebot, Onboarding und Einstellungsbereitschaft in einem gesteuerten Ablauf.", loading: "Orchestrierung wird geladen…", retry: "Erneut versuchen", noPipeline: "Keine Pipeline zugewiesen", choosePipeline: "Pipeline wählen", assign: "Zuweisen", stage: "Phase", sla: "SLA", breached: "SLA überschritten", withinSla: "Innerhalb SLA", nextStage: "Nächste Phase", move: "Weiter", reason: "Begründung", scorecards: "Interview-Scorecards", scorecardCount: "{count} Scorecard(s)", roleFit: "Rollenpassung", communication: "Kommunikation", problemSolving: "Problemlösung", operations: "Operations", recommendation: "Empfehlung", submitScorecard: "Scorecard speichern", conflict: "Interessenkonflikt", offer: "Angebot", createOffer: "Angebot erstellen", country: "Land", currency: "Währung", amount: "Vergütung", period: "Periode", start: "Startdatum", employment: "Beschäftigungsart", benefits: "Zusatzleistungen", probation: "Probezeit / Bedingungen", issueLink: "Sicheren Kandidatenlink erzeugen", copyLink: "Link kopieren", linkCopied: "Sicherer Kandidatenlink kopiert. Der Link ist einmalig.", onboarding: "Onboarding-Aufgaben", owner: "Verantwortlich", due: "Fällig", deps: "Abhängigkeiten", complete: "Abschließen", startTask: "Starten", block: "Blockieren", waive: "Erlassen", waiverNote: "Begründung", ready: "Einstellungsbereit", blocked: "Noch nicht einstellungsbereit", readyDetail: "Pipeline ist READY_TO_HIRE und alle Pflichtaufgaben sind abgeschlossen.", blockedDetail: "Fehlende Schritte abschließen; der Server prüft die Berechtigung bei Aktivierung erneut.", noTasks: "Onboarding-Aufgaben entstehen nach Annahme des Angebots automatisch.", noOffer: "Noch kein Angebot.", refresh: "Aktualisieren", candidatePortal: "Kandidatenportal", secureLinkWarning: "Capability-Link nur über sicheren Kanal teilen. Das Token wird später nicht erneut angezeigt.", accepted: "Angenommen", declined: "Abgelehnt", issued: "Ausgestellt", expired: "Abgelaufen", pending: "Offen", completed: "Abgeschlossen", waived: "Erlassen", inProgress: "In Bearbeitung", taskBlocked: "Blockiert",
  },
  ar: {
    title: "تنسيق التوظيف", desc: "إدارة المسار والمقابلات والعرض ومهام الانضمام والجاهزية للتعيين ضمن تدفق واحد محكوم.", loading: "جارٍ تحميل التنسيق…", retry: "إعادة المحاولة", noPipeline: "لم يتم تعيين مسار", choosePipeline: "اختر المسار", assign: "تعيين", stage: "المرحلة", sla: "SLA", breached: "تم تجاوز SLA", withinSla: "ضمن SLA", nextStage: "المرحلة التالية", move: "تقدم", reason: "سبب الانتقال", scorecards: "بطاقات تقييم المقابلة", scorecardCount: "{count} بطاقة", roleFit: "ملاءمة الدور", communication: "التواصل", problemSolving: "حل المشكلات", operations: "العمليات", recommendation: "التوصية", submitScorecard: "حفظ التقييم", conflict: "يوجد تعارض مصالح", offer: "العرض", createOffer: "إنشاء العرض", country: "الدولة", currency: "العملة", amount: "التعويض", period: "الفترة", start: "تاريخ البدء", employment: "نوع التوظيف", benefits: "المزايا", probation: "فترة التجربة / الشروط", issueLink: "إنشاء رابط مرشح آمن", copyLink: "نسخ الرابط", linkCopied: "تم نسخ رابط المرشح الآمن. الرابط للاستخدام مرة واحدة.", onboarding: "مهام الانضمام", owner: "المالك", due: "الموعد", deps: "الاعتماديات", complete: "إكمال", startTask: "بدء", block: "حظر", waive: "إعفاء", waiverNote: "سبب الإعفاء/الحظر", ready: "جاهز للتعيين", blocked: "غير جاهز للتعيين بعد", readyDetail: "المسار في READY_TO_HIRE وتم إنجاز المهام الإلزامية.", blockedDetail: "أكمل الخطوات الناقصة؛ الخادم يعيد التحقق عند التفعيل النهائي.", noTasks: "يتم إنشاء مهام الانضمام تلقائياً بعد قبول العرض.", noOffer: "لا يوجد عرض بعد.", refresh: "تحديث", candidatePortal: "بوابة المرشح", secureLinkWarning: "شارك رابط الصلاحية مع المرشح عبر قناة آمنة فقط. لن يظهر الرمز مرة أخرى.", accepted: "مقبول", declined: "مرفوض", issued: "صادر", expired: "منتهي", pending: "قيد الانتظار", completed: "مكتمل", waived: "معفى", inProgress: "قيد التنفيذ", taskBlocked: "محظور",
  },
};

function interpolate(value, params = {}) { return String(value).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? ""); }
function hours(seconds) { return `${Math.max(0, Math.round(Number(seconds || 0) / 360) / 10)}h`; }
function offerState(value, c) { const key = String(value || "ISSUED").toLowerCase(); return c[key] || value || c.issued; }
function taskState(value, c) { return ({ PENDING: c.pending, COMPLETED: c.completed, WAIVED: c.waived, IN_PROGRESS: c.inProgress, BLOCKED: c.taskBlocked })[value] || value; }

export default function RecruitmentOrchestrationPanel({ request, candidate, canApprove, onChanged, onReadyChange, setError }) {
  const { locale } = usePlatformPreferences();
  const c = COPY[locale] || COPY.en;
  const [summary, setSummary] = useState(null);
  const [pipelines, setPipelines] = useState([]);
  const [selectedPipeline, setSelectedPipeline] = useState("");
  const [targetStage, setTargetStage] = useState("");
  const [transitionReason, setTransitionReason] = useState("");
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState("");
  const [scorecard, setScorecard] = useState({ role_fit: 75, communication: 75, problem_solving: 75, operations: 75, recommendation: "HIRE", conflict: false });
  const [offer, setOffer] = useState({ country_code: "TR", currency: "TRY", compensation_amount: "", compensation_period: "MONTHLY", employment_start: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10), benefits_summary: "", probation_summary: "" });
  const [secureLink, setSecureLink] = useState("");
  const [taskNotes, setTaskNotes] = useState({});

  const currentTemplate = useMemo(() => pipelines.find((item) => item.templateId === summary?.pipeline?.templateId), [pipelines, summary]);
  const stages = currentTemplate?.stages || [];
  const currentIndex = stages.findIndex((stage) => stage.key === summary?.pipeline?.currentStage);
  const nextStages = currentIndex >= 0 ? stages.slice(currentIndex + 1).filter((stage, index) => index === 0 || stages[currentIndex]?.allowSkip) : [];
  const latestOffer = summary?.offers?.[0] || null;
  const requiredTasks = (summary?.onboardingTasks || []).filter((task) => task.required);
  const finishedTasks = requiredTasks.filter((task) => ["COMPLETED", "WAIVED"].includes(task.status));
  const ready = Boolean(summary?.pipeline?.currentStage === "READY_TO_HIRE" && latestOffer?.state === "ACCEPTED" && requiredTasks.length > 0 && requiredTasks.length === finishedTasks.length);

  useEffect(() => { if (onReadyChange) onReadyChange(ready); }, [ready, onReadyChange]);

  async function load() {
    setLoadError(""); setBusy("load");
    try {
      const [pipelineRows, detail] = await Promise.all([
        listRecruitmentPipelines(),
        loadCandidateOrchestration(request.id, candidate.id),
      ]);
      setPipelines(pipelineRows || []); setSummary(detail);
      if (!selectedPipeline && pipelineRows?.[0]?.templateId) setSelectedPipeline(pipelineRows[0].templateId);
    } catch (error) { setLoadError(error.message); }
    finally { setBusy(""); }
  }

  useEffect(() => { load(); /* candidate identity is stable for this card */ }, [request.id, candidate.id]);

  async function mutate(key, action) {
    setBusy(key); setError?.("");
    try { await action(); setSecureLink(""); await load(); if (onChanged) await onChanged(); }
    catch (error) { setError?.(error.message); }
    finally { setBusy(""); }
  }

  async function assign() { if (!selectedPipeline) return; await mutate("assign", () => assignRecruitmentPipeline(request.id, candidate.id, selectedPipeline)); }
  async function move() { if (!targetStage) return; await mutate("move", () => transitionRecruitmentStage(request.id, candidate.id, targetStage, transitionReason)); setTransitionReason(""); setTargetStage(""); }
  async function saveScorecard(event) {
    event.preventDefault();
    await mutate("score", () => submitRecruitmentScorecard(request.id, candidate.id, {
      role_fit: Number(scorecard.role_fit), communication: Number(scorecard.communication), problem_solving: Number(scorecard.problem_solving), operations: Number(scorecard.operations),
    }, scorecard.recommendation, scorecard.conflict));
  }
  async function makeOffer(event) {
    event.preventDefault();
    if (!offer.compensation_amount) return;
    await mutate("offer", async () => {
      const result = await createRecruitmentOffer(request.id, candidate.id, {
        ...offer,
        position: request.positionLabel || request.positionCode || "Role",
        employment_type: request.employmentType || "FULL_TIME",
        work_location: request.warehouseName || request.warehouseId || "",
        compensation_amount: Number(offer.compensation_amount),
      });
      return result;
    });
  }
  async function issueLink() {
    if (!latestOffer?.offerId) return;
    setBusy("link");
    try {
      const result = await issueRecruitmentOfferCapability(latestOffer.offerId, 168);
      const url = `${window.location.origin}/candidate/offer#offer=${encodeURIComponent(result.capability)}`;
      setSecureLink(url);
    } catch (error) { setError?.(error.message); }
    finally { setBusy(""); }
  }
  async function copyLink() {
    if (!secureLink) return;
    try { await navigator.clipboard.writeText(secureLink); setError?.(c.linkCopied); }
    catch { setError?.(secureLink); }
  }
  async function task(task, status) {
    const note = String(taskNotes[task.taskId] || "").trim();
    if ((status === "WAIVED" || status === "BLOCKED") && !note) { setError?.(c.waiverNote); return; }
    await mutate(`task-${task.taskId}`, () => updateRecruitmentOnboardingTask(task.taskId, status, note));
  }

  if (busy === "load" && !summary) return <div className="rec-orch-loading" role="status"><RefreshCw size={16} /> {c.loading}</div>;
  if (loadError) return <div className="rec-orch-error" role="alert"><span>{loadError}</span><button type="button" onClick={load}><RefreshCw size={15} />{c.retry}</button></div>;

  return <section className="rec-orch" aria-label={c.title}>
    <header className="rec-orch-head"><div><span className="rec-kicker">{c.title}</span><p>{c.desc}</p></div><button type="button" className="rec-icon-action" title={c.refresh} onClick={load} disabled={busy === "load"}><RefreshCw size={16} /></button></header>

    {!summary?.pipeline ? <div className="rec-orch-block"><BriefcaseBusiness size={18} /><div><strong>{c.noPipeline}</strong><div className="rec-orch-inline"><select value={selectedPipeline} onChange={(e) => setSelectedPipeline(e.target.value)} aria-label={c.choosePipeline}><option value="">{c.choosePipeline}</option>{pipelines.map((item) => <option key={item.templateId} value={item.templateId}>{item.name} · v{item.version}</option>)}</select>{canApprove ? <button type="button" onClick={assign} disabled={!selectedPipeline || busy === "assign"}>{c.assign}</button> : null}</div></div></div> : <>
      <div className="rec-orch-stage"><div><small>{c.stage}</small><strong>{summary.pipeline.currentStage}</strong></div><div className={summary.pipeline.stageSlaBreached ? "breach" : "ok"}><Clock3 size={15} /><span>{c.sla}: {hours(summary.pipeline.stageElapsedSeconds)} / {hours(summary.pipeline.stageSlaSeconds)} · {summary.pipeline.stageSlaBreached ? c.breached : c.withinSla}</span></div></div>
      {canApprove && nextStages.length ? <div className="rec-orch-transition"><select value={targetStage} onChange={(e) => setTargetStage(e.target.value)} aria-label={c.nextStage}><option value="">{c.nextStage}</option>{nextStages.map((stage) => <option key={stage.key} value={stage.key}>{stage.label}</option>)}</select><input value={transitionReason} onChange={(e) => setTransitionReason(e.target.value)} placeholder={c.reason} /><button type="button" onClick={move} disabled={!targetStage || busy === "move"}><ArrowRight size={15} />{c.move}</button></div> : null}
    </>}

    {summary?.pipeline ? <div className="rec-orch-section"><div className="rec-orch-section-title"><Users size={17} /><strong>{c.scorecards}</strong><span>{interpolate(c.scorecardCount, { count: (summary.scorecards || []).reduce((sum, row) => sum + Number(row.count || 0), 0) })}</span></div>{canApprove ? <form className="rec-orch-score" onSubmit={saveScorecard}>{[["role_fit",c.roleFit],["communication",c.communication],["problem_solving",c.problemSolving],["operations",c.operations]].map(([key,label]) => <label key={key}>{label}<input type="number" min="0" max="100" value={scorecard[key]} onChange={(e) => setScorecard({ ...scorecard, [key]: e.target.value })} /></label>)}<label>{c.recommendation}<select value={scorecard.recommendation} onChange={(e) => setScorecard({ ...scorecard, recommendation: e.target.value })}><option value="STRONG_HIRE">STRONG_HIRE</option><option value="HIRE">HIRE</option><option value="NO_HIRE">NO_HIRE</option><option value="STRONG_NO_HIRE">STRONG_NO_HIRE</option></select></label><label className="rec-orch-check"><input type="checkbox" checked={scorecard.conflict} onChange={(e) => setScorecard({ ...scorecard, conflict: e.target.checked })} />{c.conflict}</label><button type="submit" disabled={busy === "score"}>{c.submitScorecard}</button></form> : null}</div> : null}

    {summary?.pipeline?.currentStage === "OFFER" && canApprove ? <div className="rec-orch-section"><div className="rec-orch-section-title"><FileSignature size={17} /><strong>{c.offer}</strong></div>{!latestOffer ? <form className="rec-orch-offer" onSubmit={makeOffer}><label>{c.country}<input maxLength="2" value={offer.country_code} onChange={(e) => setOffer({ ...offer, country_code: e.target.value.toUpperCase() })} /></label><label>{c.currency}<input maxLength="3" value={offer.currency} onChange={(e) => setOffer({ ...offer, currency: e.target.value.toUpperCase() })} /></label><label>{c.amount}<input type="number" min="0.01" step="0.01" value={offer.compensation_amount} onChange={(e) => setOffer({ ...offer, compensation_amount: e.target.value })} /></label><label>{c.period}<select value={offer.compensation_period} onChange={(e) => setOffer({ ...offer, compensation_period: e.target.value })}><option value="MONTHLY">MONTHLY</option><option value="HOURLY">HOURLY</option><option value="ANNUAL">ANNUAL</option></select></label><label>{c.start}<input type="date" value={offer.employment_start} onChange={(e) => setOffer({ ...offer, employment_start: e.target.value })} /></label><label className="wide">{c.benefits}<textarea value={offer.benefits_summary} onChange={(e) => setOffer({ ...offer, benefits_summary: e.target.value })} /></label><label className="wide">{c.probation}<textarea value={offer.probation_summary} onChange={(e) => setOffer({ ...offer, probation_summary: e.target.value })} /></label><button type="submit" disabled={busy === "offer"}>{c.createOffer}</button></form> : <div className="rec-orch-offer-state"><span className={`rec-status ${latestOffer.state === "ACCEPTED" ? "success" : latestOffer.state === "DECLINED" ? "danger" : "info"}`}>{offerState(latestOffer.state,c)}</span><code>{latestOffer.packageSha256?.slice(0,12)}…</code>{latestOffer.state === "ISSUED" ? <button type="button" onClick={issueLink} disabled={busy === "link"}><Send size={15} />{c.issueLink}</button> : null}</div>}{secureLink ? <div className="rec-orch-secure-link"><ShieldCheck size={16} /><div><strong>{c.candidatePortal}</strong><p>{c.secureLinkWarning}</p><input readOnly value={secureLink} aria-label={c.candidatePortal} /></div><button type="button" onClick={copyLink}><Clipboard size={15} />{c.copyLink}</button></div> : null}</div> : null}

    <div className="rec-orch-section"><div className="rec-orch-section-title"><ListChecks size={17} /><strong>{c.onboarding}</strong><span>{finishedTasks.length}/{requiredTasks.length}</span></div>{summary?.onboardingTasks?.length ? <div className="rec-orch-tasks">{summary.onboardingTasks.map((taskRow) => <article key={taskRow.taskId} className="rec-orch-task"><div><strong>{taskRow.title}</strong><small>{c.owner}: {taskRow.ownerRole} · {c.due}: {taskRow.dueAt ? new Date(taskRow.dueAt).toLocaleString() : "—"}</small>{taskRow.dependencies?.length ? <small>{c.deps}: {taskRow.dependencies.join(", ")}</small> : null}</div><span className={`rec-status ${taskRow.status === "COMPLETED" ? "success" : taskRow.status === "BLOCKED" ? "danger" : "neutral"}`}>{taskState(taskRow.status,c)}</span>{canApprove && !["COMPLETED","WAIVED"].includes(taskRow.status) ? <div className="rec-orch-task-actions"><input value={taskNotes[taskRow.taskId] || ""} onChange={(e) => setTaskNotes({ ...taskNotes, [taskRow.taskId]: e.target.value })} placeholder={c.waiverNote} /><button type="button" onClick={() => task(taskRow,"IN_PROGRESS")} disabled={busy === `task-${taskRow.taskId}`}>{c.startTask}</button><button type="button" onClick={() => task(taskRow,"BLOCKED")} disabled={busy === `task-${taskRow.taskId}`}>{c.block}</button><button type="button" onClick={() => task(taskRow,"COMPLETED")} disabled={busy === `task-${taskRow.taskId}`}>{c.complete}</button><button type="button" onClick={() => task(taskRow,"WAIVED")} disabled={busy === `task-${taskRow.taskId}`}>{c.waive}</button></div> : null}</article>)}</div> : <p className="rec-orch-muted">{c.noTasks}</p>}</div>

    <div className={`rec-orch-readiness ${ready ? "ready" : "blocked"}`} role="status"><CheckCircle2 size={20} /><div><strong>{ready ? c.ready : c.blocked}</strong><p>{ready ? c.readyDetail : c.blockedDetail}</p></div></div>
  </section>;
}
