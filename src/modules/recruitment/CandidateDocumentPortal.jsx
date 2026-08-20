import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, FileUp, LockKeyhole, ShieldCheck } from "lucide-react";

import { uploadCandidateEvidenceWithCapability } from "./recruitmentApi.js";
import "./candidateDocumentPortal.css";

const SESSION_KEY = "eay_candidate_document_upload_capability";
const SESSION_TYPE_KEY = "eay_candidate_document_type";
const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED = new Set(["application/pdf", "image/jpeg", "image/png"]);
const LABELS = {
  CRIMINAL_RECORD: "Adli Sicil Belgesi",
  RESIDENCE: "Yerleşim Yeri Belgesi",
  SGK_SERVICE: "SGK Hizmet Dökümü",
  MILITARY_STATUS: "Askerlik Durum Belgesi",
  EDUCATION: "Öğrenim Belgesi",
  CIVIL_REGISTRY: "Nüfus Kayıt Belgesi",
  OTHER: "İşe giriş belgesi",
};

function consumeFragment() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const capability = params.get("upload")?.trim() || "";
  const documentType = params.get("type")?.trim().toUpperCase() || "";
  if (capability) sessionStorage.setItem(SESSION_KEY, capability);
  if (documentType) sessionStorage.setItem(SESSION_TYPE_KEY, documentType);
  if (window.location.hash) window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  return {
    capability: capability || sessionStorage.getItem(SESSION_KEY) || "",
    documentType: documentType || sessionStorage.getItem(SESSION_TYPE_KEY) || "",
  };
}

export default function CandidateDocumentPortal() {
  const initial = useMemo(consumeFragment, []);
  const [capability, setCapability] = useState(initial.capability);
  const [documentType] = useState(initial.documentType);
  const [file, setFile] = useState(null);
  const [state, setState] = useState(initial.capability && initial.documentType ? "ready" : "invalid");
  const [error, setError] = useState("");
  const label = LABELS[documentType] || documentType || "Belge";

  useEffect(() => () => { setFile(null); }, []);

  function choose(next) {
    setError("");
    if (!next) { setFile(null); return; }
    if (!ACCEPTED.has(next.type)) { setError("Yalnızca PDF, JPG veya PNG dosyası yükleyebilirsiniz."); return; }
    if (next.size <= 0 || next.size > MAX_BYTES) { setError("Dosya boyutu 10 MB veya altında olmalıdır."); return; }
    setFile(next);
  }

  async function upload() {
    if (!file || !capability || !documentType) return;
    setState("uploading"); setError("");
    try {
      const result = await uploadCandidateEvidenceWithCapability(capability, documentType, file);
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_TYPE_KEY);
      setCapability(""); setFile(null); setState("done");
      window.dispatchEvent(new Event("eay:recruitment:external-change"));
      if (!result?.accepted) throw new Error("Belge kabul makbuzu alınamadı.");
    } catch (err) {
      setState("ready");
      setError(err.message || "Belge yüklenemedi.");
    }
  }

  return <main className="cand-doc-page">
    <section className="cand-doc-card">
      <div className="cand-doc-brand"><span>EAY</span><strong>Secure Hiring</strong></div>
      {state === "invalid" ? <div className="cand-doc-state error"><CircleAlert size={28}/><h1>Belge bağlantısı geçersiz</h1><p>Bu bağlantı eksik, kullanılmış veya süresi dolmuş olabilir. İK ekibinden yeni güvenli bağlantı isteyin.</p></div> : null}
      {state === "done" ? <div className="cand-doc-state success"><CheckCircle2 size={34}/><h1>Belgeniz güvenli şekilde alındı</h1><p>Dosya karantinaya alındı ve güvenlik taramasına gönderildi. Bu bağlantı artık tekrar kullanılamaz.</p><small>Yüklenen dosya bu ekrandan görüntülenemez veya indirilemez.</small></div> : null}
      {["ready", "uploading"].includes(state) ? <>
        <header><span className="cand-doc-kicker"><LockKeyhole size={15}/>Tek kullanımlık güvenli yükleme</span><h1>{label}</h1><p>Bu bağlantı yalnız yukarıdaki belge türü için yetkilidir. EAY sizden bu ekranda parola, e-Devlet şifresi veya OTP istemez.</p></header>
        <div className="cand-doc-trust"><ShieldCheck size={19}/><div><strong>Şifreli ve sınırlandırılmış teslim</strong><span>Belge okuma/listeleme yetkisi verilmez · Tek yükleme · Maksimum 10 MB</span></div></div>
        {error ? <div className="cand-doc-alert"><CircleAlert size={17}/>{error}</div> : null}
        <label className={`cand-doc-drop ${file ? "has-file" : ""}`}>
          <FileUp size={28}/><strong>{file ? file.name : "PDF, JPG veya PNG seçin"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "Dosyanız seçilene kadar hiçbir veri gönderilmez."}</span>
          <input type="file" accept="application/pdf,image/jpeg,image/png" hidden disabled={state === "uploading"} onChange={(event) => choose(event.target.files?.[0] || null)}/>
        </label>
        <button className="cand-doc-submit" type="button" disabled={!file || state === "uploading"} onClick={upload}>{state === "uploading" ? "Güvenli olarak yükleniyor…" : "Belgeyi güvenli gönder"}</button>
        <footer>Bağlantıyı ortak bilgisayarda kullandıysanız işlem tamamlandığında bu sekmeyi kapatın.</footer>
      </> : null}
    </section>
  </main>;
}
