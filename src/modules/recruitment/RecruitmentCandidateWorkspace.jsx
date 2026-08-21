import React, { useState } from "react";
import { BadgeCheck, Check, CircleAlert, Download, FileCheck2, Fingerprint, Plus, Rocket, ShieldCheck, Upload, UserCheck, UserPlus, X } from "lucide-react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { recruitmentMessage } from "../../platform/i18n/recruitmentMessages.js";
import {
  activateRecruitmentHire,
  attestRecruitmentCandidateDocument,
  decideRecruitmentCandidate,
  downloadRecruitmentCandidateEvidence,
  registerRecruitmentCandidate,
  uploadRecruitmentCandidateEvidence,
  verifyRecruitmentCandidateDocument,
} from "./recruitmentApi.js";
import { candidateEvidenceGate, isEvidenceMalwareCleared } from "./recruitmentEvidenceTrust.js";


function addDays(days) { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); }

const CANDIDATE_STATUS = {
  EVIDENCE_PENDING: ["statusEvidencePending", "warning"],
  REVIEW_PENDING: ["statusReviewPending", "info"],
  APPROVED: ["statusApproved", "success"],
  REJECTED: ["statusRejected", "danger"],
  HIRED: ["statusHired", "success"],
};

const DOCUMENT_TYPES = ["CRIMINAL_RECORD", "RESIDENCE", "SGK_SERVICE", "MILITARY_STATUS", "EDUCATION", "CIVIL_REGISTRY", "OTHER"];
const OFFICIAL_STATES = {
  BARCODE_EXTRACTION_PENDING: ["verificationAwaiting", "warning"],
  OFFICIAL_VERIFIED: ["verificationVerified", "success"],
  HUMAN_WITNESSED_PENDING_ATTESTATION: ["verificationAttestationPending", "warning"],
  HUMAN_WITNESSED_ATTESTED: ["verificationAttested", "success"],
  OFFICIAL_REVIEW_FAILED: ["verificationFailed", "danger"],
  NOT_REQUIRED: ["verificationNotRequired", "neutral"],
};

function shortDigest(value) { return value ? `${value.slice(0, 10)}…${value.slice(-6)}` : "—"; }

function VerificationPill({ value, m }) {
  const [key, tone] = OFFICIAL_STATES[value] || ["verificationAwaiting", "warning"];
  return <span className={`rec-status ${tone}`}>{m(key)}</span>;
}

function CandidateEvidence({ item, candidateId, requestId, canApprove, onVerify, onAttest, m }) {
  const verification = item.officialVerification;
  const malwareCleared = isEvidenceMalwareCleared(item);
  return <article className="rec-document-card">
    <div className="rec-document-icon"><FileCheck2 size={19} /></div>
    <div className="rec-document-main"><div className="rec-document-title"><strong>{m(`document${item.documentType || "OTHER"}`)}</strong><VerificationPill value={item.verificationState} m={m} /></div><span>{item.originalName}</span><small>SHA-256 · {shortDigest(item.sha256)}</small></div>
    {malwareCleared ? <button type="button" className="rec-icon-action" title={m("downloadDocument")} onClick={() => downloadRecruitmentCandidateEvidence(requestId, candidateId, item.sha256, item.originalName)}><Download size={16} /></button> : null}
    <div className="rec-document-checks">
      <span className={malwareCleared ? "pass" : item.contentSafetyState === "MALWARE_DETECTED" ? "fail" : "pending"}><ShieldCheck size={15} />{malwareCleared ? m("malwareCleared") : item.contentSafetyState === "MALWARE_DETECTED" ? m("malwareDetected") : item.contentSafetyState === "SCAN_FAILED" ? m("malwareScanFailed") : m("malwareScanPending")}</span>
      <span className={["OFFICIAL_VERIFIED", "HUMAN_WITNESSED_ATTESTED"].includes(item.verificationState) ? "pass" : "pending"}><ShieldCheck size={15} />{item.verificationState === "OFFICIAL_VERIFIED" ? m("officialSourceConfirmed") : item.verificationState === "HUMAN_WITNESSED_ATTESTED" ? m("fourEyesConfirmed") : m("officialSourcePending")}</span>
      <span className={verification?.subjectMatch === "MATCH" ? "pass" : verification?.subjectMatch === "MISMATCH" ? "fail" : "pending"}><UserCheck size={15} />{verification?.subjectMatch === "MATCH" ? m("personMatchConfirmed") : verification?.subjectMatch === "MISMATCH" ? m("personMismatch") : m("personMatchPending")}</span>
      <span><Fingerprint size={15} />{verification?.truthBoundary === "AUTHORIZED_MACHINE_TO_MACHINE" ? m("authorizedApiTruth") : verification ? m("humanWitnessedTruth") : m("noOfficialTruth")}</span>
    </div>
    {verification ? <div className="rec-truth-boundary"><strong>{m("truthBoundary")}</strong><span>{m("truthBoundaryDetail", { receipt: verification.officialReceiptId || "—" })}</span></div> : null}
    {canApprove && malwareCleared && item.requiresOfficialVerification && ["BARCODE_EXTRACTION_PENDING", "OFFICIAL_REVIEW_FAILED"].includes(item.verificationState) ? <button type="button" className="rec-verify-action" onClick={() => onVerify(item)}><ShieldCheck size={16} />{m("recordOfficialVerification")}</button> : null}
    {canApprove && malwareCleared && item.verificationState === "HUMAN_WITNESSED_PENDING_ATTESTATION" ? <button type="button" className="rec-verify-action" onClick={() => onAttest(item)}><UserCheck size={16} />{m("attestSecondReviewer")}</button> : null}
  </article>;
}

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
  const [documentTypes, setDocumentTypes] = useState({});
  const [verifyTarget, setVerifyTarget] = useState(null);
  const [attestTarget, setAttestTarget] = useState(null);
  const [attestationNote, setAttestationNote] = useState("");
  const [verification, setVerification] = useState({ result: "VERIFIED", subjectMatch: "MATCH", receiptId: "", responseSha256: "", issuedAt: "", note: "" });
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
    try { await uploadRecruitmentCandidateEvidence(request.id, candidateId, file, documentTypes[candidateId] || "OTHER"); await changed(m("candidateEvidenceAdded")); }
    catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  async function recordVerification(event) {
    event.preventDefault();
    if (!verifyTarget || !verification.receiptId.trim() || !/^[0-9a-f]{64}$/.test(verification.responseSha256.trim()) || !verification.note.trim()) { setError(m("verificationFieldsRequired")); return; }
    setBusy(`verify-${verifyTarget.candidateId}`);
    try {
      await verifyRecruitmentCandidateDocument(request.id, verifyTarget.candidateId, {
        evidence_sha256: verifyTarget.item.sha256, result: verification.result, subject_match: verification.subjectMatch,
        document_type: verifyTarget.item.documentType, official_receipt_id: verification.receiptId.trim(),
        official_response_sha256: verification.responseSha256.trim(), issued_at: verification.issuedAt || null, note: verification.note.trim(),
      });
      setVerifyTarget(null); setVerification({ result: "VERIFIED", subjectMatch: "MATCH", receiptId: "", responseSha256: "", issuedAt: "", note: "" });
      await changed(m("verificationRecorded"));
    } catch (error) { setError(error.message); }
    finally { setBusy(""); }
  }

  async function attestVerification(event) {
    event.preventDefault();
    if (!attestTarget || !attestationNote.trim()) { setError(m("attestationNoteRequired")); return; }
    setBusy(`attest-${attestTarget.candidateId}`);
    try { await attestRecruitmentCandidateDocument(request.id, attestTarget.candidateId, attestTarget.item.sha256, attestationNote.trim()); setAttestTarget(null); setAttestationNote(""); await changed(m("attestationRecorded")); }
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
        const evidence = row.evidence || [];
        const evidenceCount = row.evidenceCount ?? evidence.length;
        const gate = candidateEvidenceGate(evidence);
        const trustTitle = !gate.evidenceCount ? m("evidenceRequiredForApproval") : gate.unsafeCount ? m("contentSafetyBlocked", { count: gate.unsafeCount }) : gate.officialUnresolvedCount ? m("exceptionReview", { count: gate.officialUnresolvedCount }) : m("documentGateClear");
        const trustDetail = !gate.evidenceCount ? m("evidenceRequiredForApprovalDetail") : gate.unsafeCount ? m("contentSafetyBlockedDetail") : gate.officialUnresolvedCount ? m("exceptionReviewDetail") : m("documentGateClearDetail");
        return <article key={row.id} className="rec-candidate-card"><div className="rec-candidate-head"><div><strong>{row.fullName}</strong><small>{row.sourceRef} · {row.id}</small></div><CandidateStatus value={row.status} m={m} /></div><div className="rec-candidate-trust"><div><ShieldCheck size={17} /><span><strong>{trustTitle}</strong><small>{trustDetail}</small></span></div><span className={`rec-trust-score ${gate.canApprove ? "clear" : "blocked"}`}>{gate.canApprove ? m("approvalReady") : m("approvalBlocked")}</span></div><div className="rec-candidate-evidence"><FileCheck2 size={16} /><span>{m("evidenceCount", { count: evidenceCount })}</span>{canApprove && row.status !== "HIRED" && row.status !== "REJECTED" ? <div className="rec-upload-cluster"><select aria-label={m("documentType")} value={documentTypes[row.id] || "OTHER"} onChange={(e) => setDocumentTypes({ ...documentTypes, [row.id]: e.target.value })}>{DOCUMENT_TYPES.map((type) => <option key={type} value={type}>{m(`document${type}`)}</option>)}</select><label className="rec-mini-upload"><Upload size={15} />{busy === `evidence-${row.id}` ? m("uploading") : m("uploadEvidence")}<input type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={(e) => uploadEvidence(row.id, e.target.files?.[0])} /></label></div> : null}</div>
          {row.evidence?.length ? <div className="rec-document-list">{row.evidence.map((item) => <CandidateEvidence key={item.sha256} item={item} candidateId={row.id} requestId={request.id} canApprove={canApprove} m={m} onVerify={(target) => setVerifyTarget({ candidateId: row.id, item: target })} onAttest={(target) => setAttestTarget({ candidateId: row.id, item: target })} />)}</div> : null}
          {canApprove && row.status === "REVIEW_PENDING" ? <div className="rec-candidate-review"><input value={reviewNotes[row.id] || ""} onChange={(e) => setReviewNotes({ ...reviewNotes, [row.id]: e.target.value })} placeholder={m("decisionReason")} /><button className="reject" onClick={() => decide(row.id, "REJECTED")} disabled={busy === `decision-${row.id}`}><X size={15} /> {m("reject")}</button><button className="approve" title={!gate.canApprove ? trustDetail : undefined} onClick={() => decide(row.id, "APPROVED")} disabled={busy === `decision-${row.id}` || !gate.canApprove}><Check size={15} /> {m("approve")}</button>{!gate.canApprove ? <small className="rec-approval-block-reason">{trustDetail}</small> : null}</div> : null}
          {canApprove && row.status === "APPROVED" ? <button className="rec-primary rec-hire-open" onClick={() => setHireCandidate(row)}><Rocket size={16} /> {m("employeeMasterShift")}</button> : null}
          {row.status === "HIRED" ? <div className="rec-candidate-hired"><BadgeCheck size={16} /> {m("hiredMaster", { employee: row.employeeId || m("statusHired") })}</div> : null}
        </article>;
      })}
      {!candidates.length ? <div className="rec-empty">{m("noCandidate")}</div> : null}
    </div>

    {verifyTarget ? <div className="rec-verification-backdrop" onMouseDown={() => setVerifyTarget(null)}><form className="rec-verification-dialog" onSubmit={recordVerification} onMouseDown={(event) => event.stopPropagation()}><header><div><span className="rec-kicker">{m("officialVerification")}</span><h3>{m(`document${verifyTarget.item.documentType}`)}</h3><p>{m("officialVerificationDesc")}</p></div><button type="button" className="rec-modal-close-inline" onClick={() => setVerifyTarget(null)}><X size={17} /></button></header><div className="rec-truth-warning"><CircleAlert size={18} /><span><strong>{m("truthBoundary")}</strong>{m("humanWitnessWarning")}</span></div><div className="rec-form-grid"><label>{m("verificationResult")}<select value={verification.result} onChange={(e) => setVerification({ ...verification, result: e.target.value })}><option value="VERIFIED">{m("resultVerified")}</option><option value="FAILED">{m("resultFailed")}</option><option value="INCONCLUSIVE">{m("resultInconclusive")}</option></select></label><label>{m("subjectMatch")}<select value={verification.subjectMatch} onChange={(e) => setVerification({ ...verification, subjectMatch: e.target.value })}><option value="MATCH">{m("match")}</option><option value="MISMATCH">{m("mismatch")}</option><option value="NOT_CHECKED">{m("notChecked")}</option></select></label><label>{m("officialReceiptId")}<input value={verification.receiptId} onChange={(e) => setVerification({ ...verification, receiptId: e.target.value })} /></label><label>{m("issuedAt")}<input type="date" value={verification.issuedAt} onChange={(e) => setVerification({ ...verification, issuedAt: e.target.value })} /></label><label className="wide">{m("officialResponseDigest")}<input value={verification.responseSha256} onChange={(e) => setVerification({ ...verification, responseSha256: e.target.value.toLowerCase().replace(/[^0-9a-f]/g, "").slice(0, 64) })} placeholder={m("sha256Placeholder")} /></label><label className="wide">{m("verificationNote")}<textarea value={verification.note} onChange={(e) => setVerification({ ...verification, note: e.target.value })} /></label></div><button className="rec-primary" disabled={busy === `verify-${verifyTarget.candidateId}`}><ShieldCheck size={16} />{m("sealVerification")}</button></form></div> : null}

    {attestTarget ? <div className="rec-verification-backdrop" onMouseDown={() => setAttestTarget(null)}><form className="rec-verification-dialog" onSubmit={attestVerification} onMouseDown={(event) => event.stopPropagation()}><header><div><span className="rec-kicker">{m("fourEyesReview")}</span><h3>{m(`document${attestTarget.item.documentType}`)}</h3><p>{m("fourEyesReviewDesc")}</p></div><button type="button" className="rec-modal-close-inline" onClick={() => setAttestTarget(null)}><X size={17} /></button></header><div className="rec-truth-warning"><Fingerprint size={18} /><span><strong>{m("independentReviewer")}</strong>{m("independentReviewerWarning")}</span></div><label>{m("attestationNote")}<textarea value={attestationNote} onChange={(e) => setAttestationNote(e.target.value)} /></label><button className="rec-primary" disabled={busy === `attest-${attestTarget.candidateId}`}><UserCheck size={16} />{m("completeAttestation")}</button></form></div> : null}

    {hireCandidate ? <form className="rec-hire-form" onSubmit={activate}><header><div><span className="rec-kicker">{m("hireActivation")}</span><h3>{hireCandidate.fullName}</h3></div><button type="button" className="rec-modal-close-inline" onClick={() => { setHireCandidate(null); setHire({ ...hire, tckn: "" }); }}><X size={17} /></button></header><div className="rec-form-grid"><label>{m("hrEmployeeId")}<input value={hire.employeeId} onChange={(e) => setHire({ ...hire, employeeId: e.target.value })} /></label><label>{m("rosterId")}<input value={hire.rosterId} onChange={(e) => setHire({ ...hire, rosterId: e.target.value })} /></label><label>{m("tckn")}<input type="password" inputMode="numeric" autoComplete="new-password" value={hire.tckn} onChange={(e) => setHire({ ...hire, tckn: e.target.value.replace(/\D/g, "").slice(0, 11) })} /></label><label>{m("hireDate")}<input type="date" value={hire.employmentStart} onChange={(e) => setHire({ ...hire, employmentStart: e.target.value, shiftDate: e.target.value })} /></label><label>{m("email")}<input value={hire.email} onChange={(e) => setHire({ ...hire, email: e.target.value })} /></label><label>{m("phone")}<input value={hire.phone} onChange={(e) => setHire({ ...hire, phone: e.target.value })} /></label><label>{m("firstShiftDate")}<input type="date" value={hire.shiftDate} onChange={(e) => setHire({ ...hire, shiftDate: e.target.value })} /></label><label>{m("shiftStart")}<input type="time" value={hire.shiftStart} onChange={(e) => setHire({ ...hire, shiftStart: e.target.value })} /></label><label>{m("shiftEnd")}<input type="time" value={hire.shiftEnd} onChange={(e) => setHire({ ...hire, shiftEnd: e.target.value })} /></label><label>{m("breakMinutes")}<input type="number" min="0" max="180" value={hire.breakMinutes} onChange={(e) => setHire({ ...hire, breakMinutes: e.target.value })} /></label></div><p className="rec-config-note">{m("tcknNote")}</p><button className="rec-primary" disabled={busy === `hire-${hireCandidate.id}`}><Rocket size={16} /> {busy === `hire-${hireCandidate.id}` ? m("activating") : m("hireAndShift")}</button></form> : null}
  </section>;
}
