import React, { useEffect, useMemo, useState } from "react";
import { Clipboard, FileKey2, Link2, RefreshCw, ShieldCheck } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { issueRecruitmentCandidateUploadCapability, loadRecruitment } from "./recruitmentApi.js";
import "./recruitmentCandidateDocumentCenter.css";

const DOCUMENT_TYPES = ["CRIMINAL_RECORD", "RESIDENCE", "SGK_SERVICE", "MILITARY_STATUS", "EDUCATION", "CIVIL_REGISTRY", "OTHER"];
const LABEL = {
  CRIMINAL_RECORD: "Adli Sicil", RESIDENCE: "Yerleşim Yeri", SGK_SERVICE: "SGK Hizmet", MILITARY_STATUS: "Askerlik Durumu",
  EDUCATION: "Öğrenim", CIVIL_REGISTRY: "Nüfus Kayıt", OTHER: "Diğer",
};

export default function RecruitmentCandidateDocumentCenter() {
  const { canAction } = useAuth();
  const canManage = canAction("recruitment", "approveRecruitmentRequest");
  const [data, setData] = useState(null);
  const [requestId, setRequestId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [documentType, setDocumentType] = useState("CRIMINAL_RECORD");
  const [expires, setExpires] = useState(1440);
  const [link, setLink] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setData(await loadRecruitment()); setError(""); }
    catch (err) { setError(err.message); }
  }
  useEffect(() => { if (canManage) load(); }, [canManage]);

  const requests = useMemo(() => (data?.requests || []).filter((row) => ["APPROVED", "SOURCING", "PARTIALLY_FILLED"].includes(row.status) && (row.candidates || []).some((candidate) => ["EVIDENCE_PENDING", "REVIEW_PENDING"].includes(candidate.status))), [data]);
  const selectedRequest = requests.find((row) => row.id === requestId) || null;
  const candidates = (selectedRequest?.candidates || []).filter((candidate) => ["EVIDENCE_PENDING", "REVIEW_PENDING"].includes(candidate.status));

  if (!canManage) return null;

  async function issue() {
    if (!requestId || !candidateId) { setError("Talep ve aday seçin."); return; }
    setBusy(true); setError(""); setLink("");
    try {
      const result = await issueRecruitmentCandidateUploadCapability(requestId, candidateId, documentType, Number(expires));
      const url = `${window.location.origin}/candidate/documents#upload=${encodeURIComponent(result.capability)}&type=${encodeURIComponent(documentType)}`;
      setLink(url); setExpiresAt(result.expiresAt || "");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function copy() {
    if (!link) return;
    try { await navigator.clipboard.writeText(link); }
    catch { setError("Bağlantı panoya kopyalanamadı. Güvenli şekilde manuel kopyalayın."); }
  }

  return <section className="rec-doc-center">
    <header><div><span><FileKey2 size={16}/>Candidate document intake</span><h2>Güvenli aday belge bağlantısı</h2><p>Aday yalnız seçilen belge türünü bir kez yükleyebilir. Link, iç API veya belge okuma yetkisi vermez.</p></div><button type="button" onClick={load}><RefreshCw size={15}/>Yenile</button></header>
    <div className="rec-doc-center-trust"><ShieldCheck size={18}/><span>KMS/S3 encrypted quarantine · malware release gate · one-time capability · aday şifresi/e-Devlet parolası alınmaz</span></div>
    {error ? <div className="rec-doc-center-error">{error}</div> : null}
    <div className="rec-doc-center-grid">
      <label>İşe alım talebi<select value={requestId} onChange={(event) => { setRequestId(event.target.value); setCandidateId(""); setLink(""); }}><option value="">Seçin</option>{requests.map((row) => <option key={row.id} value={row.id}>{row.warehouseName} · {row.positionLabel} · {row.id}</option>)}</select></label>
      <label>Aday<select value={candidateId} onChange={(event) => { setCandidateId(event.target.value); setLink(""); }} disabled={!selectedRequest}><option value="">Seçin</option>{candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.fullName} · {candidate.sourceRef}</option>)}</select></label>
      <label>Belge türü<select value={documentType} onChange={(event) => { setDocumentType(event.target.value); setLink(""); }}>{DOCUMENT_TYPES.map((type) => <option value={type} key={type}>{LABEL[type]}</option>)}</select></label>
      <label>Link süresi<select value={expires} onChange={(event) => { setExpires(Number(event.target.value)); setLink(""); }}><option value={60}>1 saat</option><option value={360}>6 saat</option><option value={1440}>24 saat</option><option value={4320}>3 gün</option></select></label>
    </div>
    <button className="rec-doc-issue" type="button" onClick={issue} disabled={busy || !candidateId}><Link2 size={16}/>{busy ? "Üretiliyor…" : "Tek kullanımlık link üret"}</button>
    {link ? <div className="rec-doc-link"><div><strong>Güvenli aday bağlantısı</strong><code>{link}</code>{expiresAt ? <small>Geçerlilik: {new Date(expiresAt).toLocaleString()}</small> : null}</div><button type="button" onClick={copy}><Clipboard size={16}/>Kopyala</button><p>Capability URL fragment içindedir; sunucu access log’una gitmez. Linki ticket, açık Slack kanalı veya ortak dokümana yapıştırmayın.</p></div> : null}
  </section>;
}
