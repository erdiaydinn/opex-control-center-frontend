import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Rocket, ShieldCheck, Users, X } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { activateRecruitmentHire, loadRecruitment } from "./recruitmentApi.js";
import RecruitmentOrchestrationPanel from "./RecruitmentOrchestrationPanel.jsx";
import "./recruitmentOrchestrationCenter.css";

const COPY = {
  tr: { open: "İşe alım orkestrasyonu", title: "Adaydan ilk vardiyaya", desc: "Mülakat, teklif, onboarding ve işe giriş hazırlığını yönetin.", select: "Aday seçin", noCandidate: "Aktif aday bulunmuyor.", ready: "READY_TO_HIRE", activate: "Employee Master + ilk vardiya", employeeId: "Çalışan ID", roster: "Roster ID", tckn: "TCKN", start: "İşe giriş", shiftDate: "İlk vardiya tarihi", shiftStart: "Başlangıç", shiftEnd: "Bitiş", break: "Mola (dk)", email: "E-posta", phone: "Telefon", required: "Çalışan ID, Roster ID ve 11 haneli TCKN zorunludur.", success: "İşe giriş tamamlandı. Employee Master ve ilk vardiya atomik olarak oluşturuldu.", wait: "Aktivasyon, server-backed READY_TO_HIRE oluşana kadar kilitlidir." },
  en: { open: "Hiring orchestration", title: "Candidate to first shift", desc: "Manage interviews, offer, onboarding and hire readiness.", select: "Select candidate", noCandidate: "No active candidate.", ready: "READY_TO_HIRE", activate: "Employee Master + first shift", employeeId: "Employee ID", roster: "Roster ID", tckn: "TCKN", start: "Employment start", shiftDate: "First shift date", shiftStart: "Start", shiftEnd: "End", break: "Break (min)", email: "Email", phone: "Phone", required: "Employee ID, Roster ID and an 11-digit TCKN are required.", success: "Hire activation completed. Employee Master and first shift were created atomically.", wait: "Activation stays locked until server-backed READY_TO_HIRE is reached." },
  de: { open: "Recruiting-Orchestrierung", title: "Vom Kandidaten zur ersten Schicht", desc: "Interviews, Angebot, Onboarding und Einstellungsbereitschaft verwalten.", select: "Kandidat wählen", noCandidate: "Kein aktiver Kandidat.", ready: "READY_TO_HIRE", activate: "Employee Master + erste Schicht", employeeId: "Mitarbeiter-ID", roster: "Roster-ID", tckn: "TCKN", start: "Eintritt", shiftDate: "Erste Schicht", shiftStart: "Beginn", shiftEnd: "Ende", break: "Pause (Min.)", email: "E-Mail", phone: "Telefon", required: "Mitarbeiter-ID, Roster-ID und 11-stellige TCKN sind erforderlich.", success: "Einstellung abgeschlossen. Employee Master und erste Schicht wurden atomar erstellt.", wait: "Aktivierung bleibt bis serverseitigem READY_TO_HIRE gesperrt." },
  ar: { open: "تنسيق التوظيف", title: "من المرشح إلى أول وردية", desc: "إدارة المقابلات والعرض والانضمام والجاهزية للتعيين.", select: "اختر المرشح", noCandidate: "لا يوجد مرشح نشط.", ready: "READY_TO_HIRE", activate: "سجل الموظف + أول وردية", employeeId: "معرف الموظف", roster: "معرف الجدول", tckn: "TCKN", start: "بدء العمل", shiftDate: "تاريخ أول وردية", shiftStart: "البداية", shiftEnd: "النهاية", break: "الاستراحة", email: "البريد", phone: "الهاتف", required: "معرف الموظف ومعرف الجدول وTCKN من 11 رقماً مطلوبة.", success: "اكتمل التعيين وتم إنشاء سجل الموظف وأول وردية بشكل ذري.", wait: "يبقى التفعيل مقفلاً حتى الوصول إلى READY_TO_HIRE من الخادم." },
};

function addDays(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }

export default function RecruitmentOrchestrationCenter() {
  const { canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const c = COPY[locale] || COPY.en;
  const canManage = canAction("recruitment", "approveRecruitmentRequest");
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [selection, setSelection] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [hire, setHire] = useState({ employeeId: "", rosterId: "", tckn: "", email: "", phone: "", employmentStart: addDays(7), shiftDate: addDays(7), shiftStart: "09:00", shiftEnd: "18:00", breakMinutes: 60 });

  const choices = useMemo(() => (data?.requests || []).flatMap((request) => (request.candidates || [])
    .filter((candidate) => !["HIRED", "REJECTED"].includes(candidate.status))
    .map((candidate) => ({ request, candidate, key: `${request.id}::${candidate.id}` }))), [data]);
  const selected = choices.find((item) => item.key === selection) || null;

  async function refresh() {
    try {
      const snapshot = await loadRecruitment();
      setData(snapshot);
      if (selection && !snapshot?.requests?.some((request) => (request.candidates || []).some((candidate) => `${request.id}::${candidate.id}` === selection))) setSelection("");
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { if (open) refresh(); }, [open]);
  useEffect(() => { setReady(false); setError(""); setNotice(""); }, [selection]);

  async function activate(event) {
    event.preventDefault();
    if (!selected || !ready) return;
    if (!hire.employeeId.trim() || !hire.rosterId.trim() || !/^\d{11}$/.test(hire.tckn)) { setError(c.required); return; }
    setBusy(true); setError("");
    try {
      await activateRecruitmentHire(selected.request.id, {
        candidate_id: selected.candidate.id,
        employee_id: hire.employeeId.trim(),
        roster_ids: [hire.rosterId.trim()],
        full_name: selected.candidate.fullName,
        tckn: hire.tckn,
        email: hire.email.trim() || null,
        phone: hire.phone.trim() || null,
        employment_start: hire.employmentStart,
        first_shift: { roster_id: hire.rosterId.trim(), date: hire.shiftDate, start: hire.shiftStart, end: hire.shiftEnd, break_minutes: Number(hire.breakMinutes) },
      });
      setNotice(c.success); setHire({ employeeId: "", rosterId: "", tckn: "", email: "", phone: "", employmentStart: addDays(7), shiftDate: addDays(7), shiftStart: "09:00", shiftEnd: "18:00", breakMinutes: 60 });
      await refresh();
      window.dispatchEvent(new CustomEvent("eay:recruitment:external-change"));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  if (!canManage) return null;
  return <>
    <button type="button" className="rec-orch-launcher" onClick={() => setOpen(true)}><ShieldCheck size={17} />{c.open}</button>
    {open ? <div className="rec-orch-center-backdrop" onMouseDown={() => setOpen(false)}><section className="rec-orch-center" onMouseDown={(event) => event.stopPropagation()} aria-modal="true" role="dialog" aria-label={c.title}>
      <header><div><span>{c.open}</span><h2>{c.title}</h2><p>{c.desc}</p></div><button type="button" onClick={() => setOpen(false)} aria-label="Close"><X size={18} /></button></header>
      {error ? <div className="rec-orch-center-alert error" role="alert">{error}</div> : null}{notice ? <div className="rec-orch-center-alert success" role="status"><CheckCircle2 size={17} />{notice}</div> : null}
      <label className="rec-orch-center-select"><span>{c.select}</span><select value={selection} onChange={(e) => setSelection(e.target.value)}><option value="">{c.select}</option>{choices.map((item) => <option key={item.key} value={item.key}>{item.candidate.fullName} · {item.request.warehouseName} · {item.request.positionLabel}</option>)}</select></label>
      {!choices.length ? <div className="rec-orch-center-empty"><Users size={22} />{c.noCandidate}</div> : null}
      {selected ? <>
        <RecruitmentOrchestrationPanel request={selected.request} candidate={selected.candidate} canApprove={canManage} onChanged={refresh} onReadyChange={setReady} setError={setError} />
        <section className={`rec-orch-activation ${ready ? "ready" : "locked"}`}>
          <div className="rec-orch-activation-head"><Rocket size={18} /><div><strong>{ready ? c.ready : c.activate}</strong><small>{ready ? c.activate : c.wait}</small></div></div>
          {ready ? <form onSubmit={activate} className="rec-orch-activation-form"><label>{c.employeeId}<input value={hire.employeeId} onChange={(e) => setHire({ ...hire, employeeId: e.target.value })} /></label><label>{c.roster}<input value={hire.rosterId} onChange={(e) => setHire({ ...hire, rosterId: e.target.value })} /></label><label>{c.tckn}<input type="password" inputMode="numeric" autoComplete="new-password" value={hire.tckn} onChange={(e) => setHire({ ...hire, tckn: e.target.value.replace(/\D/g, "").slice(0,11) })} /></label><label>{c.start}<input type="date" value={hire.employmentStart} onChange={(e) => setHire({ ...hire, employmentStart: e.target.value, shiftDate: e.target.value })} /></label><label>{c.email}<input type="email" value={hire.email} onChange={(e) => setHire({ ...hire, email: e.target.value })} /></label><label>{c.phone}<input value={hire.phone} onChange={(e) => setHire({ ...hire, phone: e.target.value })} /></label><label>{c.shiftDate}<input type="date" value={hire.shiftDate} onChange={(e) => setHire({ ...hire, shiftDate: e.target.value })} /></label><label>{c.shiftStart}<input type="time" value={hire.shiftStart} onChange={(e) => setHire({ ...hire, shiftStart: e.target.value })} /></label><label>{c.shiftEnd}<input type="time" value={hire.shiftEnd} onChange={(e) => setHire({ ...hire, shiftEnd: e.target.value })} /></label><label>{c.break}<input type="number" min="0" max="180" value={hire.breakMinutes} onChange={(e) => setHire({ ...hire, breakMinutes: e.target.value })} /></label><button type="submit" disabled={busy}><Rocket size={16} />{c.activate}</button></form> : null}
        </section>
      </> : null}
    </section></div> : null}
  </>;
}
