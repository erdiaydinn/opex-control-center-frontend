import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Archive,
  ArrowLeft,
  Bell,
  CalendarDays,
  CalendarCheck,
  CheckCircle2,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Coffee,
  FileClock,
  Fingerprint,
  Home,
  Languages,
  MapPin,
  Megaphone,
  MessageSquareWarning,
  ShieldCheck,
  Smartphone,
  Moon,
  Sun,
  Send,
  Trash2,
  UserRound,
} from "lucide-react";

import { formatMinutes, loadWorkforceState, pickerShifts } from "./workforceData.js";
import { useWorkforceUi } from "./WorkforceUiContext.jsx";
import { useAuth } from "../../auth/AuthContext.jsx";
import { dismissAnnouncementRemote, loadMobileWorkforce, markNotificationRead, postAttendance, postBreak, postCorrection, postLeave, removeAllNotifications, removeNotification, requestNativeAttendanceProof, resolveLeave, resolveManagerTask } from "./workforceApi.js";
import { WorkforceExperienceCenter } from "./WorkforceExperienceCenter.jsx";
import "./workforce.css";

const DEFAULT_FEATURES = {
  breaks: true, leaveRequests: true, appeals: true, announcements: true,
  notifications: true, archive: true, managerTasks: true, qrCheckIn: false,
  liveBreakActivity: true,
  employeeExperience: true,
};
const LOCAL_PILOT_MODE = String(import.meta.env.VITE_LOCAL_PILOT_MODE || "false").toLowerCase() === "true";

function elapsedClock(startedAt, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return [hours, minutes, remainder].map((value) => String(value).padStart(2, "0")).join(":");
}

function BreakTimer({ startedAt, compact = false }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return <div className={`wfx-break-timer ${compact ? "compact" : ""}`}><span className="pulse" /><div><small>Moladasın</small><strong>{elapsedClock(startedAt, now)}</strong></div></div>;
}

async function syncBreakLiveActivity(action, payload) {
  try {
    window.webkit?.messageHandlers?.opexLiveActivity?.postMessage({ action, ...payload });
    if (!("serviceWorker" in navigator) || !("Notification" in window)) return;
    let permission = Notification.permission;
    if (action === "start" && permission === "default") permission = await Notification.requestPermission();
    if (permission !== "granted") return;
    const registration = await navigator.serviceWorker.ready;
    if (action === "start") await registration.showNotification("Moladasın", { body: `${payload.warehouse} · Mola kronometresi uygulamada çalışıyor.`, tag: "opex-active-break", renotify: true, requireInteraction: true, data: { url: "/workforce/app", shiftId: payload.shiftId } });
    else await registration.getNotifications({ tag: "opex-active-break" }).then((items) => items.forEach((item) => item.close()));
  } catch { /* native/PWA live activity is best effort */ }
}

function archiveYears(shifts) {
  return [
    { year: 2026, months: [{ month: "Temmuz", shifts }, { month: "Haziran", shifts: [] }] },
    { year: 2025, months: [] },
    { year: 2024, months: [] },
  ];
}

function datesBetween(startDate, endDate) {
  const rows = [];
  const start = new Date(`${startDate}T12:00:00`);
  const end = new Date(`${endDate || startDate}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return rows;
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) rows.push(cursor.toISOString().slice(0, 10));
  return rows;
}

function ShiftCard({ shift, onClick }) {
  return (
    <button type="button" className={`wfx-shift-card tone-${shift.tone}`} onClick={onClick}>
      <div className="date"><strong>{shift.shortDate}</strong><span>{shift.month}</span><small>{shift.day}</small></div>
      <div className="info"><strong>{shift.warehouse}</strong><span className={`wfx-status ${shift.tone}`}>{shift.status}</span><small>{shift.planned} · {shift.role}</small></div>
      <ChevronRight size={22} />
    </button>
  );
}

function ShiftDetail({ shift, onBack, onSubmitAppeal, existingAppeal, breakState, onBreakAction, onEndShift, features }) {
  const actionState = breakState?.status || (shift.status === "Vardiyada" ? "active" : "closed");
  const [message, setMessage] = useState("");
  const [appealOpen, setAppealOpen] = useState(false);
  const [appeal, setAppeal] = useState({ type: "Giriş / çıkış düzeltmesi", requestedCheckIn: shift.checkIn === "—" ? "" : shift.checkIn, requestedCheckOut: shift.checkOut === "—" ? "" : shift.checkOut, reason: "" });

  function performAction() {
    if (actionState === "active") {
      onBreakAction("start");
      setMessage("Mola başlangıcı kaydedildi.");
    } else if (actionState === "break") {
      onBreakAction("finish");
      setMessage("Mola bitişi kaydedildi.");
    }
  }

  return (
    <section className="wfx-mobile-screen detail">
      <header className="wfx-mobile-header">
        <button type="button" onClick={onBack}><ArrowLeft size={22} /></button>
        <strong>Vardiya Detayı</strong>
        <button type="button"><Bell size={21} /></button>
      </header>

      <div className={`wfx-detail-hero tone-${shift.tone}`}>
        <div className="wfx-detail-status"><CalendarDays size={21} /><span>{shift.status}</span></div>
        <h1>{shift.date}</h1>
        <p>Planlanan vardiya · {shift.planned}</p>
      </div>

      <div className="wfx-detail-stack">
        <article>
          <div className="icon"><MapPin size={21} /></div>
          <div><small>Görev Yeri</small><strong>{shift.warehouse}</strong><span>{shift.role}</span></div>
          <span className="wfx-status success">Atanmış depo</span>
        </article>
        <article>
          <div className="icon"><Clock3 size={21} /></div>
          <div><small>Giriş, mola ve çıkış</small><strong>{shift.checkIn} → {shift.checkOut}</strong><span>Mola: {shift.breakText}</span></div>
          <span className={`wfx-status ${shift.tone}`}>{shift.actual}</span>
        </article>
        <article>
          <div className="icon"><FileClock size={21} /></div>
          <div><small>Puantaj Sonucu</small><strong>Net: {shift.net}</strong><span>Brüt: {shift.gross}</span></div>
          <span className={`wfx-status ${shift.tone}`}>{shift.difference}</span>
        </article>
        <article>
          <div className="icon"><ShieldCheck size={21} /></div>
          <div><small>Doğrulama</small><strong>{shift.location}</strong><span>{shift.device}</span></div>
          <CheckCircle2 size={21} className="green" />
        </article>
      </div>

      {message ? <div className="wfx-mobile-message"><CheckCircle2 size={17} />{message}</div> : null}
      {actionState === "break" && breakState?.startedAt ? <BreakTimer startedAt={breakState.startedAt} /> : null}

      <div className="wfx-mobile-detail-actions">
        {actionState !== "closed" ? (
          <>
            {features.breaks && actionState === "break" ? <button key="finish-break" type="button" className="resume" onClick={performAction}><Coffee size={18} />Molayı Bitir</button> : null}
            {features.breaks && actionState !== "break" ? <button key="start-break" type="button" className="break" onClick={performAction}><Coffee size={18} />Molaya Çık</button> : null}
            <button type="button" className={`checkout ${features.breaks ? "" : "full"}`} onClick={() => { onEndShift(); setMessage("Vardiya çıkış talebi oluşturuldu."); }}>Vardiyayı Bitir</button>
          </>
        ) : features.appeals ? (
          <button type="button" className="appeal" onClick={() => setAppealOpen((current) => !current)}><MessageSquareWarning size={18} /> {existingAppeal ? `Talep: ${existingAppeal.status}` : "İtiraz / Düzeltme Talebi"}</button>
        ) : null}
      </div>
      {appealOpen ? <form className="wfx-mobile-appeal" onSubmit={(event) => { event.preventDefault(); if (!appeal.reason.trim()) { setMessage("Talep gerekçesi boş bırakılamaz."); return; } onSubmitAppeal(appeal); setAppealOpen(false); setMessage("Talebin yöneticine gönderildi. Durumu Görevler alanından izleyebilirsin."); }}>
        <strong>İtiraz / düzeltme talebi oluştur</strong>
        <label>Talep türü<select value={appeal.type} onChange={(event) => setAppeal({ ...appeal, type: event.target.value })}><option>Giriş / çıkış düzeltmesi</option><option>Konum doğrulama itirazı</option><option>Mola düzeltmesi</option><option>Fazla mesai itirazı</option><option>Diğer</option></select></label>
        <div><label>Talep edilen giriş<input type="time" value={appeal.requestedCheckIn} onChange={(event) => setAppeal({ ...appeal, requestedCheckIn: event.target.value })} /></label><label>Talep edilen çıkış<input type="time" value={appeal.requestedCheckOut} onChange={(event) => setAppeal({ ...appeal, requestedCheckOut: event.target.value })} /></label></div>
        <label>Açıklama<textarea value={appeal.reason} onChange={(event) => setAppeal({ ...appeal, reason: event.target.value })} placeholder="Ne düzeltilmeli? Yöneticinin karar verebilmesi için açıklayın." /></label>
        <button type="submit"><MessageSquareWarning size={17} />Yöneticiye gönder</button>
      </form> : null}
    </section>
  );
}

function ArchiveView({ shifts, onBack, onOpenShift }) {
  const [openYear, setOpenYear] = useState(2026);
  const [openMonth, setOpenMonth] = useState("Temmuz");
  const years = archiveYears(shifts);
  return (
    <section className="wfx-mobile-screen archive">
      <header className="wfx-mobile-header"><button type="button" onClick={onBack}><ArrowLeft size={22} /></button><strong>Arşiv</strong><span /></header>
      <div className="wfx-archive-summary"><small>2026 özeti</small><div><span><strong>{formatMinutes(10170)}</strong>Çalışma</span><span><strong>{formatMinutes(390)}</strong>Eksik</span><span><strong>{formatMinutes(240)}</strong>Fazla</span></div></div>
      <div className="wfx-archive-list">
        {years.map((item) => (
          <article key={item.year}>
            <button type="button" onClick={() => setOpenYear(openYear === item.year ? null : item.year)}><strong>{item.year}</strong><ChevronDown className={openYear === item.year ? "rotate" : ""} /></button>
            {openYear === item.year ? <div className="months">
              {item.months.length ? item.months.map((month) => <div key={month.month}><button type="button" onClick={() => setOpenMonth(openMonth === month.month ? null : month.month)}><span>{month.month}</span><small>{month.shifts.length} vardiya</small><ChevronDown className={openMonth === month.month ? "rotate" : ""} /></button>{openMonth === month.month ? <div className="month-shifts">{month.shifts.map((shift) => <ShiftCard key={shift.id} shift={shift} onClick={() => onOpenShift(shift)} />)}</div> : null}</div>) : <p>Bu yıla ait kayıt bulunmuyor.</p>}
            </div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function MobileNav({ view, setView, notificationCount, taskCount, features }) {
  return <nav className="wfx-mobile-nav">
    <button type="button" className={view === "home" ? "active" : ""} onClick={() => setView("home")}><Home size={21} /><span>Ana Sayfa</span></button>
    <button type="button" className={view === "shifts" ? "active" : ""} onClick={() => setView("shifts")}><CalendarDays size={21} /><span>Vardiyalarım</span></button>
    {features.notifications ? <button type="button" className={view === "notifications" ? "active" : ""} onClick={() => setView("notifications")}><Bell size={21} /><span>Bildirimler</span>{notificationCount ? <i>{notificationCount}</i> : null}</button> : null}
    {(features.managerTasks || features.leaveRequests || features.appeals) ? <button type="button" className={view === "tasks" ? "active" : ""} onClick={() => setView("tasks")}><ClipboardCheck size={21} /><span>Görevler</span>{taskCount ? <i>{taskCount}</i> : null}</button> : null}
    <button type="button" className={view === "profile" ? "active" : ""} onClick={() => setView("profile")}><UserRound size={21} /><span>Profil</span></button>
  </nav>;
}

function AttendanceTrustRail({ phase = "idle", active = false }) {
  const steps = [
    { id: "device", icon: Smartphone, label: "Kayıtlı cihaz" },
    { id: "presence", icon: Fingerprint, label: "Face ID / cihaz kilidi" },
    { id: "location", icon: MapPin, label: "Depo konumu" },
  ];
  const working = ["authenticating", "verifying"].includes(phase);
  return <div className={`wfx-attendance-trust ${working ? "is-working" : ""}`}>{steps.map((step, index) => { const Icon = step.icon; const done = active || phase === "success" || (phase === "verifying" && index < 2); return <span key={step.id} className={done ? "done" : working && index === 0 ? "current" : ""}><i>{done ? <CheckCircle2 size={14} /> : <Icon size={14} />}</i>{step.label}</span>; })}</div>;
}

export default function WorkforcePickerApp() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const rootRef = useRef(null);
  const { theme, setTheme, locale, setLocale, dir, localeCode, useDomLocalization } = useWorkforceUi();
  useDomLocalization(rootRef, locale);
  const [workforceState, setWorkforceState] = useState(() => loadWorkforceState());
  const features = { ...DEFAULT_FEATURES, ...(workforceState.featureFlags || {}) };
  const currentPersonId =
    user?.employeeId ||
    (import.meta.env.DEV
      ? window.localStorage.getItem(
          "opex_picker_person_id"
        ) || "100184"
      : "");
  const todayKey = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
  const currentPerson = workforceState.people.find((person) => String(person.id) === String(currentPersonId)) || workforceState.people[0];
  const notifications = (workforceState.notifications || []).filter((item) => String(item.personId) === String(currentPersonId));
  const correctionRequests = workforceState.correctionRequests || [];
  const ownAppeals = correctionRequests.filter((item) => String(item.personId) === String(currentPersonId));
  const managerTasks = (workforceState.rosterTasks || []).filter((item) => String(item.assigneeId) === String(currentPersonId));
  const isCurrentManager = /manager|müdür|captain/i.test(currentPerson?.role || "");
  const managerAppeals = isCurrentManager ? correctionRequests.filter((item) => item.warehouse === currentPerson?.warehouse && item.status?.includes("inceleme")) : [];
  const leaveRequests = workforceState.leaveRequests || [];
  const ownLeaveRequests = leaveRequests.filter((item) => String(item.personId) === String(currentPersonId));
  const managerLeaveRequests = isCurrentManager ? leaveRequests.filter((item) => item.warehouse === currentPerson?.warehouse && item.status === "Yönetici incelemesinde") : [];
  const announcementReceipts = workforceState.announcementReceipts || {};
  const dismissedAnnouncements = announcementReceipts[currentPersonId] || {};
  const announcements = (workforceState.announcements || []).filter((item) => !dismissedAnnouncements[item.id]?.dismissed && item.active !== false && (!item.targetType || item.targetType === "all" || (item.targetType === "warehouse" && item.targetValue === currentPerson?.warehouse) || (item.targetType === "person" && String(item.targetValue) === String(currentPersonId))));
  const assignedShift = useMemo(
    () => workforceState.shifts.find((shift) => String(shift.personId) === String(currentPersonId) && shift.date === todayKey && shift.status !== "İptal")
      || (LOCAL_PILOT_MODE ? workforceState.shifts.find((shift) => String(shift.personId) === String(currentPersonId) && shift.status !== "İptal") : null),
    [workforceState, currentPersonId, todayKey],
  );
  const ownShifts = useMemo(() => {
    const fromPlan = workforceState.shifts.filter((shift) => String(shift.personId) === String(currentPersonId)).map((shift) => {
      const attendance = workforceState.attendance.find((item) => item.shiftId === shift.id);
      const date = new Date(`${shift.date}T12:00:00`);
      const status = attendance?.status || (shift.status === "Atandı" ? "Check-in bekliyor" : shift.status);
      const tone = status.includes("Tamam") ? "done" : status.includes("Gelmedi") ? "missed" : status.includes("Fazla") ? "pending" : "live";
      return {
        id: shift.id,
        date: date.toLocaleDateString(localeCode, { day: "2-digit", month: "long", year: "numeric", weekday: "long" }),
        shortDate: String(date.getDate()).padStart(2, "0"),
        month: date.toLocaleDateString(localeCode, { month: "long" }),
        day: date.toLocaleDateString(localeCode, { weekday: "short" }),
        warehouse: shift.warehouse,
        role: shift.role,
        planned: `${shift.start}–${shift.end}`,
        actual: attendance ? `${attendance.checkIn}–${attendance.checkOut}` : "Henüz kayıt yok",
        checkIn: attendance?.checkIn || "—",
        checkOut: attendance?.checkOut || "—",
        breakText: attendance?.breakMinutes ? `${attendance.breakMinutes} dakika` : "—",
        gross: attendance?.netMinutes ? `${attendance.netMinutes} dakika` : "0 dakika",
        net: attendance?.netMinutes ? `${attendance.netMinutes} dakika` : "0 dakika",
        difference: attendance?.approval || "Vardiya atandı",
        status,
        tone,
        location: attendance?.location || "Check-in sırasında doğrulanacak",
        device: attendance?.device || "Kayıtlı cihaz gerekli",
      };
    });
    const ids = new Set(fromPlan.map((shift) => shift.id));
    return [...fromPlan, ...pickerShifts.filter((shift) => !ids.has(shift.id))];
  }, [workforceState, localeCode, currentPersonId]);
  const [view, setView] = useState("home");
  const [selectedShift, setSelectedShift] = useState(pickerShifts[0]);
  const [filter, setFilter] = useState("Tümü");
  const [editingTask, setEditingTask] = useState(null);
  const [leaveFormOpen, setLeaveFormOpen] = useState(false);
  const [leaveForm, setLeaveForm] = useState({ typeId: "annual", startDate: "2026-07-15", endDate: "2026-07-15", note: "" });
  const [leaveMessage, setLeaveMessage] = useState("");
  const [checkInState, setCheckInState] = useState(() => workforceState.attendance.some((row) => String(row.personId) === String(currentPersonId) && row.status === "Vardiyada") ? "active" : "idle");
  const [attendanceFlow, setAttendanceFlow] = useState({ phase: "idle", message: "" });
  const activeBreakEntry = Object.entries(workforceState.shiftBreakStates || {}).find(([shiftId, item]) => item.status === "break" && ownShifts.some((shift) => shift.id === shiftId));
  const activeBreak = activeBreakEntry ? { shift: ownShifts.find((item) => item.id === activeBreakEntry[0]), state: activeBreakEntry[1] } : null;

  async function refreshBackend() {
    if (!currentPersonId) { setLeaveMessage("SSO tokenında employee_id alanı bulunamadı."); return; }
    try {
      const data = await loadMobileWorkforce(currentPersonId);
      const breakStates = Object.fromEntries((data.breaks || []).reduce((entries, item) => {
        const current = entries.find(([id]) => id === item.shiftId);
        const state = item.finishedAt ? { status: "active", lastEndedAt: item.finishedAt } : { status: "break", startedAt: item.startedAt };
        if (current) current[1] = state; else entries.push([item.shiftId, state]);
        return entries;
      }, []));
      const receipts = Object.fromEntries((data.announcementReceipts || []).map((item) => [item.announcementId, { dismissed: true, read: true, readAt: item.dismissedAt }]));
      setWorkforceState((current) => ({ ...current, shifts: data.shifts || [], attendance: data.attendance || [], notifications: data.notifications || [], leaveRequests: data.leaveRequests || [], correctionRequests: data.correctionRequests || [], rosterTasks: data.managerTasks || [], announcements: data.announcements || [], announcementReceipts: { ...(current.announcementReceipts || {}), [currentPersonId]: receipts }, featureFlags: data.features || current.featureFlags, shiftBreakStates: breakStates }));
      setCheckInState((data.attendance || []).some((row) => row.status === "Vardiyada") ? "active" : "idle");
    } catch (error) { setLeaveMessage(error.message || "Workforce verileri yüklenemedi."); }
  }

  useEffect(() => { refreshBackend(); }, [currentPersonId]);

  useEffect(() => {
    if (!activeBreak?.state?.startedAt) return undefined;
    const updateTitle = () => { document.title = `${elapsedClock(activeBreak.state.startedAt)} · Moladasın`; };
    updateTitle();
    const timer = window.setInterval(updateTitle, 1000);
    return () => { window.clearInterval(timer); document.title = "OPEX Control Center"; };
  }, [activeBreak?.state?.startedAt]);

  const filteredShifts = useMemo(() => {
    if (filter === "Tümü") return ownShifts;
    return ownShifts.filter((shift) => shift.status.includes(filter));
  }, [filter, ownShifts]);
  const completedShiftCount = ownShifts.filter((shift) => shift.status.includes("Tamam")).length;
  const openRequestCount = [...ownLeaveRequests, ...ownAppeals].filter((item) => item.status?.includes("inceleme")).length;
  const unreadNotificationCount = notifications.filter((item) => !item.read).length;
  const homeShiftState = activeBreak ? "Molada" : checkInState === "active" ? "Vardiyada" : assignedShift ? "Check-in bekliyor" : "Plan bekleniyor";

  function openShift(shift) {
    setSelectedShift(shift);
    setView("detail");
  }

  async function markAllNotificationsRead() {
    await Promise.all(notifications.filter((item) => !item.read).map((item) => markNotificationRead(item.id, currentPersonId)));
    await refreshBackend();
  }

  async function deleteNotification(id) {
    await removeNotification(id, currentPersonId); await refreshBackend();
  }

  async function clearNotifications() {
    await removeAllNotifications(currentPersonId); await refreshBackend();
  }

  async function dismissAnnouncement(id) {
    try { await dismissAnnouncementRemote(id, currentPersonId); await refreshBackend(); }
    catch (error) { setLeaveMessage(error.message); }
  }

  async function changeBreak(shift, action) {
    try { await postBreak(shift.id, currentPersonId, action); await refreshBackend(); }
    catch (error) { setLeaveMessage(error.message); return; }
    const at = new Date().toISOString();
    const current = (workforceState.shiftBreakStates || {})[shift.id] || { status: "active", history: [] };
    const nextBreak = action === "start"
      ? { ...current, status: "break", startedAt: at }
      : { status: "active", history: [...(current.history || []), { startedAt: current.startedAt, endedAt: at }], lastEndedAt: at };
    if (features.liveBreakActivity) syncBreakLiveActivity(action, { shiftId: shift.id, warehouse: shift.warehouse, startedAt: nextBreak.startedAt, personId: currentPersonId });
  }

  async function endShift(shift) {
    try {
      setAttendanceFlow({ phase: "authenticating", message: "Cihaz üzerinde kimliğini doğrula…" });
      const proof = await requestNativeAttendanceProof("check-out", shift.id, currentPersonId);
      setAttendanceFlow({ phase: "verifying", message: "Cihaz imzası ve depo konumu doğrulanıyor…" });
      await postAttendance(shift.id, "check-out", { ...proof, person_id: currentPersonId });
      if (features.liveBreakActivity) syncBreakLiveActivity("finish", { shiftId: shift.id, warehouse: shift.warehouse, personId: currentPersonId });
      await refreshBackend();
      setAttendanceFlow({ phase: "success", message: "Çıkışın güvenle kaydedildi." });
    } catch (error) { setAttendanceFlow({ phase: "error", message: error.message }); setLeaveMessage(error.message); }
  }

  async function startShift(shift) {
    try {
      setAttendanceFlow({ phase: "authenticating", message: "Face ID veya cihaz kilidi bekleniyor…" });
      const proof = await requestNativeAttendanceProof("check-in", shift.id, currentPersonId);
      setAttendanceFlow({ phase: "verifying", message: "Cihaz imzası ve depo konumu doğrulanıyor…" });
      await postAttendance(shift.id, "check-in", { ...proof, person_id: currentPersonId });
      await refreshBackend();
      setAttendanceFlow({ phase: "success", message: "Girişin güvenle kaydedildi. İyi vardiyalar!" });
    } catch (error) { setAttendanceFlow({ phase: "error", message: error.message }); setLeaveMessage(error.message); }
  }

  async function submitLeaveRequest(event) {
    event.preventDefault();
    const dates = datesBetween(leaveForm.startDate, leaveForm.endDate);
    if (!dates.length) { setLeaveMessage("Tarih aralığı geçersiz. Bitiş tarihi başlangıçtan önce olamaz."); return; }
    if (!leaveForm.note.trim()) { setLeaveMessage("Açıklama boş bırakılamaz."); return; }
    if (leaveRequests.some((item) => String(item.personId) === String(currentPersonId) && item.startDate === leaveForm.startDate && item.endDate === leaveForm.endDate && item.status === "Yönetici incelemesinde")) { setLeaveMessage("Bu tarih aralığı için zaten açık bir izin talebin var."); return; }
    const type = leaveForm.typeId === "weekly_off" ? "Haftalık izin" : "Yıllık izin";
    try { await postLeave({ person_id: currentPersonId, person_name: currentPerson?.name, warehouse: currentPerson?.warehouse, leave_type: leaveForm.typeId, start_date: leaveForm.startDate, end_date: leaveForm.endDate, note: leaveForm.note }); await refreshBackend(); }
    catch (error) { setLeaveMessage(error.message); return; }
    setLeaveFormOpen(false);
    setLeaveMessage("İzin talebin yöneticine gönderildi. Durumu Görevler ekranından izleyebilirsin.");
    setLeaveForm({ typeId: "annual", startDate: leaveForm.endDate, endDate: leaveForm.endDate, note: "" });
  }

  async function submitAppeal(shift, values) {
    try { await postCorrection({ person_id: currentPersonId, shift_id: shift.id, request_type: values.type, requested_check_in: values.requestedCheckIn || null, requested_check_out: values.requestedCheckOut || null, reason: values.reason }); await refreshBackend(); }
    catch (error) { setLeaveMessage(error.message); }
  }

  async function resolveMobileTask() {
    if (!editingTask?.managerNote?.trim()) return;
    const decision = (editingTask.decision || "Onaylandı") === "Onaylandı" ? "APPROVED" : "REJECTED";
    try {
      if (editingTask.kind === "leave") await resolveLeave(editingTask.id, decision, editingTask.managerNote);
      else await resolveManagerTask(editingTask.id, { decision, manager_note: editingTask.managerNote, requested_check_in: editingTask.requestedCheckIn || null, requested_check_out: editingTask.requestedCheckOut || null, target_minutes: editingTask.targetMinutes ? Number(editingTask.targetMinutes) : null });
      setEditingTask(null); await refreshBackend();
    } catch (error) { setLeaveMessage(error.message); }
  }

  function shell(content) {
    return <main ref={rootRef} dir={dir} className={`wfx-picker-page wfx-theme-${theme}`}><div className="wfx-picker-preferences"><label><Languages size={15} /><select aria-label="Dil" value={locale} onChange={(event) => setLocale(event.target.value)}><option value="tr">TR</option><option value="en">EN</option><option value="de">DE</option><option value="ar">AR</option></select></label><button type="button" title={theme === "dark" ? "Açık tema" : "Koyu tema"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button></div>{content}</main>;
  }

  if (view === "detail") return shell(<ShiftDetail shift={selectedShift} features={features} breakState={(workforceState.shiftBreakStates || {})[selectedShift.id]} onBreakAction={(action) => changeBreak(selectedShift, action)} onEndShift={() => endShift(selectedShift)} onBack={() => setView("shifts")} existingAppeal={ownAppeals.find((item) => item.shiftId === selectedShift.id && item.status !== "Reddedildi")} onSubmitAppeal={(values) => submitAppeal(selectedShift, values)} />);
  if (view === "archive") return shell(<ArchiveView shifts={ownShifts} onBack={() => setView("shifts")} onOpenShift={openShift} />);
  if (view === "experience") return shell(<WorkforceExperienceCenter onBack={() => setView("home")} />);

  if (["home", "notifications", "tasks", "profile"].includes(view)) return shell(<section className="wfx-mobile-screen wfx-mobile-info-screen">
    <header className={`wfx-mobile-header ${view === "home" ? "wfx-home-header" : ""}`}>{view === "home" ? <><div className="wfx-home-appmark">W</div><div className="wfx-home-app-title"><small>OPEX Control Center</small><strong>Workforce</strong></div><span /></> : <><button type="button" onClick={() => navigate("/workforce")}><ArrowLeft size={22} /></button><strong>{view === "notifications" ? "Bildirimler" : view === "tasks" ? "Yönetici Görevleri" : "Profil"}</strong><span /></>}</header>
    {view === "home" ? <div className="wfx-mobile-info-content wfx-home-dashboard">
      <div className="wfx-home-greeting"><div><small>{new Date().toLocaleDateString(localeCode, { timeZone: "Europe/Istanbul", day: "2-digit", month: "long", year: "numeric", weekday: "long" })}</small><h1>Merhaba, {currentPerson?.name?.split(" ")[0]}</h1><p>Bugünkü operasyon durumun hazır.</p></div><div className="avatar">{currentPerson?.name?.split(" ").map((item) => item[0]).slice(0, 2).join("")}</div></div>
      <section className={`wfx-home-shift-hero ${activeBreak ? "on-break" : ""}`}>
        <div className="wfx-home-shift-top"><span><i />Bugünkü vardiya</span><b>{homeShiftState}</b></div>
        <div className="wfx-home-shift-location"><div><MapPin size={20} /></div><span><small>Görev yeri</small><strong>{assignedShift?.warehouse || currentPerson?.warehouse || "Atanmış vardiya yok"}</strong><p>{assignedShift ? `${assignedShift.role} · ${assignedShift.start}–${assignedShift.end}` : "Vardiya yayınlandığında burada görünecek."}</p></span></div>
        {activeBreak?.state?.startedAt ? <BreakTimer compact startedAt={activeBreak.state.startedAt} /> : <AttendanceTrustRail phase={attendanceFlow.phase} active={checkInState === "active"} />}
        {attendanceFlow.message ? <p className={`wfx-attendance-flow-message ${attendanceFlow.phase}`}>{attendanceFlow.message}</p> : null}
        <button type="button" disabled={!assignedShift && !ownShifts.length} onClick={() => activeBreak?.shift ? openShift(activeBreak.shift) : setView("shifts")}><span>{activeBreak ? "Molayı yönet" : checkInState === "active" ? "Vardiyayı yönet" : "Vardiyaya git"}</span><ChevronRight size={19} /></button>
      </section>
      <section className="wfx-home-kpis">
        <article><FileClock size={18} /><span><strong>{ownShifts.length}</strong><small>Bu ay vardiya</small></span></article>
        <article><CheckCircle2 size={18} /><span><strong>{completedShiftCount}</strong><small>Tamamlanan</small></span></article>
        <article><ClipboardCheck size={18} /><span><strong>{openRequestCount}</strong><small>Açık talep</small></span></article>
      </section>
      {features.announcements && announcements.length ? <section className="wfx-home-block"><div className="wfx-home-block-title"><span>Güncel duyurular</span><small>{announcements.length} yeni</small></div>{announcements.map((item) => <article className="wfx-mobile-announcement" key={item.id}><Megaphone size={22} /><div><small>Duyuru</small><strong>{item.title}</strong><p>{item.message}</p><button type="button" onClick={() => dismissAnnouncement(item.id)}><CheckCircle2 size={15} />Okudum, kapat</button></div></article>)}</section> : null}
      <section className="wfx-home-block"><div className="wfx-home-block-title"><span>Hızlı işlemler</span><small>Tek dokunuşla</small></div><div className="wfx-home-actions">
        {features.employeeExperience ? <button type="button" className="featured" onClick={() => setView("experience")}><div className="purple"><Fingerprint size={20} /></div><span><strong>Çalışan merkezi</strong><small>Belge · eğitim · anket · zimmet</small></span><ChevronRight size={17} /></button> : null}
        {features.archive ? <button type="button" onClick={() => setView("archive")}><div className="blue"><FileClock size={20} /></div><span><strong>Vardiya arşivi</strong><small>{ownShifts.length} kayıt</small></span><ChevronRight size={17} /></button> : null}
        {features.leaveRequests ? <button type="button" onClick={() => setLeaveFormOpen((open) => !open)}><div className="pink"><CalendarCheck size={20} /></div><span><strong>İzin talebi</strong><small>Haftalık veya yıllık</small></span><ChevronRight size={17} /></button> : null}
        {features.notifications ? <button type="button" onClick={() => setView("notifications")}><div className="amber"><Bell size={20} /></div><span><strong>Bildirimler</strong><small>{unreadNotificationCount ? `${unreadNotificationCount} okunmamış` : "Tümü okundu"}</small></span><ChevronRight size={17} /></button> : null}
        {(features.managerTasks || features.leaveRequests || features.appeals) ? <button type="button" onClick={() => setView("tasks")}><div className="green"><ClipboardCheck size={20} /></div><span><strong>Görevler ve talepler</strong><small>{openRequestCount ? `${openRequestCount} işlem bekliyor` : "Güncel durumu izle"}</small></span><ChevronRight size={17} /></button> : null}
      </div></section>
      {leaveMessage ? <div className={`wfx-mobile-form-message ${leaveMessage.startsWith("İzin talebin") ? "success" : "error"}`}><AlertCircle size={17} />{leaveMessage}</div> : null}
      {leaveFormOpen ? <form className="wfx-mobile-appeal wfx-mobile-leave-form" onSubmit={submitLeaveRequest}><strong>İzin talebi oluştur</strong><label>İzin türü<select value={leaveForm.typeId} onChange={(event) => { setLeaveMessage(""); setLeaveForm({ ...leaveForm, typeId: event.target.value }); }}><option value="weekly_off">Haftalık izin</option><option value="annual">Yıllık izin</option></select></label><div><label>Başlangıç<input type="date" value={leaveForm.startDate} onChange={(event) => { setLeaveMessage(""); setLeaveForm({ ...leaveForm, startDate: event.target.value, endDate: event.target.value > leaveForm.endDate ? event.target.value : leaveForm.endDate }); }} /></label><label>Bitiş<input type="date" min={leaveForm.startDate} value={leaveForm.endDate} onChange={(event) => { setLeaveMessage(""); setLeaveForm({ ...leaveForm, endDate: event.target.value }); }} /></label></div><label>Açıklama<textarea required value={leaveForm.note} onChange={(event) => { setLeaveMessage(""); setLeaveForm({ ...leaveForm, note: event.target.value }); }} placeholder="Yöneticinin değerlendirmesi için kısa bir açıklama…" /></label><button type="submit"><Send size={17} />Yöneticiye gönder</button></form> : null}
    </div> : null}
    {view === "notifications" ? <div className="wfx-mobile-info-content"><div className="wfx-mobile-section-title"><span>Vardiya ve sistem bildirimleri</span><strong>{notifications.length} kayıt</strong></div>{activeBreak?.state?.startedAt ? <article className="wfx-active-break-notification"><Coffee size={22} /><div><small>Aktif mola</small><strong>{activeBreak.shift?.warehouse}</strong><BreakTimer compact startedAt={activeBreak.state.startedAt} /></div><button type="button" onClick={() => openShift(activeBreak.shift)}>Molayı yönet</button></article> : null}{notifications.length ? <div className="wfx-mobile-notification-toolbar"><button type="button" onClick={markAllNotificationsRead}><CheckCheck size={16} />Tümünü okundu yap</button><button type="button" className="danger" onClick={clearNotifications}><Trash2 size={16} />Tümünü sil</button></div> : null}{notifications.length ? notifications.map((item) => <article className={`wfx-mobile-notification ${item.read ? "read" : "unread"}`} key={item.id} onClick={async () => { if (!item.read) { await markNotificationRead(item.id, currentPersonId); await refreshBackend(); } }}><div><Bell size={18} /></div><span><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.createdAt).toLocaleString(localeCode)}</small></span><button type="button" aria-label="Bildirimi sil" onClick={(event) => { event.stopPropagation(); deleteNotification(item.id); }}><Trash2 size={16} /></button></article>) : activeBreak ? null : <div className="wfx-mobile-empty"><Bell size={30} /><strong>Yeni bildirim yok</strong><p>Vardiya atandığında veya güncellendiğinde burada görünecek.</p></div>}</div> : null}
    {view === "tasks" ? <div className="wfx-mobile-info-content"><div className="wfx-mobile-section-title"><span>Atanan yönetici işleri ve taleplerim</span><strong>{managerTasks.length + managerAppeals.length + managerLeaveRequests.length + ownAppeals.length + ownLeaveRequests.length} kayıt</strong></div>{editingTask ? <form className="wfx-mobile-appeal" onSubmit={(event) => { event.preventDefault(); resolveMobileTask(); }}><strong>{editingTask.kind === "roster" ? "11 saat görevini düzelt" : editingTask.kind === "leave" ? "İzin talebini sonuçlandır" : "Picker talebini sonuçlandır"}</strong>{editingTask.kind === "roster" ? <label>Hesaba esas süre (dakika)<input type="number" value={editingTask.targetMinutes} onChange={(event) => setEditingTask({ ...editingTask, targetMinutes: event.target.value })} /></label> : <label>Karar<select value={editingTask.decision} onChange={(event) => setEditingTask({ ...editingTask, decision: event.target.value })}><option>Onaylandı</option><option>Reddedildi</option></select></label>}<label>Yönetici açıklaması<textarea value={editingTask.managerNote} onChange={(event) => setEditingTask({ ...editingTask, managerNote: event.target.value })} /></label><button type="submit"><CheckCircle2 size={17} />Kararı kaydet</button></form> : null}{features.managerTasks ? managerTasks.map((task) => <article className="wfx-mobile-task" key={task.id}><ClipboardCheck size={20} /><div><strong>{task.title}</strong><p>{task.warehouse} · {task.recordCount} kayıt</p><small>{task.status}</small>{!["Tamamlandı", "Düzeltildi"].includes(task.status) ? <button type="button" onClick={() => setEditingTask({ ...task, kind: "roster", targetMinutes: task.targetMinutes || 450, managerNote: task.managerNote || "" })}>Görevi düzelt</button> : null}</div></article>) : null}{features.appeals ? managerAppeals.map((task) => <article className="wfx-mobile-task" key={task.id}><MessageSquareWarning size={20} /><div><strong>{task.type}</strong><p>{task.personName} · {task.date}</p><small>{task.status}</small><button type="button" onClick={() => setEditingTask({ ...task, kind: "appeal", decision: "Onaylandı", managerNote: task.managerNote || "" })}>Talebi incele</button></div></article>) : null}{features.leaveRequests ? managerLeaveRequests.map((task) => <article className="wfx-mobile-task" key={task.id}><CalendarCheck size={20} /><div><strong>{task.typeName}</strong><p>{task.personName} · {task.startDate} – {task.endDate}</p><small>{task.status}</small><button type="button" onClick={() => setEditingTask({ ...task, kind: "leave", decision: "Onaylandı", managerNote: task.managerNote || "" })}>İzin talebini incele</button></div></article>) : null}{ownAppeals.map((task) => <article className="wfx-mobile-task" key={task.id}><MessageSquareWarning size={20} /><div><strong>{task.type}</strong><p>{task.warehouse} · {task.date}</p><small>{task.status}{task.managerNote ? ` · ${task.managerNote}` : ""}</small></div></article>)}{ownLeaveRequests.map((task) => <article className="wfx-mobile-task" key={task.id}><CalendarCheck size={20} /><div><strong>{task.typeName}</strong><p>{task.startDate} – {task.endDate}</p><small>{task.status}{task.managerNote ? ` · ${task.managerNote}` : ""}</small></div></article>)}{!managerTasks.length && !managerAppeals.length && !managerLeaveRequests.length && !ownAppeals.length && !ownLeaveRequests.length ? <div className="wfx-mobile-empty"><ClipboardCheck size={30} /><strong>Atanmış görev yok</strong><p>Yönetici görevleri, itirazlar ve izin talepleri burada görünür.</p></div> : null}</div> : null}
    {view === "profile" ? <div className="wfx-mobile-info-content"><div className="wfx-mobile-profile"><div className="avatar">{currentPerson?.name?.split(" ").map((item) => item[0]).slice(0, 2).join("")}</div><h2>{currentPerson?.name}</h2><p>{currentPerson?.id} · {currentPerson?.role}</p></div><article className="wfx-mobile-profile-row"><span>Asıl depo</span><strong>{currentPerson?.warehouse}</strong></article><article className="wfx-mobile-profile-row"><span>İşe giriş</span><strong>{currentPerson?.hireDate || "—"}</strong></article><article className="wfx-mobile-profile-row"><span>Cihaz doğrulama</span><strong>Kayıtlı cihaz</strong></article><div className="wfx-permission-info"><ShieldCheck size={17} />Kişisel ve hassas bilgiler yalnız yetkili roller tarafından görüntülenir.</div></div> : null}
    <MobileNav view={view} setView={setView} features={features} notificationCount={notifications.filter((item) => !item.read).length} taskCount={managerTasks.filter((item) => item.status === "Açık").length + managerAppeals.length + managerLeaveRequests.length + ownAppeals.filter((item) => item.status.includes("inceleme")).length + ownLeaveRequests.filter((item) => item.status.includes("inceleme")).length} />
  </section>);

  return shell(
      <section className="wfx-mobile-screen shifts">
        <header className="wfx-mobile-header"><button type="button" onClick={() => navigate("/workforce")}><ArrowLeft size={22} /></button><strong>Vardiyalarım</strong>{features.notifications ? <button type="button" onClick={() => setView("notifications")}><Bell size={21} /></button> : <span />}</header>

        <section className="wfx-mobile-welcome">
          <div><small>{new Date().toLocaleDateString(localeCode, { timeZone: "Europe/Istanbul", day: "2-digit", month: "long", year: "numeric", weekday: "long" })}</small><h1>İyi günler, {currentPerson?.name?.split(" ")[0]}</h1><p>Bugünkü vardiyan ve puantaj durumun burada.</p></div>
          <div className="avatar">{currentPerson?.name?.split(" ").map((item) => item[0]).slice(0, 2).join("")}</div>
        </section>

        <section className="wfx-today-card">
          <div className="head"><span><span className="pulse" /> {!assignedShift ? "Atanmış vardiya yok" : checkInState === "idle" ? "Check-in bekliyor" : "Şu anda vardiyadasın"}</span><Smartphone size={19} /></div>
          <h2>{assignedShift?.warehouse || "Vardiya bulunamadı"}</h2><p>{assignedShift ? `${assignedShift.role} · ${assignedShift.start}–${assignedShift.end}` : "Müdürünün vardiya ataması gerekir"}</p>
          <div className="timer"><Clock3 size={19} /><strong>{!assignedShift ? "—" : checkInState === "idle" ? assignedShift.start : "04:04"}</strong><span>{checkInState === "idle" ? "planlanan başlangıç" : "net çalışma"}</span></div>
          <AttendanceTrustRail phase={attendanceFlow.phase} active={checkInState === "active"} />
          <div className="verified">{assignedShift ? <ShieldCheck size={17} /> : <AlertCircle size={17} />} {!assignedShift ? "Vardiya olmadan check-in yapılamaz" : "Face ID verisi telefondan çıkmaz; yalnız doğrulama sonucu gönderilir"}</div>
          {attendanceFlow.message ? <div className={`wfx-attendance-flow-message ${attendanceFlow.phase}`}>{attendanceFlow.message}</div> : null}
          {checkInState === "idle" ? <button type="button" disabled={!assignedShift || ["authenticating", "verifying"].includes(attendanceFlow.phase)} onClick={() => assignedShift && startShift(assignedShift)}><Fingerprint size={18} />{attendanceFlow.phase === "authenticating" ? "Cihazda doğrula" : attendanceFlow.phase === "verifying" ? "Doğrulanıyor…" : assignedShift ? "Doğrula ve Vardiyaya Başla" : "Check-in kapalı"}</button> : <button type="button" className="active" onClick={() => openShift(ownShifts.find((shift) => shift.id === assignedShift?.id) || ownShifts[0])}>Vardiyayı Yönet <ChevronRight size={18} /></button>}
        </section>

        <section className="wfx-my-shifts-head">
          <div><span>Plan ve geçmiş</span><h2>Vardiyalarım</h2></div>
          {features.archive ? <button type="button" onClick={() => setView("archive")}><Archive size={18} /> Arşiv</button> : null}
        </section>

        <div className="wfx-mobile-filters">
          {["Tümü", "Tamamlandı", "Gelmedi", "Fazla"].map((item) => <button type="button" key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}</button>)}
        </div>

        <div className="wfx-shift-list">
          {filteredShifts.map((shift) => <ShiftCard key={shift.id} shift={shift} onClick={() => openShift(shift)} />)}
        </div>

        <MobileNav view={view} setView={setView} features={features} notificationCount={notifications.filter((item) => !item.read).length} taskCount={managerTasks.filter((item) => item.status === "Açık").length + managerAppeals.length + managerLeaveRequests.length + ownAppeals.filter((item) => item.status.includes("inceleme")).length + ownLeaveRequests.filter((item) => item.status.includes("inceleme")).length} />
      </section>
  );
}
