import React, { useState } from "react";
import { BadgeCheck, Check, FileCheck2, Plus, Rocket, Upload, UserPlus, X } from "lucide-react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { recruitmentMessage } from "../../platform/i18n/recruitmentMessages.js";
import {
  activateRecruitmentHire,
  decideRecruitmentCandidate,
  registerRecruitmentCandidate,
  uploadRecruitmentCandidateEvidence,
} from "./recruitmentApi.js";


function addDays(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }

const CANDIDATE_STATUS = {
  EVIDENCE_PENDING: ["statusEvidencePending", "warning"],
  REVIEW_PENDING: ["statusReviewPending", "info"],
  APPROVED: ["statusApproved", "success"],
  REJECTED: ["statusRejected", "danger"],
  HIRED: ["statusHired", "success"],
};

function CandidateStatus({ value, m }) {
  const [labelKey, tone] = CANDIDATE_STATUS[value] || ["statusReviewPending", "neutral"];
  return <span className={`rec-status ${tone}`}>{m(labelKey)}</span>;
}

export default function RecruitmentCandidateWorkspace({ request, canApprove, onChanged, flash, setError }) {
  const { locale } = usePlatformPreferences();
  const m = (key, params) => recruitmentMessage(locale, key, params);
  const [adding, setAdding] = useState(false);
  const [candidate, setCandidate] = useState({ fullName: "", sourceRef: "", note: "" });
  const [reviewNotes, setReviewNotes] = useState({});
  const [busy, setBusy] = useState("");
  const [hireCandidate, setHireCandidate] = useState(null);
  const [hire, setHire] = useState({
    employeeId: "", rosterId: "", tckn: "", email: "", phone: "",
    employmentStart: addDays(7), shiftDate: addDays(7), shiftStart: "09:00", shiftEnd: "18:00", breakMinutes: 60,
  });
  const candidates = request?.candidates || [];
  const vacancyOpen = ["APPROVED", "SOURCING", "PARTIALLY_FILLED"].includes(request?.status);

  async function changed(message) {
    flash(message);
    if (onChanged) await onChanged();
  }

  async function addCandidate(event) {
    event.preventDefault();
    if (!candidate.fullName.trim() || !candidate.sourceRef.trim()) { setError(m("candidateNameSourceRequired")); return; }
    setBusy("add");
    try {
      await registerRecruitmentCandidate(request.id, {
        full_name: candidate.fullName.trim(), source_ref: candidate.sourceRef.trim(), note: candidate.note.trim() || null,
      });
      setCandidate({ fullName: "", sourceRef: "", note: "" }); setAdding(false);
      await changed(m("candidateAdded"));
    } catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  async function uploadEvidence(candidateId, file) {
    if (!file) return;
    setBusy(`evidence-${candidateId}`);
    try { await uploadRecruitmentCandidateEvidence(request.id, candidateId, file); await changed(m("candidateEvidenceAdded")); }
    catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  async function decide(candidateId, decision) {
    const note = String(reviewNotes[candidateId] || "").trim();
    if (!note) { setError(m("candidateDecisionRequired")); return; }
    setBusy(`decision-${candidateId}`);
    try { await decideRecruitmentCandidate(request.id, candidateId, decision, note); await changed(decision === "APPROVED" ? m("candidateApproved") : m("candidateRejected")); }
    catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  async function activate(event) {
    event.preventDefault();
    if (!hireCandidate) return;
    if (!hire.employeeId.trim() || !hire.rosterId.trim() || !/^\d{11}$/.test(hire.tckn)) {
      setError(m("hireFieldsRequired")); return;
    }
    setBusy(`hire-${hireCandidate.id}`);
    try {
      await activateRecruitmentHire(request.id, {
        candidate_id: hireCandidate.id,
        employee_id: hire.employeeId.trim(),
        roster_ids: [hire.rosterId.trim()],
        full_name: hireCandidate.fullName,
        tckn: hire.tckn,
        email: hire.email.trim() || null,
        phone: hire.phone.trim() || null,
        employment_start: hire.employmentStart,
        first_shift: {
          roster_id: hire.rosterId.trim(), date: hire.shiftDate,
          start: hire.shiftStart, end: hire.shiftEnd, break_minutes: Number(hire.breakMinutes),
        },
      });
      setHireCandidate(null);
      setHire({ employeeId: "", rosterId: "", tckn: "", email: "", phone: "", employmentStart: addDays(7), shiftDate: addDays(7), shiftStart: "09:00", shiftEnd: "18:00", breakMinutes: 60 });
      await changed(m("hireComplete"));
    } catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  return <section className="rec-candidate-workspace">
    <header><div><span className="rec-kicker">{m("candidateDayOne")}</span><h3>{m("candidateHeading")}</h3><p>{m("candidateDesc")}</p></div>{canApprove && vacancyOpen ? <button className="rec-secondary" onClick={() => setAdding((value) => !value)}><Plus size={16} /> {m("addCandidate")}</button> : null}</header>

    {adding ? <form className="rec-candidate-add" onSubmit={addCandidate}><label>{m("candidateName")}<input value={candidate.fullName} onChange={(e) => setCandidate({ ...candidate, fullName: e.target.value })} /></label><label>{m("sourceReference")}<input value={candidate.sourceRef} onChange={(e) => setCandidate({ ...candidate, sourceRef: e.target.value })} placeholder={m("sourcePlaceholder")} /></label><label className="wide">{m("note")}<input value={candidate.note} onChange={(e) => setCandidate({ ...candidate, note: e.target.value })} /></label><button className="rec-primary" disabled={busy === "add"}><UserPlus size={16} /> {m("save")}</button></form> : null}

    <div className="rec-candidate-list">
      {candidates.map((row) => {
        const evidenceCount = row.evidenceCount ?? row.evidence?.length ?? 0;
        return <article key={row.id} className="rec-candidate-card"><div className="rec-candidate-head"><div><strong>{row.fullName}</strong><small>{row.sourceRef} · {row.id}</small></div><CandidateStatus value={row.status} m={m} /></div><div className="rec-candidate-evidence"><FileCheck2 size={16} /><span>{m("evidenceCount", { count: evidenceCount })}</span>{canApprove && row.status !== "HIRED" && row.status !== "REJECTED" ? <label className="rec-mini-upload"><Upload size={15} />{busy === `evidence-${row.id}` ? m("uploading") : m("uploadEvidence")}<input type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={(e) => uploadEvidence(row.id, e.target.files?.[0])} /></label> : null}</div>
          {canApprove && row.status === "REVIEW_PENDING" ? <div className="rec-candidate-review"><input value={reviewNotes[row.id] || ""} onChange={(e) => setReviewNotes({ ...reviewNotes, [row.id]: e.target.value })} placeholder={m("decisionReason")} /><button className="reject" onClick={() => decide(row.id, "REJECTED")} disabled={busy === `decision-${row.id}`}><X size={15} /> {m("reject")}</button><button className="approve" onClick={() => decide(row.id, "APPROVED")} disabled={busy === `decision-${row.id}`}><Check size={15} /> {m("approve")}</button></div> : null}
          {canApprove && row.status === "APPROVED" ? <button className="rec-primary rec-hire-open" onClick={() => setHireCandidate(row)}><Rocket size={16} /> {m("employeeMasterShift")}</button> : null}
          {row.status === "HIRED" ? <div className="rec-candidate-hired"><BadgeCheck size={16} /> {m("hiredMaster", { employee: row.employeeId || m("statusHired") })}</div> : null}
        </article>;
      })}
      {!candidates.length ? <div className="rec-empty">{m("noCandidate")}</div> : null}
    </div>

    {hireCandidate ? <form className="rec-hire-form" onSubmit={activate}><header><div><span className="rec-kicker">{m("hireActivation")}</span><h3>{hireCandidate.fullName}</h3></div><button type="button" className="rec-modal-close-inline" onClick={() => { setHireCandidate(null); setHire({ ...hire, tckn: "" }); }}><X size={17} /></button></header><div className="rec-form-grid"><label>{m("hrEmployeeId")}<input value={hire.employeeId} onChange={(e) => setHire({ ...hire, employeeId: e.target.value })} /></label><label>{m("rosterId")}<input value={hire.rosterId} onChange={(e) => setHire({ ...hire, rosterId: e.target.value })} /></label><label>{m("tckn")}<input type="password" inputMode="numeric" autoComplete="new-password" value={hire.tckn} onChange={(e) => setHire({ ...hire, tckn: e.target.value.replace(/\D/g, "").slice(0, 11) })} /></label><label>{m("hireDate")}<input type="date" value={hire.employmentStart} onChange={(e) => setHire({ ...hire, employmentStart: e.target.value, shiftDate: e.target.value })} /></label><label>{m("email")}<input value={hire.email} onChange={(e) => setHire({ ...hire, email: e.target.value })} /></label><label>{m("phone")}<input value={hire.phone} onChange={(e) => setHire({ ...hire, phone: e.target.value })} /></label><label>{m("firstShiftDate")}<input type="date" value={hire.shiftDate} onChange={(e) => setHire({ ...hire, shiftDate: e.target.value })} /></label><label>{m("shiftStart")}<input type="time" value={hire.shiftStart} onChange={(e) => setHire({ ...hire, shiftStart: e.target.value })} /></label><label>{m("shiftEnd")}<input type="time" value={hire.shiftEnd} onChange={(e) => setHire({ ...hire, shiftEnd: e.target.value })} /></label><label>{m("breakMinutes")}<input type="number" min="0" max="180" value={hire.breakMinutes} onChange={(e) => setHire({ ...hire, breakMinutes: e.target.value })} /></label></div><p className="rec-config-note">{m("tcknNote")}</p><button className="rec-primary" disabled={busy === `hire-${hireCandidate.id}`}><Rocket size={16} /> {busy === `hire-${hireCandidate.id}` ? m("activating") : m("hireAndShift")}</button></form> : null}
  </section>;
}