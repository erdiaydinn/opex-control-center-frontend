import React, { useMemo, useState } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  BookOpenCheck,
  Boxes,
  CalendarClock,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  FileSignature,
  GraduationCap,
  Megaphone,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { workforceExperienceMessage } from "../../platform/i18n/workforceExperienceMessages.js";
import { workforceFlexibilityMessage } from "../../platform/i18n/workforceFlexibilityMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import WorkforceFlexibilityAdmin from "./WorkforceFlexibilityAdmin.jsx";
import WorkforceFlexibilityCenter from "./WorkforceFlexibilityCenter.jsx";

const EXPERIENCE_ITEMS = [
  { id: "documents", title: "Bordro ve Belgeler", detail: "1 belge imza bekliyor", icon: FileSignature, tone: "pink" },
  { id: "learning", title: "Eğitimlerim", detail: "İSG eğitimi · %72", icon: GraduationCap, tone: "purple" },
  { id: "survey", title: "Nabız Anketi", detail: "1 dakikada tamamla", icon: ClipboardList, tone: "blue" },
  { id: "assets", title: "Zimmetlerim", detail: "2 aktif zimmet", icon: Boxes, tone: "green" },
];

function ExperienceOverview({ onSelect, items }) {
  return <>
    <section className="wfx-experience-hero">
      <div><span>Çalışan merkezi</span><h1>İş hayatın, tek ekranda.</h1><p>Belgelerini imzala, eğitimlerini tamamla ve taleplerini İK beklemeden yönet.</p></div>
      <Sparkles size={28} />
    </section>
    <section className="wfx-experience-trust"><ShieldCheck size={18} /><div><strong>Gizlilik varsayılan ayar</strong><small>Yalnız sana ait kayıtlar ve rolün için gerekli bilgiler gösterilir.</small></div></section>
    <div className="wfx-experience-grid">
      {items.map((item) => { const Icon = item.icon; return <button type="button" key={item.id} onClick={() => onSelect(item.id)}><div className={item.tone}><Icon size={23} /></div><span><strong>{item.title}</strong><small>{item.detail}</small></span><ChevronRight size={18} /></button>; })}
    </div>
    <section className="wfx-experience-calendar"><header><CalendarDays size={19} /><div><strong>Yaklaşan</strong><small>Şirket takvimi</small></div></header><article><span>18</span><div><strong>Ağustos · İSG eğitimi</strong><small>14:00 · Fulya eğitim alanı</small></div><BadgeCheck size={18} /></article><article><span>30</span><div><strong>Ağustos · Dönem kapanışı</strong><small>Puantaj onay son günü</small></div><Megaphone size={18} /></article></section>
  </>;
}

function DocumentCenter({ signed, onSign }) {
  return <div className="wfx-service-detail"><div className="wfx-service-title"><FileSignature size={24} /><div><span>Bordro ve belgeler</span><h2>Dijital imza merkezi</h2></div></div><article className="wfx-document-card"><div><small>Temmuz 2026</small><strong>Ücret pusulası</strong><span>PDF · 248 KB · Kişiye özel</span></div><span className={`wfx-status ${signed ? "success" : "warning"}`}>{signed ? "İmzalandı" : "İmza bekliyor"}</span><button type="button" disabled={signed} onClick={onSign}>{signed ? <CheckCircle2 size={17} /> : <FileSignature size={17} />}{signed ? "İmza tamamlandı" : "Cihazda doğrula ve imzala"}</button></article><p className="wfx-service-note"><ShieldCheck size={16} />İmza işlemi cihaz doğrulamasına bağlanır; belge ve işlem özeti audit kaydına alınır.</p></div>;
}

function LearningCenter({ completed, onComplete }) {
  const progress = completed ? 100 : 72;
  return <div className="wfx-service-detail"><div className="wfx-service-title"><GraduationCap size={24} /><div><span>Eğitimlerim</span><h2>Rolüne özel gelişim</h2></div></div><article className="wfx-learning-card"><div className="wfx-learning-cover"><BookOpenCheck size={31} /><span>Zorunlu</span></div><div><small>İş sağlığı ve güvenliği</small><strong>Depoda Güvenli Çalışma 2026</strong><p>Son bölüm: Acil durum ve tahliye</p><div className="wfx-progress"><i style={{ width: `${progress}%` }} /></div><span>%{progress} tamamlandı</span><button type="button" disabled={completed} onClick={onComplete}>{completed ? "Eğitim tamamlandı" : "Kaldığın yerden devam et"}<ChevronRight size={17} /></button></div></article></div>;
}

function SurveyCenter({ answer, onAnswer }) {
  return <div className="wfx-service-detail"><div className="wfx-service-title"><ClipboardList size={24} /><div><span>Nabız anketi</span><h2>Bugün iş nasıl gidiyor?</h2></div></div>{answer ? <section className="wfx-survey-thanks"><CheckCircle2 size={34} /><strong>Teşekkürler</strong><p>Yanıtın anonim toplulaştırmaya dahil edildi. Tekil yanıt yöneticine gösterilmez.</p></section> : <section className="wfx-survey-card"><p>Bugünkü vardiya deneyimini nasıl değerlendirirsin?</p><div>{[1, 2, 3, 4, 5].map((score) => <button type="button" key={score} onClick={() => onAnswer(score)}><span>{["Çok zor", "Zor", "Normal", "İyi", "Harika"][score - 1]}</span><strong>{score}</strong></button>)}</div><small>Tek soru · yaklaşık 10 saniye</small></section>}</div>;
}

function AssetCenter() {
  return <div className="wfx-service-detail"><div className="wfx-service-title"><Boxes size={24} /><div><span>Zimmetlerim</span><h2>Sana teslim edilenler</h2></div></div><div className="wfx-asset-list"><article><div className="purple"><Boxes size={20} /></div><span><strong>El terminali · Zebra TC22</strong><small>SN: EAY-TC22-0184 · 08.07.2026</small></span><span className="wfx-status success">Aktif</span></article><article><div className="green"><BadgeCheck size={20} /></div><span><strong>Depo erişim kartı</strong><small>Kart: FUL-0184 · 04.01.2026</small></span><span className="wfx-status success">Teslim alındı</span></article></div></div>;
}

export function WorkforceExperienceCenter({ onBack }) {
  const { locale } = usePlatformPreferences();
  const [section, setSection] = useState("overview");
  const [signed, setSigned] = useState(false);
  const [courseCompleted, setCourseCompleted] = useState(false);
  const [surveyAnswer, setSurveyAnswer] = useState(null);
  const items = useMemo(() => [
    { id: "flexibility", title: workforceFlexibilityMessage(locale, "title"), detail: workforceFlexibilityMessage(locale, "detail"), icon: CalendarClock, tone: "pink" },
    ...EXPERIENCE_ITEMS,
  ], [locale]);
  const title = useMemo(() => items.find((item) => item.id === section)?.title || "Çalışan Merkezi", [items, section]);
  return <section className="wfx-mobile-screen wfx-experience-screen"><header className="wfx-mobile-header"><button type="button" onClick={section === "overview" ? onBack : () => setSection("overview")}><ArrowLeft size={22} /></button><strong>{title}</strong><span /></header><div className="wfx-mobile-info-content">{section === "overview" ? <ExperienceOverview onSelect={setSection} items={items} /> : null}{section === "flexibility" ? <WorkforceFlexibilityCenter /> : null}{section === "documents" ? <DocumentCenter signed={signed} onSign={() => setSigned(true)} /> : null}{section === "learning" ? <LearningCenter completed={courseCompleted} onComplete={() => setCourseCompleted(true)} /> : null}{section === "survey" ? <SurveyCenter answer={surveyAnswer} onAnswer={setSurveyAnswer} /> : null}{section === "assets" ? <AssetCenter /> : null}</div></section>;
}

export function WorkforceExperienceAdmin() {
  const { locale } = usePlatformPreferences();
  const m = (key, params) => workforceExperienceMessage(locale, key, params);
  const capabilities = [
    { icon: FileSignature, title: m("documentTitle"), value: m("documentValue"), detail: m("documentDetail"), tone: "pink" },
    { icon: GraduationCap, title: m("learningTitle"), value: m("learningValue"), detail: m("learningDetail"), tone: "purple" },
    { icon: ClipboardList, title: m("pulseTitle"), value: m("pulseValue"), detail: m("pulseDetail"), tone: "blue" },
    { icon: Boxes, title: m("assetTitle"), value: m("assetValue"), detail: m("assetDetail"), tone: "green" },
  ];
  return <div className="wfx-experience-admin">
    <section className="wfx-panel wfx-experience-admin-hero"><div><span>{m("adminEyebrow")}</span><h2>{m("adminHeading")}</h2><p>{m("adminIntro")}</p></div><div className="wfx-experience-score"><small>{m("experienceScore")}</small><strong>92</strong><span>{m("scoreTrend")}</span></div></section>
    <section className="wfx-experience-admin-grid">{capabilities.map((item) => { const Icon = item.icon; return <article className="wfx-panel" key={item.title}><div className={item.tone}><Icon size={22} /></div><span>{item.title}</span><strong>{item.value}</strong><small>{item.detail}</small></article>; })}</section>
    <WorkforceFlexibilityAdmin />
    <section className="wfx-panel wfx-market-difference"><header><div><span>{m("productStandard")}</span><h3>{m("outcomeHeading")}</h3></div><Sparkles size={24} /></header><div><article><BadgeCheck size={20} /><span><strong>{m("oneTapTitle")}</strong><small>{m("oneTapDetail")}</small></span></article><article><ShieldCheck size={20} /><span><strong>{m("privacyTitle")}</strong><small>{m("privacyDetail")}</small></span></article><article><CalendarDays size={20} /><span><strong>{m("contextTitle")}</strong><small>{m("contextDetail")}</small></span></article></div></section>
  </div>;
}
