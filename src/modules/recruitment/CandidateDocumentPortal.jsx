import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, ExternalLink, FileUp, LockKeyhole, ShieldCheck } from "lucide-react";

import { uploadCandidateEvidenceWithCapability } from "./recruitmentApi.js";
import "./candidateDocumentPortal.css";

const SESSION_KEY = "eay_candidate_document_upload_capability";
const SESSION_TYPE_KEY = "eay_candidate_document_type";
const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPTED = new Set(["application/pdf", "image/jpeg", "image/png"]);
const OFFICIAL_DOCUMENT_TYPES = new Set([
  "CRIMINAL_RECORD",
  "RESIDENCE",
  "SGK_SERVICE",
  "MILITARY_STATUS",
  "EDUCATION",
  "CIVIL_REGISTRY",
]);
const EDEVLET_HOME = "https://www.turkiye.gov.tr/";
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
  const [officialFlow, setOfficialFlow] = useState("idle");
  const label = LABELS[documentType] || documentType || "Belge";
  const isOfficial = OFFICIAL_DOCUMENT_TYPES.has(documentType);

  useEffect(() => () => { setFile(null); }, []);

  useEffect(() => {
    if (officialFlow !== "launched") return undefined;
    const markReturned = () => setOfficialFlow((value) => value === "launched" ? "returned" : value);
    window.addEventListener("focus", markReturned);
    document.addEventListener("visibilitychange", markReturned);
    return () => {
      window.removeEventListener("focus", markReturned);
      document.removeEventListener("visibilitychange", markReturned);
    };
  }, [officialFlow]);

  function choose(next) {
    setError("");
    if (!next) { setFile(null); return; }
    if (!ACCEPTED.has(next.type)) { setError("Yalnızca PDF, JPG veya PNG dosyası yükleyebilirsiniz."); return; }
    if (next.size <= 0 || next.size > MAX_BYTES) { setError("Dosya boyutu 10 MB veya altında olmalıdır."); return; }
    setFile(next);
  }

  function openEDevlet() {
    setError("");
    const opened = window.open(EDEVLET_HOME, "_blank", "noopener,noreferrer");
    setOfficialFlow(opened ? "launched" : "blocked");
    if (!opened) setError("Tarayıcı yeni sekmeyi engelledi. Aşağıdaki bağlantıyı yeni sekmede açın ve işlemden sonra EAY'a dönün.");
  }

  async function upload() {
    if (!file || !capability || !documentType) return;
    setState("uploading"); setError("");
    try {
      const result = await uploadCandidateEvidenceWithCapability(capability, documentType, file);
      if (!result?.accepted) throw new Error("Belge kabul makbuzu alınamadı.");
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_TYPE_KEY);
      setCapability(""); setFile(null); setState("done");
      window.dispatchEvent(new Event("eay:recruitment:external-change"));
    } catch (err) {
      setState("ready");
      setError(err.message || "Belge yüklenemedi.");
    }
  }

  return <main className="cand-doc-page">
    <section className="cand-doc-card">
      <div className="cand-doc-brand"><span>EAY</span><strong>Secure Hiring</strong></div>
      {state === "invalid" ? <div className="cand-doc-state error"><CircleAlert size={28}/><h1>Belge bağlantısı geçersiz</h1><p>Bu bağlantı eksik, kullanılmış veya süresi dolmuş olabilir. İK ekibinden yeni güvenli bağlantı isteyin.</p></div> : null}
      {state === "done" ? <div className="cand-doc-state success"><CheckCircle2 size={34}/><h1>Belgeniz güvenli şekilde alındı</h1><p>Dosya karantinaya alındı ve güvenlik taramasına gönderildi. Resmî doğrulama gereken belgeler barkod/karekod ve ikinci yetkili kontrolü tamamlanmadan onaylanmaz.</p><small>Yüklenen dosya bu ekrandan görüntülenemez veya indirilemez.</small></div> : null}
      {["ready", "uploading"].includes(state) ? <>
        <header><span className="cand-doc-kicker"><LockKeyhole size={15}/>Tek kullanımlık güvenli yükleme</span><h1>{label}</h1><p>Bu bağlantı yalnız yukarıdaki belge türü için yetkilidir. EAY sizden bu ekranda parola, e-Devlet şifresi, OTP veya e-Devlet oturum bilgisi istemez.</p></header>
        <div className="cand-doc-trust"><ShieldCheck size={19}/><div><strong>Şifreli ve sınırlandırılmış teslim</strong><span>Belge okuma/listeleme yetkisi verilmez · Tek yükleme · Maksimum 10 MB</span></div></div>
        {isOfficial ? <div className="cand-doc-official">
          <div><strong>1 · Barkodlu belgeyi e-Devlet'te siz oluşturun</strong><p>e-Devlet ayrı sekmede açılır. Giriş, şifre, OTP, CAPTCHA ve oturum tamamen sizin tarayıcınızda kalır. EAY bu sekmeyi okuyamaz ve yönetmez.</p></div>
          <button type="button" className="cand-doc-official-open" disabled={state === "uploading"} onClick={openEDevlet}><ExternalLink size={16}/>e-Devlet'i güvenli sekmede aç</button>
          {officialFlow === "returned" ? <div className="cand-doc-return"><CheckCircle2 size={17}/><span>EAY'a geri döndünüz. İndirdiğiniz barkodlu PDF'yi aşağıdan seçerek devam edin.</span></div> : null}
          {officialFlow === "blocked" ? <a className="cand-doc-official-link" href={EDEVLET_HOME} target="_blank" rel="noopener noreferrer">turkiye.gov.tr adresini yeni sekmede aç</a> : null}
          <small>Tarayıcı güvenliği gereği EAY, bilgisayarınızdaki İndirilenler klasörünü otomatik okuyamaz. Dosyayı yalnızca sizin seçmeniz gerekir.</small>
        </div> : null}
        {error ? <div className="cand-doc-alert"><CircleAlert size={17}/>{error}</div> : null}
        <label className={`cand-doc-drop ${file ? "has-file" : ""}`}>
          <FileUp size={28}/><strong>{file ? file.name : isOfficial ? "2 · Barkodlu PDF/JPG/PNG dosyanızı seçin" : "PDF, JPG veya PNG seçin"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "Dosyanız seçilene kadar hiçbir veri gönderilmez."}</span>
          <input type="file" accept="application/pdf,image/jpeg,image/png" hidden disabled={state === "uploading"} onChange={(event) => choose(event.target.files?.[0] || null)}/>
        </label>
        <button className="cand-doc-submit" type="button" disabled={!file || state === "uploading"} onClick={upload}>{state === "uploading" ? "Güvenli olarak yükleniyor…" : "Belgeyi güvenli gönder"}</button>
        <footer>Bağlantıyı ortak bilgisayarda kullandıysanız işlem tamamlandığında hem EAY hem e-Devlet sekmelerini kapatın.</footer>
      </> : null}
    </section>
  </main>;
}
