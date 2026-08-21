import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FileCheck2, ShieldCheck, XCircle } from "lucide-react";

import { decideCandidateOffer, viewCandidateOffer } from "./recruitmentApi.js";
import "./candidateOfferPortal.css";


const COPY = {
  tr: {
    eyebrow: "EAY Güvenli Aday Portalı",
    title: "İş teklifiniz",
    intro: "Teklif detaylarını kontrol edin. Kararınız tek kullanımlık güvenli bağlantıyla kaydedilir.",
    loading: "Teklif doğrulanıyor…",
    invalid: "Bu teklif bağlantısı geçersiz, kullanılmış veya süresi dolmuş olabilir.",
    position: "Pozisyon", location: "Çalışma yeri", start: "Başlangıç tarihi", employment: "Çalışma tipi",
    compensation: "Ücret", benefits: "Yan haklar", probation: "Deneme süresi / koşullar", expires: "Teklif geçerlilik sonu",
    fingerprint: "Teklif parmak izi", acknowledgement: "Teklif detaylarını okudum ve kararımın kaydedilmesini onaylıyorum.",
    accept: "Teklifi kabul et", decline: "Teklifi reddet", accepting: "Karar kaydediliyor…",
    accepted: "Teklif kabul edildi", declined: "Teklif reddedildi",
    acceptedDetail: "Kararınız güvenli şekilde kaydedildi. Onboarding adımları ilgili ekipler için oluşturuldu.",
    declinedDetail: "Kararınız güvenli şekilde kaydedildi.",
    truthTitle: "Karar kaydı hakkında", truth: "Bu işlem tek kullanımlık aday karar kaydıdır; nitelikli/kanuni elektronik imza olarak sunulmaz.",
    support: "Sorun devam ederse İK ile iletişime geçin.",
  },
  en: {
    eyebrow: "EAY Secure Candidate Portal",
    title: "Your employment offer",
    intro: "Review the offer details. Your decision is recorded through a single-use secure capability.",
    loading: "Verifying offer…",
    invalid: "This offer link may be invalid, already used, or expired.",
    position: "Position", location: "Work location", start: "Start date", employment: "Employment type",
    compensation: "Compensation", benefits: "Benefits", probation: "Probation / conditions", expires: "Offer expires",
    fingerprint: "Offer fingerprint", acknowledgement: "I reviewed the offer details and authorize EAY to record my decision.",
    accept: "Accept offer", decline: "Decline offer", accepting: "Recording decision…",
    accepted: "Offer accepted", declined: "Offer declined",
    acceptedDetail: "Your decision was securely recorded. Onboarding tasks were created for the responsible teams.",
    declinedDetail: "Your decision was securely recorded.",
    truthTitle: "About this decision record", truth: "This is a single-use candidate decision record; it is not represented as a qualified/legal electronic signature.",
    support: "Contact HR if the problem continues.",
  },
  de: {
    eyebrow: "EAY Sicheres Bewerberportal", title: "Ihr Stellenangebot", intro: "Prüfen Sie die Angebotsdetails. Ihre Entscheidung wird über einen einmaligen sicheren Zugang erfasst.",
    loading: "Angebot wird geprüft…", invalid: "Dieser Angebotslink ist möglicherweise ungültig, bereits verwendet oder abgelaufen.",
    position: "Position", location: "Arbeitsort", start: "Startdatum", employment: "Beschäftigungsart", compensation: "Vergütung", benefits: "Zusatzleistungen", probation: "Probezeit / Bedingungen", expires: "Angebot gültig bis", fingerprint: "Angebots-Fingerabdruck",
    acknowledgement: "Ich habe die Angebotsdetails gelesen und stimme der Aufzeichnung meiner Entscheidung zu.", accept: "Angebot annehmen", decline: "Angebot ablehnen", accepting: "Entscheidung wird gespeichert…", accepted: "Angebot angenommen", declined: "Angebot abgelehnt", acceptedDetail: "Ihre Entscheidung wurde sicher gespeichert. Onboarding-Aufgaben wurden erstellt.", declinedDetail: "Ihre Entscheidung wurde sicher gespeichert.", truthTitle: "Zu diesem Entscheidungsnachweis", truth: "Dies ist ein einmaliger Entscheidungsnachweis und keine qualifizierte/rechtliche elektronische Signatur.", support: "Wenden Sie sich bei Problemen an HR.",
  },
  ar: {
    eyebrow: "بوابة EAY الآمنة للمرشحين", title: "عرض العمل", intro: "راجع تفاصيل العرض. يتم تسجيل قرارك عبر صلاحية آمنة للاستخدام مرة واحدة.",
    loading: "جارٍ التحقق من العرض…", invalid: "قد يكون رابط العرض غير صالح أو مستخدماً أو منتهي الصلاحية.",
    position: "الوظيفة", location: "مكان العمل", start: "تاريخ البدء", employment: "نوع التوظيف", compensation: "التعويض", benefits: "المزايا", probation: "فترة التجربة / الشروط", expires: "انتهاء العرض", fingerprint: "بصمة العرض",
    acknowledgement: "قرأت تفاصيل العرض وأوافق على تسجيل قراري.", accept: "قبول العرض", decline: "رفض العرض", accepting: "جارٍ تسجيل القرار…", accepted: "تم قبول العرض", declined: "تم رفض العرض", acceptedDetail: "تم تسجيل قرارك بأمان وتم إنشاء مهام الانضمام للفرق المعنية.", declinedDetail: "تم تسجيل قرارك بأمان.", truthTitle: "حول سجل القرار", truth: "هذا سجل قرار لمرة واحدة ولا يُقدَّم كتوقيع إلكتروني مؤهل أو قانوني.", support: "تواصل مع الموارد البشرية إذا استمرت المشكلة.",
  },
};

function localeKey() {
  const raw = (navigator.language || "en").toLowerCase();
  if (raw.startsWith("tr")) return "tr";
  if (raw.startsWith("de")) return "de";
  if (raw.startsWith("ar")) return "ar";
  return "en";
}

function readCapability() {
  const params = new URLSearchParams(String(window.location.hash || "").replace(/^#/, ""));
  const fromHash = params.get("offer");
  if (fromHash) {
    try { sessionStorage.setItem("eay.candidate.offer.capability", fromHash); } catch { /* memory-only browser */ }
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    return fromHash;
  }
  try { return sessionStorage.getItem("eay.candidate.offer.capability") || ""; } catch { return ""; }
}

function clearCapability() {
  try { sessionStorage.removeItem("eay.candidate.offer.capability"); } catch { /* noop */ }
}

function money(pkg) {
  const amount = Number(pkg?.compensationAmount);
  if (!Number.isFinite(amount)) return "—";
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: pkg.currency || "TRY", maximumFractionDigits: 2 }).format(amount);
  } catch { return `${amount.toLocaleString()} ${pkg.currency || ""}`.trim(); }
}

export default function CandidateOfferPortal() {
  const language = localeKey();
  const t = COPY[language] || COPY.en;
  const [capability] = useState(() => readCapability());
  const [offer, setOffer] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [decision, setDecision] = useState("");
  const rtl = language === "ar";

  useEffect(() => {
    document.title = t.title;
    if (!capability) { setError(t.invalid); return; }
    let active = true;
    viewCandidateOffer(capability)
      .then((result) => { if (active) setOffer(result); })
      .catch(() => { if (active) { clearCapability(); setError(t.invalid); } });
    return () => { active = false; };
  }, [capability, t.invalid, t.title]);

  const pkg = offer?.package || {};
  const shortHash = useMemo(() => offer?.packageSha256 ? `${offer.packageSha256.slice(0, 12)}…${offer.packageSha256.slice(-8)}` : "—", [offer]);

  async function record(nextDecision) {
    if (!acknowledged || busy || !capability) return;
    setBusy(true); setError("");
    try {
      const result = await decideCandidateOffer(capability, nextDecision);
      clearCapability();
      setDecision(result.decision || nextDecision);
      setOffer(null);
    } catch { setError(t.invalid); }
    finally { setBusy(false); }
  }

  return <main className="candidate-offer-page" dir={rtl ? "rtl" : "ltr"}>
    <section className="candidate-offer-shell" aria-live="polite">
      <div className="candidate-offer-brand"><ShieldCheck size={22} /><span>{t.eyebrow}</span></div>
      {decision ? <div className="candidate-offer-result" role="status">
        {decision === "ACCEPTED" ? <CheckCircle2 size={48} /> : <XCircle size={48} />}
        <h1>{decision === "ACCEPTED" ? t.accepted : t.declined}</h1>
        <p>{decision === "ACCEPTED" ? t.acceptedDetail : t.declinedDetail}</p>
      </div> : error ? <div className="candidate-offer-result error" role="alert"><XCircle size={48} /><h1>{t.invalid}</h1><p>{t.support}</p></div> : !offer ? <div className="candidate-offer-loading" role="status"><span className="candidate-offer-spinner" />{t.loading}</div> : <>
        <header className="candidate-offer-header"><span>{t.eyebrow}</span><h1>{t.title}</h1><p>{t.intro}</p></header>
        <div className="candidate-offer-grid">
          <div><small>{t.position}</small><strong>{pkg.position || "—"}</strong></div>
          <div><small>{t.location}</small><strong>{pkg.workLocation || "—"}</strong></div>
          <div><small>{t.start}</small><strong>{pkg.employmentStart || "—"}</strong></div>
          <div><small>{t.employment}</small><strong>{pkg.employmentType || "—"}</strong></div>
          <div><small>{t.compensation}</small><strong>{money(pkg)}{pkg.compensationPeriod ? ` / ${pkg.compensationPeriod}` : ""}</strong></div>
          <div><small>{t.expires}</small><strong>{offer.expiresAt ? new Date(offer.expiresAt).toLocaleString() : "—"}</strong></div>
        </div>
        {pkg.benefitsSummary ? <div className="candidate-offer-section"><h2>{t.benefits}</h2><p>{pkg.benefitsSummary}</p></div> : null}
        {pkg.probationSummary ? <div className="candidate-offer-section"><h2>{t.probation}</h2><p>{pkg.probationSummary}</p></div> : null}
        <div className="candidate-offer-proof"><FileCheck2 size={18} /><div><small>{t.fingerprint}</small><code>{shortHash}</code></div></div>
        <div className="candidate-offer-truth"><ShieldCheck size={18} /><div><strong>{t.truthTitle}</strong><p>{t.truth}</p></div></div>
        {offer.decisionAvailable ? <>
          <label className="candidate-offer-consent"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /><span>{t.acknowledgement}</span></label>
          <div className="candidate-offer-actions"><button type="button" className="decline" disabled={!acknowledged || busy} onClick={() => record("DECLINED")}>{busy ? t.accepting : t.decline}</button><button type="button" className="accept" disabled={!acknowledged || busy} onClick={() => record("ACCEPTED")}>{busy ? t.accepting : t.accept}</button></div>
        </> : <div className="candidate-offer-truth"><CheckCircle2 size={18} /><p>{t.invalid}</p></div>}
      </>}
    </section>
  </main>;
}
