import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, CircleAlert, Clock3, RefreshCw, ShieldCheck, UserRoundCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { loadMyRecruitmentOnboardingTasks, updateRecruitmentOnboardingTask } from "./recruitmentApi.js";
import "./recruitmentOnboardingTasks.css";

const COPY = {
  tr: {
    eyebrow: "Candidate → Day One", title: "Onboarding görevlerim", desc: "Yalnızca sizin ekip sorumluluğunuzdaki ve yetkili depo kapsamınızdaki işe giriş görevleri gösterilir.",
    back: "Ana sayfa", refresh: "Yenile", includeDone: "Tamamlananları göster", empty: "Bekleyen onboarding göreviniz yok.",
    due: "Son tarih", owner: "Sorumlu", dependencies: "Bağımlılıklar", required: "Zorunlu", optional: "Opsiyonel", overdue: "Süresi geçti", today: "Bugün", candidate: "Aday", warehouse: "Depo",
    note: "İşlem notu", notePlaceholder: "Tamamlanma kanıtı veya blocker açıklaması…", start: "Başlat", blocked: "Bloke", complete: "Tamamla", saving: "Kaydediliyor…",
    done: "Görev güncellendi.", blockedNeedsNote: "Bloke edilen görev için açıklama girin.", governance: "Zorunlu görevler bu ekrandan atlanamaz; waiver yalnız merkezi onboarding yönetim yetkisiyle yapılabilir.",
  },
  en: {
    eyebrow: "Candidate → Day One", title: "My onboarding tasks", desc: "Only hiring tasks owned by your function and inside your authorized warehouse scope are shown.",
    back: "Home", refresh: "Refresh", includeDone: "Show completed", empty: "You have no pending onboarding tasks.",
    due: "Due", owner: "Owner", dependencies: "Dependencies", required: "Required", optional: "Optional", overdue: "Overdue", today: "Today", candidate: "Candidate", warehouse: "Warehouse",
    note: "Action note", notePlaceholder: "Completion evidence or blocker explanation…", start: "Start", blocked: "Blocked", complete: "Complete", saving: "Saving…",
    done: "Task updated.", blockedNeedsNote: "Explain why the task is blocked.", governance: "Required tasks cannot be waived here; waiver requires central onboarding-management authority.",
  },
  de: {
    eyebrow: "Candidate → Day One", title: "Meine Onboarding-Aufgaben", desc: "Es werden nur Aufgaben Ihrer Funktion innerhalb Ihres berechtigten Standortbereichs angezeigt.",
    back: "Start", refresh: "Aktualisieren", includeDone: "Erledigte anzeigen", empty: "Keine offenen Onboarding-Aufgaben.",
    due: "Fällig", owner: "Verantwortlich", dependencies: "Abhängigkeiten", required: "Pflicht", optional: "Optional", overdue: "Überfällig", today: "Heute", candidate: "Kandidat", warehouse: "Standort",
    note: "Notiz", notePlaceholder: "Abschlussnachweis oder Blocker…", start: "Starten", blocked: "Blockiert", complete: "Abschließen", saving: "Speichern…",
    done: "Aufgabe aktualisiert.", blockedNeedsNote: "Bitte Blockierungsgrund angeben.", governance: "Pflichtaufgaben können hier nicht erlassen werden; dafür ist zentrale Onboarding-Berechtigung nötig.",
  },
  ar: {
    eyebrow: "Candidate → Day One", title: "مهام التهيئة الخاصة بي", desc: "تظهر فقط المهام التابعة لفريقك وضمن نطاق المواقع المصرح لك بها.",
    back: "الرئيسية", refresh: "تحديث", includeDone: "إظهار المكتمل", empty: "لا توجد مهام تهيئة معلقة.",
    due: "الاستحقاق", owner: "المسؤول", dependencies: "الاعتماديات", required: "إلزامي", optional: "اختياري", overdue: "متأخر", today: "اليوم", candidate: "المرشح", warehouse: "الموقع",
    note: "ملاحظة", notePlaceholder: "دليل الإنجاز أو سبب التعطيل…", start: "بدء", blocked: "متعطل", complete: "إكمال", saving: "جارٍ الحفظ…",
    done: "تم تحديث المهمة.", blockedNeedsNote: "أدخل سبب التعطيل.", governance: "لا يمكن تجاوز المهام الإلزامية من هذه الشاشة؛ يتطلب ذلك صلاحية إدارة التهيئة المركزية.",
  },
};

function dueState(value) {
  if (!value) return "normal";
  const due = new Date(value);
  const now = new Date();
  const sameDay = due.toDateString() === now.toDateString();
  if (due.getTime() < now.getTime()) return "overdue";
  if (sameDay) return "today";
  return "normal";
}

function statusTone(status) {
  if (["COMPLETED", "WAIVED"].includes(status)) return "success";
  if (status === "BLOCKED") return "danger";
  if (status === "IN_PROGRESS") return "info";
  return "warning";
}

export default function RecruitmentOnboardingTasks() {
  const navigate = useNavigate();
  const { locale, formatDate } = usePlatformPreferences();
  const c = COPY[locale] || COPY.en;
  const [tasks, setTasks] = useState([]);
  const [includeDone, setIncludeDone] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notes, setNotes] = useState({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setLoading(true); setError("");
    try { setTasks(await loadMyRecruitmentOnboardingTasks(includeDone)); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [includeDone]);

  async function update(task, status) {
    const note = String(notes[task.taskId] || "").trim();
    if (status === "BLOCKED" && !note) { setError(c.blockedNeedsNote); return; }
    setBusy(task.taskId); setError(""); setNotice("");
    try {
      await updateRecruitmentOnboardingTask(task.taskId, status, note);
      setNotes((current) => ({ ...current, [task.taskId]: "" }));
      setNotice(c.done);
      await load();
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  const counts = useMemo(() => ({
    pending: tasks.filter((task) => !["COMPLETED", "WAIVED"].includes(task.status)).length,
    blocked: tasks.filter((task) => task.status === "BLOCKED").length,
    overdue: tasks.filter((task) => dueState(task.dueAt) === "overdue" && !["COMPLETED", "WAIVED"].includes(task.status)).length,
  }), [tasks]);

  return <main className="onb-page">
    <section className="onb-shell">
      <header className="onb-topbar">
        <button type="button" onClick={() => navigate("/")}><ArrowLeft size={17}/>{c.back}</button>
        <button type="button" onClick={load} disabled={loading}><RefreshCw size={16}/>{c.refresh}</button>
      </header>
      <section className="onb-hero">
        <div><span><UserRoundCheck size={16}/>{c.eyebrow}</span><h1>{c.title}</h1><p>{c.desc}</p></div>
        <div className="onb-metrics"><article><strong>{counts.pending}</strong><span>Open</span></article><article><strong>{counts.blocked}</strong><span>Blocked</span></article><article><strong>{counts.overdue}</strong><span>Overdue</span></article></div>
      </section>
      <div className="onb-governance"><ShieldCheck size={17}/><span>{c.governance}</span></div>
      {error ? <div className="onb-alert error" role="alert"><CircleAlert size={17}/>{error}</div> : null}
      {notice ? <div className="onb-alert success" role="status"><CheckCircle2 size={17}/>{notice}</div> : null}
      <div className="onb-filter"><label><input type="checkbox" checked={includeDone} onChange={(e) => setIncludeDone(e.target.checked)}/>{c.includeDone}</label></div>
      {loading ? <div className="onb-empty" role="status">Loading…</div> : tasks.length ? <section className="onb-list">
        {tasks.map((task) => {
          const due = dueState(task.dueAt); const terminal = ["COMPLETED", "WAIVED"].includes(task.status);
          return <article key={task.taskId} className={`onb-card ${due === "overdue" && !terminal ? "is-overdue" : ""}`}>
            <header><div><span className={`onb-status ${statusTone(task.status)}`}>{task.status.replaceAll("_", " ")}</span><h2>{task.title}</h2></div><span className="onb-owner">{c.owner}: <strong>{task.ownerRole}</strong></span></header>
            <div className="onb-context"><span><strong>{c.candidate}</strong>{task.candidateName || task.candidateId}</span><span><strong>{c.warehouse}</strong>{task.warehouseName || task.warehouseId}</span>{task.positionLabel ? <span><strong>Role</strong>{task.positionLabel}</span> : null}</div>
            <div className="onb-meta"><span className={due}><Clock3 size={15}/>{c.due}: {task.dueAt ? formatDate(new Date(task.dueAt), { dateStyle: "medium", timeStyle: "short" }) : "—"}{due === "overdue" ? ` · ${c.overdue}` : due === "today" ? ` · ${c.today}` : ""}</span><span>{task.required ? c.required : c.optional}</span>{task.dependencies?.length ? <span>{c.dependencies}: {task.dependencies.join(", ")}</span> : null}</div>
            {!terminal ? <><textarea value={notes[task.taskId] || ""} onChange={(e) => setNotes((current) => ({ ...current, [task.taskId]: e.target.value }))} placeholder={c.notePlaceholder} aria-label={c.note}/><div className="onb-actions"><button type="button" onClick={() => update(task, "IN_PROGRESS")} disabled={busy === task.taskId || task.status === "IN_PROGRESS"}>{c.start}</button><button type="button" className="blocked" onClick={() => update(task, "BLOCKED")} disabled={busy === task.taskId}>{c.blocked}</button><button type="button" className="complete" onClick={() => update(task, "COMPLETED")} disabled={busy === task.taskId}>{busy === task.taskId ? c.saving : c.complete}</button></div></> : null}
          </article>;
        })}
      </section> : <div className="onb-empty"><CheckCircle2 size={26}/><strong>{c.empty}</strong></div>}
    </section>
  </main>;
}
