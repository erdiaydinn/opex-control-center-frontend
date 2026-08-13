import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  Building2,
  CalendarCheck,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Download,
  FileClock,
  FileSpreadsheet,
  MapPin,
  Megaphone,
  MessageSquareWarning,
  Menu,
  Languages,
  Moon,
  PencilLine,
  Plus,
  Printer,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Smartphone,
  Sparkles,
  ScrollText,
  Send,
  Sun,
  Trash2,
  Upload,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import {
  DEFAULT_WORKFORCE_STATE,
  formatMinutes,
  loadWorkforceState,
  pickerShifts,
  saveWorkforceState,
} from "./workforceData.js";
import {
  buildTimesheetRows,
  calculateAttendance,
  summarizeTimesheet,
  toTrDate,
} from "./workforceEngine.js";
import { WorkforceOpexLab, WorkforcePeriodClose } from "./WorkforcePeriodClose.jsx";
import WorkforceAnalyticsDashboard from "./WorkforceAnalyticsDashboard.jsx";
import { WorkforceExperienceAdmin } from "./WorkforceExperienceCenter.jsx";
import { loadRosterRows } from "./workforceRosterStore.js";
import { generateTurkeyHolidays } from "./turkeyHolidays.js";
import { parseTimeOffFile } from "./workforceImporters.js";
import { resolveWorkforcePerson } from "./workforceIdentity.js";
import { useWorkforceUi } from "./WorkforceUiContext.jsx";
import { approveAttendanceRemote, bulkApproveRemote, bulkPatchWarehousesRemote, correctAttendanceRemote, createAnnouncementRemote, createRuleRemote, createShiftRemote, importLeavesRemote, loadAdminWorkforce, resetDeviceRemote, resolveLeave, resolveManagerTask, saveNotificationPolicyRemote, saveWarehouseRemote, upsertPeopleRemote } from "./workforceApi.js";
import "./workforce.css";

const tabs = [
  { id: "dashboard", label: "Workforce Analytics", icon: Clock3, feature: "dashboard" },
  { id: "attendance", label: "Puantaj", icon: FileClock, feature: "attendance" },
  { id: "timesheet", label: "Puantaj Çıktısı", icon: Printer, feature: "timesheet" },
  { id: "periodClose", label: "Dönem Kapanışı", icon: FileSpreadsheet, feature: "periodClose" },
  { id: "users", label: "Kullanıcılar", icon: UsersRound, feature: "periodClose" },
  { id: "opexLab", label: "Geçici OPEX Roster Lab", icon: AlertTriangle, feature: "opexLab" },
  { id: "shifts", label: "Vardiya Planı", icon: CalendarDays, feature: "shifts" },
  { id: "approvals", label: "Onay Bekleyenler", icon: CheckCircle2, feature: "approvals" },
  { id: "managerTasks", label: "Yönetici Görevleri", icon: ClipboardCheck, feature: "managerTasks" },
  { id: "communications", label: "Duyuru ve Bildirimler", icon: Megaphone, feature: "communications" },
  { id: "experience", label: "Çalışan Deneyimi", icon: Sparkles, feature: "communications" },
  { id: "systemConfig", label: "Sistem Konfigürasyonu", icon: Settings2, feature: "systemConfig" },
  { id: "leaves", label: "İzin Yönetimi", icon: CalendarCheck, feature: "leaves" },
  { id: "warehouses", label: "Depo ve Konum", icon: MapPin, feature: "warehouses" },
  { id: "rules", label: "Kural ve Tatiller", icon: Settings2, feature: "rules" },
  { id: "devices", label: "Cihaz Yönetimi", icon: Smartphone, feature: "devices" },
  { id: "audit", label: "Audit Log", icon: ScrollText, feature: "audit" },
  { id: "picker", label: "Picker Uygulaması", icon: Smartphone, feature: "pickerApp" },
];

const emptyShift = { personId: "", warehouseId: "", date: "2026-07-15", start: "08:00", end: "17:00", breakMinutes: 60, role: "Picker" };
const emptyWarehouse = { name: "", code: "", region: "", address: "", latitude: "", longitude: "", radius: 120, accuracy: 50, method: "Konum + cihaz", qrEnabled: false, status: "Aktif" };
const emptyHoliday = { name: "", startDate: "2026-07-15", startTime: "00:00", endDate: "2026-07-15", endTime: "23:59", scope: "Tüm Türkiye", active: true };
const emptyLeave = { personId: "", typeId: "annual", date: "2026-07-15", minutes: 450, note: "" };

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function statusClass(value = "") {
  const normalized = value.toLocaleLowerCase("tr-TR");
  if (normalized.includes("tamam") || normalized.includes("onaylandı") || normalized.includes("güvenilir") || normalized === "aktif") return "success";
  if (normalized.includes("vardiyada") || normalized.includes("canlı")) return "live";
  if (normalized.includes("bekliyor") || normalized.includes("fazla") || normalized.includes("uyarı") || normalized.includes("düzeltme")) return "warning";
  if (normalized.includes("gelmedi") || normalized.includes("eksik") || normalized.includes("gerekli") || normalized.includes("pasif")) return "danger";
  return "neutral";
}

function csvEscape(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function decimalHours(minutes) {
  return Number((Number(minutes || 0) / 60).toFixed(2));
}

function datesBetween(startDate, endDate) {
  const rows = [];
  const start = new Date(`${startDate}T12:00:00`);
  const end = new Date(`${endDate || startDate}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) return rows;
  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) rows.push(cursor.toISOString().slice(0, 10));
  return rows;
}

function downloadText(filename, content, type = "text/csv;charset=utf-8") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function timeSpanMinutes(start, end, breakMinutes = 0) {
  const [sh, sm] = String(start).split(":").map(Number);
  const [eh, em] = String(end).split(":").map(Number);
  let span = eh * 60 + em - (sh * 60 + sm);
  if (span <= 0) span += 1440;
  return Math.max(0, span - Number(breakMinutes || 0));
}

function grossSpanMinutes(start, end) {
  return timeSpanMinutes(start, end, 0);
}

function ruleValue(rules, engineKey, fallback, effectiveDate = new Date().toISOString().slice(0, 10)) {
  const current = rules
    .filter((rule) => (rule.engineKey || rule.id) === engineKey && rule.active !== false && (!rule.effectiveFrom || rule.effectiveFrom <= effectiveDate))
    .sort((a, b) => String(b.effectiveFrom || "").localeCompare(String(a.effectiveFrom || "")))[0];
  return Number(current?.value ?? fallback);
}

function automaticBreakMinutes(rules, start, end, effectiveDate) {
  const gross = grossSpanMinutes(start, end);
  if (gross <= 240) return ruleValue(rules, "breakShort", 15, effectiveDate);
  if (gross <= 450) return ruleValue(rules, "breakMedium", 30, effectiveDate);
  return ruleValue(rules, "breakLong", 60, effectiveDate);
}

function shiftInterval(shift) {
  const start = new Date(`${shift.date}T${shift.start}:00`);
  const end = new Date(`${shift.date}T${shift.end}:00`);
  if (end <= start) end.setDate(end.getDate() + 1);
  return { start, end };
}

function shiftNotifications(shift, settings = {}) {
  const createdAt = new Date().toISOString();
  const { start, end } = shiftInterval(shift);
  const rows = [];
  if (settings.shiftPublished !== false) rows.push({ id: uid("NTF"), personId: shift.personId, type: "shift-published", title: "Vardiyanız yayınlandı", message: `${shift.warehouse} · ${toTrDate(shift.date)} · ${shift.start}–${shift.end}`, createdAt, scheduledAt: createdAt, read: false });
  if (settings.checkInReminder !== false) {
    const reminder = new Date(start.getTime() - Number(settings.checkInReminderMinutes || 15) * 60000);
    rows.push({ id: uid("NTF"), personId: shift.personId, type: "check-in-reminder", title: "Check-in yapmayı unutmayın", message: `${shift.warehouse} vardiyanız ${shift.start} saatinde başlayacak.`, createdAt, scheduledAt: reminder.toISOString(), read: false });
  }
  if (settings.checkOutReminder !== false) {
    const reminder = new Date(end.getTime() - Number(settings.checkOutReminderMinutes || 15) * 60000);
    rows.push({ id: uid("NTF"), personId: shift.personId, type: "check-out-reminder", title: "Check-out yapmayı unutmayın", message: `${shift.warehouse} vardiyanız ${shift.end} saatinde bitecek.`, createdAt, scheduledAt: reminder.toISOString(), read: false });
  }
  return rows;
}

function violatesRest(candidate, shifts, minimumMinutes) {
  const next = shiftInterval(candidate);
  return shifts.some((shift) => {
    if (shift.personId !== candidate.personId || shift.id === candidate.id || shift.status === "İptal") return false;
    const current = shiftInterval(shift);
    const gap = next.start >= current.end ? (next.start - current.end) / 60000 : current.start >= next.end ? (current.start - next.end) / 60000 : -1;
    return gap < minimumMinutes;
  });
}

function Modal({ title, eyebrow, children, onClose, onSave, saveLabel = "Kaydet", saveDisabled = false, wide = false }) {
  return (
    <div className="wfx-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className={`wfx-modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span>{eyebrow}</span><h2>{title}</h2></div><button type="button" className="icon" onClick={onClose}><X size={18} /></button></header>
        {children}
        <footer><button type="button" className="secondary" onClick={onClose}>Vazgeç</button>{onSave ? <button type="button" disabled={saveDisabled} onClick={onSave}><Check size={17} />{saveLabel}</button> : null}</footer>
      </section>
    </div>
  );
}

function FormField({ label, children, wide = false }) {
  return <label className={wide ? "wide" : ""}>{label}{children}</label>;
}

export default function WorkforceControl() {
  const navigate = useNavigate();
  const rootRef = useRef(null);
  const fileRef = useRef(null);
  const managerTimeOffRef = useRef(null);
  const { user, canFeature, canAction, isSuperAdmin } = useAuth();
  const { theme, setTheme, locale, setLocale, dir, localeCode, useDomLocalization } = useWorkforceUi();
  const [state, setState] = useState(() => loadWorkforceState());
  const [activeTab, setActiveTab] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [selectedRows, setSelectedRows] = useState([]);
  const [modal, setModal] = useState(null);
  const [notice, setNotice] = useState("");
  const [settingsTab, setSettingsTab] = useState("rules");
  const [holidayYear, setHolidayYear] = useState("2026");
  const [warehouseSelection, setWarehouseSelection] = useState([]);
  const [auditQuery, setAuditQuery] = useState("");
  const [auditEventFilter, setAuditEventFilter] = useState("");
  const [timesheetFilter, setTimesheetFilter] = useState({ mode: "warehouse", warehouse: "Fulya (İstanbul)", personId: "", startDate: "2026-07-01", endDate: "2026-07-31" });
  const [dashboardRosterRows, setDashboardRosterRows] = useState([]);
  const [dashboardPeriod, setDashboardPeriod] = useState({ startDate: "2026-06-01", endDate: "2026-07-20", regionalManager: "", regionalExecutive: "", warehouse: "" });
  useDomLocalization(rootRef, locale);

  const superAdmin = isSuperAdmin();
  const allowed = (action) => superAdmin || canAction("workforce", action);
  const permissions = {
    manualCorrection: allowed("manualCorrection"),
    approve: allowed("approveAttendance"),
    bulkApprove: allowed("bulkApprove"),
    createShift: allowed("createShift"),
    bulkShift: allowed("bulkShiftUpload"),
    export: allowed("export"),
    print: allowed("printAttendance"),
    warehouses: allowed("manageWarehouses"),
    rules: allowed("manageRules"),
    holidays: allowed("manageHolidays"),
    leaves: allowed("manageLeaves"),
    devices: allowed("manageDevices"),
    fullNationalId: allowed("viewFullNationalId"),
    manageEmployees: allowed("manageEmployees"),
    importTimeOff: allowed("importTimeOff"),
    closePeriod: allowed("runPayrollClose"),
    importRoster: allowed("importRoster"),
    overrideRoster: allowed("overrideRoster"),
    assignRosterTask: allowed("assignRosterTask"),
    resolveManagerTasks: allowed("resolveManagerTasks"),
    manageAnnouncements: allowed("manageAnnouncements"),
    manageNotifications: allowed("manageNotifications"),
    manageSystemConfig: allowed("manageSystemConfig"),
    manageNorms: allowed("manageStaffingNorms"),
    audit: allowed("viewAuditLog"),
  };

  const visibleTabs = tabs.filter((tab) => superAdmin || canFeature("workforce", tab.feature));
  const attendance = useMemo(() => state.attendance.map((row) => calculateAttendance(row, state.holidays, state.settings)), [state.attendance, state.holidays, state.settings]);
  const filteredAttendance = useMemo(() => attendance.filter((row) => {
    const haystack = [row.name, row.personId, row.warehouse, row.status, row.approval].join(" ").toLocaleLowerCase("tr-TR");
    return (!query || haystack.includes(query.toLocaleLowerCase("tr-TR"))) && (!warehouseFilter || row.warehouse === warehouseFilter);
  }), [attendance, query, warehouseFilter]);
  const pendingRows = filteredAttendance.filter((row) => row.status !== "Vardiyada" && row.approval !== "İK onaylı");
  const timesheetRows = useMemo(() => buildTimesheetRows(state, {
    personId: timesheetFilter.mode === "person" ? timesheetFilter.personId : "",
    warehouse: timesheetFilter.mode === "warehouse" ? timesheetFilter.warehouse : "",
    startDate: timesheetFilter.startDate,
    endDate: timesheetFilter.endDate,
  }), [state, timesheetFilter]);
  const timesheetSummary = useMemo(() => summarizeTimesheet(timesheetRows), [timesheetRows]);

  async function refreshAdmin() {
    try {
      const data = await loadAdminWorkforce();
      setState((current) => ({
        ...current,
        people: (data.people || []).length ? data.people.map((item) => ({ ...item, id: item.employeeId, rosterIds: item.rosterIds || [], name: item.fullName, role: item.position, nationalId: item.tckn, warehouse: item.warehouse || item.warehouseId || "", warehouseCode: item.warehouseId || "", hireDate: item.employmentStart || "", terminationDate: item.employmentEnd || "" })) : current.people,
        warehouses: (data.warehouses || []).map((item) => ({ ...item, code: item.code || item.id, accuracy: item.maxAccuracy, status: item.active === false ? "Pasif" : "Aktif", method: "Konum + cihaz", qrEnabled: false })),
        rules: data.rules || current.rules,
        shifts: data.shifts || [], attendance: data.attendance || [], leaves: data.leaves || current.leaves, devices: data.devices || [],
        leaveRequests: data.leaveRequests || [], correctionRequests: data.managerTasks || [],
        announcements: data.announcements || [], featureFlags: data.features || current.featureFlags,
        notificationSettings: data.notificationPolicy || current.notificationSettings,
        audit: data.audit || [],
      }));
    } catch (error) { setNotice(error.message || "Backend Workforce verileri alınamadı."); }
  }
  useEffect(() => { refreshAdmin(); }, []);
  useEffect(() => { if (import.meta.env.DEV) saveWorkforceState(state); }, [state]);
  useEffect(() => { loadRosterRows().then(setDashboardRosterRows).catch(() => setDashboardRosterRows([])); }, [state.rosterImport?.importedAt]);
  useEffect(() => { if (!notice) return undefined; const timer = window.setTimeout(() => setNotice(""), 3000); return () => clearTimeout(timer); }, [notice]);

  function updateState(key, updater, auditEvent) {
    setState((current) => {
      const nextValue = typeof updater === "function" ? updater(current[key]) : updater;
      return { ...current, [key]: nextValue, audit: auditEvent ? [...current.audit, { id: uid("AUD"), at: new Date().toISOString(), actor: user?.email, ...auditEvent }] : current.audit };
    });
  }

  async function approve(ids) {
    if (!ids.length) return;
    try { if (ids.length === 1) await approveAttendanceRemote(ids[0]); else await bulkApproveRemote(ids); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setSelectedRows([]);
    setNotice(`${ids.length} puantaj kaydı onaylandı.`);
  }

  function openShiftModal(shift = null) {
    setModal({ type: "shift", value: shift ? { ...shift } : { ...emptyShift } });
  }

  async function saveShift() {
    const form = modal.value;
    const person = state.people.find((item) => item.id === form.personId);
    const warehouse = state.warehouses.find((item) => item.id === form.warehouseId);
    if (!person || !warehouse || !form.date || !form.start || !form.end) return;
    const duplicate = state.shifts.some((row) => row.personId === form.personId && row.date === form.date && row.id !== form.id && row.status !== "İptal");
    if (duplicate) { setNotice("Bu personelin aynı tarihte aktif vardiyası var; kayıt reddedildi."); return; }
    const breakMinutes = Math.max(Number(form.breakMinutes || 0), automaticBreakMinutes(state.rules, form.start, form.end, form.date));
    const expectedMinutes = timeSpanMinutes(form.start, form.end, breakMinutes);
    if (expectedMinutes > ruleValue(state.rules, "dailyMax", 660, form.date)) { setNotice("Günlük azami net çalışma kuralı aşıldı; vardiya kaydedilmedi."); return; }
    const candidate = { ...form, breakMinutes };
    if (violatesRest(candidate, state.shifts, ruleValue(state.rules, "betweenShifts", 660, form.date))) { setNotice("Vardiyalar arası asgari dinlenme kuralı sağlanmıyor."); return; }
    if (form.id) { setNotice("Canlı vardiya değişikliği için mevcut kaydı iptal edip yeni sürüm oluşturun; ham kayıt korunur."); return; }
    try { await createShiftRemote({ person_id: form.personId, person_name: person.name, warehouse_id: warehouse.id, date: form.date, start: form.start, end: form.end, break_minutes: breakMinutes, role: form.role || person.role }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null);
    setNotice(form.id ? "Vardiya güncellendi." : "Vardiya oluşturuldu; picker artık check-in yapabilir.");
  }

  function downloadShiftTemplate() {
    const content = "person_id;warehouse_code;date;start;end;break_minutes;role\n100184;FUL;2026-07-15;08:00;17:00;60;Picker\n";
    downloadText("workforce_toplu_vardiya_sablonu.csv", `\ufeff${content}`);
  }

  function uploadShifts(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const lines = String(reader.result || "").replace(/^\ufeff/, "").split(/\r?\n/).filter(Boolean);
      const delimiter = lines[0]?.includes(";") ? ";" : ",";
      const headers = lines.shift().split(delimiter).map((item) => item.trim().toLowerCase());
      const created = [];
      const errors = [];
      lines.forEach((line, index) => {
        const values = line.split(delimiter).map((item) => item.trim());
        const row = Object.fromEntries(headers.map((header, i) => [header, values[i] || ""]));
        const person = state.people.find((item) => item.id === row.person_id);
        const warehouse = state.warehouses.find((item) => item.code.toLowerCase() === String(row.warehouse_code).toLowerCase() || item.name === row.warehouse_code);
        if (!person || !warehouse || !row.date || !row.start || !row.end) { errors.push(`${index + 2}. satır`); return; }
        const duplicate = [...state.shifts, ...created].some((item) => item.personId === person.id && item.date === row.date && item.status !== "İptal");
        const breakMinutes = Math.max(Number(row.break_minutes || 0), automaticBreakMinutes(state.rules, row.start, row.end, row.date));
        const expectedMinutes = timeSpanMinutes(row.start, row.end, breakMinutes);
        const candidate = { personId: person.id, date: row.date, start: row.start, end: row.end };
        if (duplicate || expectedMinutes > ruleValue(state.rules, "dailyMax", 660, row.date) || violatesRest(candidate, [...state.shifts, ...created], ruleValue(state.rules, "betweenShifts", 660, row.date))) { errors.push(`${index + 2}. satır`); return; }
        created.push({ id: uid("SHIFT"), personId: person.id, personName: person.name, warehouseId: warehouse.id, warehouse: warehouse.name, date: row.date, start: row.start, end: row.end, breakMinutes, expectedMinutes, role: row.role || person.role, status: "Atandı", source: "Toplu CSV", createdBy: user?.email, createdAt: new Date().toISOString() });
      });
      if (created.length) for (const shift of created) {
        try { await createShiftRemote({ person_id: shift.personId, person_name: shift.personName, warehouse_id: shift.warehouseId, date: shift.date, start: shift.start, end: shift.end, break_minutes: shift.breakMinutes, role: shift.role }); }
        catch { errors.push(`${shift.personId} / ${shift.date}`); }
      }
      await refreshAdmin();
      setNotice(`${created.length} vardiya yüklendi${errors.length ? `; ${errors.length} satır reddedildi` : ""}.`);
    };
    reader.readAsText(file, "UTF-8");
  }

  async function saveWarehouse() {
    const form = modal.value;
    if (!form.name || !form.code || form.latitude === "" || form.longitude === "") return;
    try { await saveWarehouseRemote({ id: form.id || null, name: form.name, latitude: Number(form.latitude), longitude: Number(form.longitude), m2: Number(form.m2 || 0), radius: Number(form.radius), max_accuracy: Number(form.accuracy), active: form.status !== "Pasif" }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setNotice("Depo konum ayarları kaydedildi.");
  }

  async function saveBulkWarehouses() {
    const form = modal.value;
    const patch = {};
    if (form.region) patch.region = form.region;
    if (form.radius !== "") patch.radius = Number(form.radius);
    if (form.accuracy !== "") patch.accuracy = Number(form.accuracy);
    if (form.method) patch.method = form.method;
    if (form.status) patch.status = form.status;
    if (form.qrEnabled !== "") patch.qrEnabled = form.qrEnabled === true || form.qrEnabled === "true";
    try { await bulkPatchWarehousesRemote({ warehouse_ids: warehouseSelection, radius: patch.radius ?? null, max_accuracy: patch.accuracy ?? null, active: patch.status ? patch.status !== "Pasif" : null }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setWarehouseSelection([]); setNotice(`${warehouseSelection.length} depo toplu olarak güncellendi.`);
  }

  async function saveRule() {
    const form = modal.value;
    if (!form.title || !form.engineKey || !form.effectiveFrom || Number(form.value) < 0) return;
    try { await createRuleRemote({ engine_key: form.engineKey, title: form.title, value: Number(form.value), level: form.level, effective_from: form.effectiveFrom, note: form.note || "" }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setNotice("Kuralın yeni sürümü kaydedildi ve başlangıç tarihinden itibaren hesap motoruna bağlandı.");
  }

  async function resetDevice() {
    const form = modal.value;
    if (!form.reason?.trim()) return;
    try { await resetDeviceRemote(form.personId, form.reason); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null);
    setNotice(`${form.person} için eski cihaz iptal edildi; yeni telefonda güvenli kayıt açıldı.`);
  }

  function saveHoliday() {
    const form = modal.value;
    if (!form.name || !form.startDate || !form.endDate) return;
    const record = { id: form.id || uid("HOL"), name: form.name, startAt: `${form.startDate}T${form.startTime}:00+03:00`, endAt: `${form.endDate}T${form.endTime}:59+03:00`, scope: form.scope, active: form.active, demo: false };
    updateState("holidays", (rows) => form.id ? rows.map((row) => row.id === form.id ? record : row) : [...rows, record], { event: form.id ? "HOLIDAY_UPDATED" : "HOLIDAY_CREATED", recordId: record.id });
    setModal(null); setNotice("Resmî tatil saat aralığı hesap motoruna eklendi.");
  }

  function holidayToForm(item) {
    const start = new Date(item.startAt); const end = new Date(item.endAt);
    const pad = (value) => String(value).padStart(2, "0");
    const date = (value) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
    const time = (value) => `${pad(value.getHours())}:${pad(value.getMinutes())}`;
    return { ...item, startDate: date(start), startTime: time(start), endDate: date(end), endTime: time(end) };
  }

  function saveLeave() {
    const form = modal.value;
    const person = state.people.find((item) => item.id === form.personId);
    if (!person || !form.typeId || !form.date) return;
    const duplicate = state.leaves.some((item) => item.personId === form.personId && item.date === form.date && item.id !== form.id);
    if (duplicate) { setNotice("Bu çalışan ve tarih için izin kaydı zaten var; mükerrer kayıt oluşturulmadı."); return; }
    const record = { ...form, id: form.id || uid("LEV"), warehouse: person.warehouse, minutes: Number(form.minutes), approval: "Onaylandı", enteredBy: user?.email, enteredAt: new Date().toISOString() };
    updateState("leaves", (rows) => form.id ? rows.map((row) => row.id === form.id ? record : row) : [...rows, record], { event: form.id ? "LEAVE_UPDATED" : "LEAVE_CREATED", recordId: record.id });
    setModal(null); setNotice("İzin kaydı puantaja işlendi.");
  }

  function saveLeaveType() {
    const form = modal.value;
    const record = { ...form, excusesMissing: form.excusesMissing !== false, id: form.id || uid("LT"), code: String(form.code || form.name).toLocaleUpperCase("tr-TR").replaceAll(" ", "_") };
    updateState("leaveTypes", (rows) => form.id ? rows.map((row) => row.id === form.id ? record : row) : [...rows, record], { event: form.id ? "LEAVE_TYPE_UPDATED" : "LEAVE_TYPE_CREATED", recordId: record.id });
    setModal(null); setNotice("İzin türünün puantaj etkileri kaydedildi.");
  }

  async function uploadManagerTimeOff(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const imported = await parseTimeOffFile(file);
      const bootstrap = [...new Map(imported.rows.filter((row) => row.sourcePersonId && row.nationalId?.length === 11 && row.personName && !resolveWorkforcePerson(row, state.people, state.rosterIdentityMap || {}).person).map((row) => [row.nationalId, { id: String(row.sourcePersonId), name: row.personName, nationalId: row.nationalId, role: "Çalışan", warehouse: "", hireDate: "", terminationDate: "", active: true }])).values()];
      if (bootstrap.length) await upsertPeopleRemote(bootstrap);
      const peopleForResolution = [...state.people, ...bootstrap];
      if (bootstrap.length) updateState("people", (current) => {
        const byId = new Map(current.map((person) => [String(person.id), person]));
        bootstrap.forEach((person) => { if (!byId.has(String(person.id))) byId.set(String(person.id), person); });
        return [...byId.values()];
      }, { event: "PEOPLE_BOOTSTRAPPED_FROM_TIME_OFF", file: file.name, count: bootstrap.length });
      const existingKeys = new Set(state.leaves.map((leave) => `${leave.personId}|${leave.date}`));
      const unmatched = [];
      const accepted = imported.rows.flatMap((leave) => {
        const resolved = resolveWorkforcePerson(leave, peopleForResolution, state.rosterIdentityMap || {});
        if (!resolved.person) { unmatched.push(leave); return []; }
        const sourceKey = `${resolved.person.id}|${leave.date}`;
        if (existingKeys.has(sourceKey)) return [];
        existingKeys.add(sourceKey);
        return [{ ...leave, personId: String(resolved.person.id), sourceKey, identityMethod: resolved.method, personName: resolved.person.name, warehouse: resolved.person.warehouse || "Eşleşmeyen personel", enteredBy: user?.email, enteredAt: new Date().toISOString() }];
      });
      const customTypes = [...new Map(accepted.filter((leave) => !state.leaveTypes.some((type) => type.id === leave.typeId)).map((leave) => [leave.typeId, { id: leave.typeId, code: leave.typeId.toLocaleUpperCase("tr-TR"), name: leave.category, paid: false, creditsPayroll: false, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true }])).values()];
      if (accepted.length) await importLeavesRemote(accepted, file.name);
      if (customTypes.length) updateState("leaveTypes", (rows) => [...rows, ...customTypes], { event: "LEAVE_TYPES_AUTO_CREATED", count: customTypes.length });
      if (accepted.length) updateState("leaves", (rows) => [...rows, ...accepted], { event: "TIME_OFF_MANAGER_IMPORTED", count: accepted.length, sourceRows: imported.sourceCount, file: file.name });
      setNotice(`${accepted.length} izin günü TC öncelikli yüklendi; ${imported.rows.length - accepted.length - unmatched.length} mükerrer gün atlandı; ${unmatched.length} kayıt eşleşmedi.`);
    } catch (error) { setNotice(`Time Off dosyası okunamadı: ${error.message}`); }
  }

  async function saveCorrection() {
    const form = modal.value;
    if (!form.reason?.trim()) return;
    try { await correctAttendanceRemote(form.id, { check_in: form.checkIn === "—" ? null : form.checkIn, check_out: form.checkOut === "—" ? null : form.checkOut, break_minutes: Number(form.breakMinutes), reason: form.reason }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setNotice("Manuel düzeltme audit kaydıyla oluşturuldu.");
  }

  async function saveNotificationSettings() {
    const form = modal.value;
    const record = {
      shiftPublished: form.shiftPublished !== false,
      checkInReminder: form.checkInReminder !== false,
      checkInReminderMinutes: Math.max(0, Number(form.checkInReminderMinutes || 0)),
      checkOutReminder: form.checkOutReminder !== false,
      checkOutReminderMinutes: Math.max(0, Number(form.checkOutReminderMinutes || 0)),
    };
    try { await saveNotificationPolicyRemote({ shift_published: record.shiftPublished, check_in_reminder: record.checkInReminder, check_in_reminder_minutes: record.checkInReminderMinutes, check_out_reminder: record.checkOutReminder, check_out_reminder_minutes: record.checkOutReminderMinutes }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setNotice("Vardiya bildirim ve hatırlatma politikası kaydedildi.");
  }

  async function saveAnnouncement() {
    const form = modal.value;
    if (!form.title?.trim() || !form.message?.trim()) return;
    const recipients = state.people.filter((person) => form.targetType === "all" || (form.targetType === "warehouse" && person.warehouse === form.targetValue) || (form.targetType === "person" && person.id === form.targetValue));
    try { await createAnnouncementRemote({ title: form.title, message: form.message, target_type: form.targetType, target_value: form.targetValue || "", publish_at: form.publishAt ? new Date(form.publishAt).toISOString() : null }); await refreshAdmin(); }
    catch (error) { setNotice(error.message); return; }
    setModal(null); setNotice(`Duyuru yayınlandı; ${recipients.length} kullanıcı hedeflendi.`);
  }

  async function saveManagerTask() {
    const form = modal.value;
    const resolvedAt = new Date().toISOString();
    if (!form.managerNote?.trim()) return;
    if (form.kind === "roster") {
      const targetMinutes = Math.max(0, Number(form.targetMinutes || 450));
      updateState("rosterOverrides", (current = {}) => ({ ...current, ...Object.fromEntries((form.recordKeys || []).map((key) => [key, { normalizedMinutes: targetMinutes, reason: form.managerNote, actor: user?.email, at: resolvedAt, simulationOnly: false }])) }), { event: "ROSTER_MANAGER_TASK_CORRECTION_APPLIED", taskId: form.id, targetMinutes, reason: form.managerNote, recordKeys: form.recordKeys || [] });
      updateState("rosterTasks", (rows = []) => rows.map((row) => row.id === form.id ? { ...row, status: "Düzeltildi", targetMinutes, managerNote: form.managerNote, completedAt: resolvedAt, completedBy: user?.email } : row), { event: "ROSTER_MANAGER_TASK_RESOLVED", taskId: form.id, targetMinutes });
    } else if (form.kind === "leave") {
      try { await resolveLeave(form.id, form.decision === "Onaylandı" ? "APPROVED" : "REJECTED", form.managerNote); await refreshAdmin(); }
      catch (error) { setNotice(error.message); return; }
    } else {
      try { await resolveManagerTask(form.id, { decision: form.decision === "Onaylandı" ? "APPROVED" : "REJECTED", manager_note: form.managerNote, requested_check_in: form.requestedCheckIn || null, requested_check_out: form.requestedCheckOut || null, target_minutes: form.targetMinutes ? Number(form.targetMinutes) : null }); await refreshAdmin(); }
      catch (error) { setNotice(error.message); return; }
    }
    setModal(null); setNotice("Yönetici görevi düzeltme ve audit kaydıyla sonuçlandırıldı.");
  }

  function exportTimesheet() {
    const headers = ["Personel ID", "Ad Soyad", "Depo", "Tarih", "Normal (saat)", "Gece (saat)", "Resmi Tatil (saat)", "Fazla Mesai (saat)", "Eksik (saat)", "İzin", "Ücretli İzin (saat)"];
    const lines = [headers.map(csvEscape).join(";"), ...timesheetRows.map((row) => [row.personId, row.name, row.warehouse, row.date, decimalHours(row.normalMinutes), decimalHours(row.nightMinutes), decimalHours(row.holidayMinutes), decimalHours(row.overtimeMinutes), decimalHours(row.missingMinutes), row.leaveType || "", decimalHours(row.paidLeaveMinutes)].map(csvEscape).join(";"))];
    downloadText("workforce_puantaj_ciktisi.csv", `\ufeff${lines.join("\n")}`);
  }

  function renderAttendanceTable(rows, withSelection = false) {
    const allSelected = rows.length > 0 && rows.every((row) => selectedRows.includes(row.id));
    return <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr>{withSelection ? <th><input type="checkbox" checked={allSelected} onChange={() => setSelectedRows(allSelected ? selectedRows.filter((id) => !rows.some((row) => row.id === id)) : [...new Set([...selectedRows, ...rows.map((row) => row.id)])])} /></th> : null}<th>Personel</th><th>Depo</th><th>Tarih / Plan</th><th>Giriş–Çıkış</th><th>Normal</th><th>Gece</th><th>Resmî tatil</th><th>Eksik / Fazla</th><th>Durum / Onay</th><th>İşlem</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>{withSelection ? <td><input type="checkbox" checked={selectedRows.includes(row.id)} onChange={() => setSelectedRows((current) => current.includes(row.id) ? current.filter((id) => id !== row.id) : [...current, row.id])} /></td> : null}<td><strong>{row.name}</strong><small>{row.personId} · {row.role}</small></td><td><strong>{row.warehouse}</strong><small>{row.location} · {row.source}</small></td><td><strong>{row.date}</strong><small>{row.planned}</small></td><td><strong>{row.checkIn} → {row.checkOut}</strong><small>Mola: {formatMinutes(row.breakMinutes)}</small></td><td><strong>{formatMinutes(row.normalMinutes)}</strong></td><td><strong>{formatMinutes(row.nightMinutes)}</strong></td><td><strong className={row.holidayMinutes ? "wfx-purple" : ""}>{formatMinutes(row.holidayMinutes)}</strong></td><td><strong className={row.missingMinutes ? "wfx-red" : ""}>−{formatMinutes(row.missingMinutes)}</strong><small className={row.overtimeMinutes ? "wfx-purple" : ""}>+{formatMinutes(row.overtimeMinutes)}</small></td><td><span className={`wfx-status ${statusClass(row.status)}`}>{row.status}</span><small><span className={`wfx-status ${statusClass(row.approval)}`}>{row.approval}</span></small></td><td><div className="wfx-row-actions">{permissions.approve && row.status !== "Vardiyada" && row.approval !== "İK onaylı" ? <button type="button" className="icon success" onClick={() => approve([row.id])}><Check size={16} /></button> : null}{permissions.manualCorrection ? <button type="button" className="icon" onClick={() => setModal({ type: "correction", value: { ...row, breakStart: row.breaks?.[0]?.start || "", breakEnd: row.breaks?.[0]?.end || "", reason: "" } })}><PencilLine size={16} /></button> : <span className="wfx-locked-action"><ShieldCheck size={15} /></span>}</div></td></tr>)}</tbody></table></div>;
  }

  function renderDashboard() {
    const temporaryRosterActive = Boolean(state.rosterImport && state.rosterImport.temporaryActive !== false);
    return <WorkforceAnalyticsDashboard state={state} attendance={attendance} rosterRows={temporaryRosterActive ? dashboardRosterRows : []} period={dashboardPeriod} setPeriod={setDashboardPeriod} locale={locale} theme={theme} />;
  }

  function renderAttendance() {
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Hesaplanan puantaj</span><h2>Normal, gece ve resmî tatil saatleri</h2><p>Mola aralığı resmî tatil/gece kesişiminden doğru şekilde düşülür.</p></div><div className="wfx-toolbar"><label className="wfx-search"><Search size={16} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Picker, ID veya depo ara…" /></label><select value={warehouseFilter} onChange={(e) => setWarehouseFilter(e.target.value)}><option value="">Tüm depolar</option>{state.warehouses.map((item) => <option key={item.id}>{item.name}</option>)}</select>{permissions.export ? <button type="button" className="secondary compact" onClick={exportTimesheet}><Download size={16} />Excel/CSV</button> : null}</div></header>{renderAttendanceTable(filteredAttendance)}{!permissions.manualCorrection ? <div className="wfx-permission-info"><ShieldCheck size={17} />Manuel düzeltme yalnız Admin veya özel yetkili kullanıcı içindir.</div> : null}</section>;
  }

  function renderApprovals() {
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Onay akışı</span><h2>Onay bekleyen kayıtlar</h2><p>Satır seç, sayfadakileri seç veya toplu onayla.</p></div><div className="wfx-toolbar"><strong className="wfx-selection-count">{selectedRows.length} seçili</strong>{permissions.bulkApprove ? <button type="button" disabled={!selectedRows.length} onClick={() => approve(selectedRows)}><CheckCircle2 size={17} />Seçilenleri onayla</button> : null}{permissions.bulkApprove ? <button type="button" className="secondary compact" onClick={() => approve(pendingRows.map((row) => row.id))}>Tümünü onayla</button> : null}</div></header>{renderAttendanceTable(pendingRows, true)}</section>;
  }

  function renderShifts() {
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Planlama</span><h2>Vardiya planı ve toplu yükleme</h2><p>Atanmış vardiya yoksa mobil check-in endpoint’i işlemi reddeder.</p></div><div className="wfx-toolbar">{permissions.bulkShift ? <><button type="button" className="secondary compact" onClick={downloadShiftTemplate}><Download size={16} />Şablon indir</button><button type="button" className="secondary compact" onClick={() => fileRef.current?.click()}><Upload size={16} />Toplu vardiya yükle</button><input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={uploadShifts} /></> : null}{permissions.createShift ? <button type="button" onClick={() => openShiftModal()}><Plus size={17} />Vardiya oluştur</button> : null}</div></header><div className="wfx-shift-table"><div className="wfx-shift-head"><span>Personel</span><span>Depo</span><span>Tarih</span><span>Saat</span><span>Net plan</span><span>Kaynak</span><span>Durum</span><span>İşlem</span></div>{state.shifts.map((shift) => <article key={shift.id}><div><strong>{shift.personName}</strong><small>{shift.personId} · {shift.role}</small></div><div><strong>{shift.warehouse}</strong><small>{shift.warehouseId}</small></div><strong>{toTrDate(shift.date)}</strong><strong>{shift.start}–{shift.end}</strong><strong>{formatMinutes(shift.expectedMinutes)}</strong><span>{shift.source}</span><span className={`wfx-status ${statusClass(shift.status)}`}>{shift.status}</span><div className="wfx-row-actions">{permissions.createShift ? <button type="button" className="icon" onClick={() => openShiftModal(shift)}><PencilLine size={15} /></button> : null}{permissions.createShift ? <button type="button" className="icon danger" onClick={() => updateState("shifts", (rows) => rows.filter((row) => row.id !== shift.id), { event: "SHIFT_DELETED", recordId: shift.id })}><Trash2 size={15} /></button> : null}</div></article>)}</div></section>;
  }

  function renderWarehouses() {
    const allSelected = state.warehouses.length > 0 && warehouseSelection.length === state.warehouses.length;
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Geofence</span><h2>Depo ve konum doğrulama</h2><p>Koordinat, yarıçap, GPS sapması ve opsiyonel QR ayarları.</p></div><div className="wfx-toolbar">{permissions.warehouses ? <button type="button" className="secondary compact" onClick={() => setWarehouseSelection(allSelected ? [] : state.warehouses.map((item) => item.id))}>{allSelected ? "Seçimi temizle" : "Tümünü seç"}</button> : null}{permissions.warehouses && warehouseSelection.length ? <button type="button" className="secondary compact" onClick={() => setModal({ type: "warehouseBulk", value: { region: "", radius: "", accuracy: "", method: "", status: "", qrEnabled: "" } })}><PencilLine size={16} />Toplu düzenle ({warehouseSelection.length})</button> : null}{permissions.warehouses ? <button type="button" onClick={() => setModal({ type: "warehouse", value: { ...emptyWarehouse } })}><Plus size={17} />Depo ekle</button> : null}</div></header><div className="wfx-card-grid">{state.warehouses.map((item) => <article className={`wfx-config-card ${warehouseSelection.includes(item.id) ? "is-selected" : ""}`} key={item.id}>{permissions.warehouses ? <label className="wfx-card-select"><input type="checkbox" checked={warehouseSelection.includes(item.id)} onChange={() => setWarehouseSelection((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} /><span /></label> : null}<div className="wfx-config-icon"><MapPin size={20} /></div><span className={`wfx-status ${statusClass(item.status)}`}>{item.status}</span><h3>{item.name}</h3><p>{item.code} · {item.region}</p><dl><div><dt>Koordinat</dt><dd>{item.latitude}, {item.longitude}</dd></div><div><dt>Yarıçap</dt><dd>{item.radius} m</dd></div><div><dt>GPS sapması</dt><dd>≤ {item.accuracy} m</dd></div><div><dt>Doğrulama</dt><dd>{item.method}</dd></div><div><dt>QR</dt><dd>{item.qrEnabled ? "Açık" : "Kapalı / opsiyonel"}</dd></div></dl>{permissions.warehouses ? <button type="button" className="wfx-card-edit" onClick={() => setModal({ type: "warehouse", value: { ...item } })}><PencilLine size={15} />Düzenle</button> : null}</article>)}</div></section>;
  }

  function renderRules() {
    const activeRules = state.rules.filter((rule) => rule.active !== false);
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Sürümlü yönetim</span><h2>Kural setleri, resmî tatiller ve izin türleri</h2><p>Her kural başlangıç tarihinden itibaren hesap motorunu etkiler; önceki sürüm audit için korunur.</p></div>{settingsTab === "rules" && permissions.rules ? <button type="button" onClick={() => setModal({ type: "rule", value: { title: "", engineKey: "dailyMax", value: 660, unit: "dakika", level: "Sert blok", effectiveFrom: new Date().toISOString().slice(0, 10), note: "" } })}><Plus size={17} />Yeni çalışma kuralı</button> : null}</header><div className="wfx-subtabs"><button className={settingsTab === "rules" ? "active" : ""} onClick={() => setSettingsTab("rules")}>Çalışma Kuralları</button><button className={settingsTab === "holidays" ? "active" : ""} onClick={() => setSettingsTab("holidays")}>Resmî Tatiller</button><button className={settingsTab === "leaveTypes" ? "active" : ""} onClick={() => setSettingsTab("leaveTypes")}>İzin Türleri</button></div>{settingsTab === "rules" ? <div className="wfx-rules">{activeRules.map((rule) => <article key={rule.id}><div><strong>{rule.title}</strong><span>{rule.level}</span></div><b>{formatMinutes(rule.value)}</b><p>{rule.note}</p><small>Başlangıç: {rule.effectiveFrom} · Motor: {rule.engineKey || rule.id}</small>{permissions.rules ? <button type="button" className="wfx-card-edit" onClick={() => setModal({ type: "rule", value: { ...rule, engineKey: rule.engineKey || rule.id } })}><PencilLine size={14} />Yeni sürüm</button> : null}</article>)}</div> : null}{settingsTab === "holidays" ? <div className="wfx-settings-list"><header><div className="wfx-toolbar"><select value={holidayYear} onChange={(event) => setHolidayYear(event.target.value)}>{Array.from({ length: 25 }, (_, index) => String(2026 + index)).map((year) => <option key={year}>{year}</option>)}</select>{permissions.holidays ? <button type="button" className="secondary compact" onClick={() => updateState("holidays", generateTurkeyHolidays(2026, 2050), { event: "TR_HOLIDAY_CALENDAR_REFRESHED", officialThrough: 2035 })}><RefreshCw size={16} />2026–2050 yenile</button> : null}{permissions.holidays ? <button type="button" onClick={() => setModal({ type: "holiday", value: { ...emptyHoliday } })}><Plus size={16} />Resmî tatil ekle</button> : null}</div></header>{state.holidays.filter((item) => item.startAt.startsWith(holidayYear)).map((item) => <article key={item.id}><CalendarCheck size={20} /><div><strong>{item.name}{item.projected ? " (öngörü)" : ""}</strong><small>{new Date(item.startAt).toLocaleString(localeCode)} → {new Date(item.endAt).toLocaleString(localeCode)}</small></div><span>{item.scope}</span><span className={`wfx-status ${item.projected ? "warning" : item.active ? "success" : "danger"}`}>{item.projected ? "Doğrulama gerekli" : item.active ? "Resmî" : "Pasif"}</span>{permissions.holidays ? <button type="button" className="icon" onClick={() => setModal({ type: "holiday", value: holidayToForm(item) })}><PencilLine size={15} /></button> : null}</article>)}</div> : null}{settingsTab === "leaveTypes" ? <div className="wfx-settings-list leave-types"><header>{permissions.rules ? <button type="button" onClick={() => setModal({ type: "leaveType", value: { name: "", code: "", paid: true, creditsPayroll: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true } })}><Plus size={16} />İzin türü ekle</button> : null}</header>{state.leaveTypes.map((item) => <article key={item.id}><CalendarDays size={20} /><div><strong>{item.name}</strong><small>{item.code}</small></div><span>{item.paid ? "Ücretli" : "Ücretsiz"}</span><span>{item.creditsPayroll ? "Puantaj kredisi var" : "Çalışmaya eklenmez"}</span><span>{item.countsWeekly ? "Haftalık toplama girer" : "Haftalık fiili çalışmaya girmez"}</span>{permissions.rules ? <button type="button" className="icon" onClick={() => setModal({ type: "leaveType", value: { ...item } })}><PencilLine size={15} /></button> : null}</article>)}</div> : null}</section>;
  }

  function renderLeaves() {
    const typeById = Object.fromEntries(state.leaveTypes.map((item) => [item.id, item]));
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>İzin işlemleri</span><h2>Çalışan izin girişleri</h2><p>Müdür izin girer; izin türünün puantaj etkisi otomatik uygulanır.</p></div><div className="wfx-toolbar">{permissions.importTimeOff ? <><button type="button" className="secondary compact" onClick={() => managerTimeOffRef.current?.click()}><Upload size={16} />Time Off toplu yükle</button><input ref={managerTimeOffRef} hidden type="file" accept=".xlsx,.xls" onChange={uploadManagerTimeOff} /></> : null}{permissions.leaves ? <button type="button" onClick={() => setModal({ type: "leave", value: { ...emptyLeave } })}><Plus size={17} />İzin gir</button> : null}</div></header><div className="wfx-settings-list">{state.leaves.map((leave) => { const person = state.people.find((item) => item.id === leave.personId); const type = typeById[leave.typeId] || {}; return <article key={leave.id}><UserRound size={20} /><div><strong>{person?.name || leave.personName}</strong><small>{leave.warehouse} · {toTrDate(leave.date)}</small></div><span className="wfx-status neutral">{type.name || leave.category}</span><span>{formatMinutes(leave.minutes)}</span><span>{type.paid ? "Ücretli" : "Ücretsiz"}</span><span>{type.countsWeekly ? "Haftalık toplama girer" : "Fiili çalışmaya eklenmez"}</span>{permissions.leaves ? <button type="button" className="icon" onClick={() => setModal({ type: "leave", value: { ...leave } })}><PencilLine size={15} /></button> : null}</article>; })}</div></section>;
  }

  function renderManagerTasks() {
    const rosterTasks = state.rosterTasks || [];
    const requests = state.correctionRequests || [];
    const leaveRequests = state.leaveRequests || [];
    const openCount = rosterTasks.filter((item) => !["Tamamlandı", "Düzeltildi"].includes(item.status)).length + requests.filter((item) => item.status?.includes("inceleme")).length + leaveRequests.filter((item) => item.status?.includes("inceleme")).length;
    const completed = rosterTasks.filter((item) => ["Tamamlandı", "Düzeltildi"].includes(item.status)).length + [...requests, ...leaveRequests].filter((item) => ["Onaylandı", "Reddedildi"].includes(item.status)).length;
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Yönetici iş merkezi</span><h2>11 saat görevleri, düzeltme ve izin talepleri</h2><p>PC ve mobil aynı görev kuyruğunu kullanır. Her karar, gerekçe ve oluşan izin kaydı audit izine yazılır.</p></div><span className="wfx-status warning">{openCount} açık görev</span></header><div className="wfx-task-summary"><article><ClipboardCheck size={22} /><div><small>11 saat / roster</small><strong>{rosterTasks.length}</strong></div></article><article><MessageSquareWarning size={22} /><div><small>Picker talepleri</small><strong>{requests.length + leaveRequests.length}</strong></div></article><article><CheckCircle2 size={22} /><div><small>Sonuçlanan</small><strong>{completed}</strong></div></article></div><div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Tür</th><th>Personel / Depo</th><th>Atanan Yönetici</th><th>Kayıt / Vardiya</th><th>Durum</th><th>İşlem</th></tr></thead><tbody>
      {leaveRequests.map((item) => <tr key={item.id}><td><strong>İzin talebi</strong><small>{item.typeName}</small></td><td><strong>{item.personName}</strong><small>{item.warehouse}</small></td><td><strong>Depo yöneticisi</strong><small>{item.createdAt?.slice(0, 16).replace("T", " ")}</small></td><td><strong>{item.startDate} – {item.endDate}</strong><small>{item.days} gün · {item.note}</small></td><td><span className={`wfx-status ${statusClass(item.status)}`}>{item.status}</span></td><td>{permissions.resolveManagerTasks ? <button type="button" onClick={() => setModal({ type: "managerTask", value: { ...item, kind: "leave", decision: item.status === "Reddedildi" ? "Reddedildi" : "Onaylandı", managerNote: item.managerNote || "" } })}><PencilLine size={15} />İzin talebini incele</button> : "—"}</td></tr>)}
      {requests.map((item) => <tr key={item.id}><td><strong>Picker itirazı</strong><small>{item.type}</small></td><td><strong>{item.personName}</strong><small>{item.warehouse}</small></td><td><strong>Depo yöneticisi</strong><small>{item.createdAt?.slice(0, 16).replace("T", " ")}</small></td><td><strong>{item.date}</strong><small>{item.actualCheckIn} → {item.actualCheckOut}</small></td><td><span className={`wfx-status ${statusClass(item.status)}`}>{item.status}</span></td><td>{permissions.resolveManagerTasks || permissions.manualCorrection ? <button type="button" onClick={() => setModal({ type: "managerTask", value: { ...item, kind: "appeal", decision: item.status === "Reddedildi" ? "Reddedildi" : "Onaylandı", managerNote: item.managerNote || "" } })}><PencilLine size={15} />İncele ve düzelt</button> : "—"}</td></tr>)}
      {rosterTasks.map((item) => <tr key={item.id}><td><strong>11 saat kontrolü</strong><small>{item.priority}</small></td><td><strong>{item.warehouse}</strong><small>{item.recordCount} kayıt</small></td><td><strong>{item.assigneeName}</strong><small>{item.assigneeSource}</small></td><td><strong>{item.periodStart} – {item.periodEnd}</strong><small>{item.id}</small></td><td><span className={`wfx-status ${statusClass(item.status)}`}>{item.status}</span></td><td>{permissions.resolveManagerTasks || permissions.assignRosterTask ? <button type="button" onClick={() => setModal({ type: "managerTask", value: { ...item, kind: "roster", targetMinutes: item.targetMinutes || 450, managerNote: item.managerNote || "" } })}><PencilLine size={15} />Düzelt</button> : "—"}</td></tr>)}
      {!requests.length && !rosterTasks.length && !leaveRequests.length ? <tr><td colSpan="6">Henüz yönetici görevi veya picker talebi bulunmuyor.</td></tr> : null}</tbody></table></div></section>;
  }

  function renderSystemConfig() {
    const labels = {
      breaks: ["Mobil mola yönetimi", "Molaya çık / molayı bitir aksiyonlarını açar."],
      leaveRequests: ["Picker izin talepleri", "Haftalık ve yıllık izin talebini müdür onayına gönderir."],
      appeals: ["İtiraz / düzeltme talepleri", "Picker'ın vardiya kaydına itiraz etmesini sağlar."],
      announcements: ["Mobil duyurular", "Hedefli duyuruları ana sayfada gösterir."],
      notifications: ["Bildirim merkezi", "Vardiya ve sistem bildirimlerini mobilde açar."],
      archive: ["Vardiya arşivi", "Picker'ın geçmiş vardiyalarını görmesini sağlar."],
      managerTasks: ["Yönetici görevleri", "11 saat ve düzeltme işlerini PC/mobil kuyruğa alır."],
      qrCheckIn: ["QR ile check-in", "Konum + cihaz doğrulamaya opsiyonel QR ekler."],
      liveBreakActivity: ["Mola canlı aktivitesi", "Aktif molayı uygulama, bildirim ekranı ve desteklenen iPhone uygulamasında canlı gösterir."],
      employeeExperience: ["Çalışan deneyimi merkezi", "Belge, eğitim, anket ve zimmet self-servisini mobilde açar."],
    };
    const flags = { ...DEFAULT_WORKFORCE_STATE.featureFlags, ...(state.featureFlags || {}) };
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Ürün yönetimi</span><h2>Şirket özellikleri ve mobil modüller</h2><p>Her özellik şirket bazında açılıp kapatılır. Yetki matrisi, açık özelliklerin kimlerce kullanılacağını ayrıca belirler.</p></div><span className="wfx-status neutral">Admin kontrolü</span></header><div className="wfx-security-note"><ShieldCheck size={18} />Değişiklik anında picker ve yönetici ekranlarına uygulanır; her açma/kapama işlemi audit log'a kaydedilir.</div><div className="wfx-feature-config-grid">{Object.entries(labels).map(([key, [title, description]]) => <article key={key}><div><strong>{title}</strong><p>{description}</p></div><button type="button" disabled={!permissions.manageSystemConfig} className={flags[key] ? "enabled" : "disabled"} onClick={() => updateState("featureFlags", { ...flags, [key]: !flags[key] }, { event: "FEATURE_FLAG_CHANGED", feature: key, enabled: !flags[key] })}><span>{flags[key] ? "Açık" : "Kapalı"}</span><i /></button></article>)}</div></section>;
  }

  function renderCommunications() {
    const settings = state.notificationSettings || DEFAULT_WORKFORCE_STATE.notificationSettings;
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>İletişim merkezi</span><h2>Duyurular ve vardiya bildirimleri</h2><p>Yayınlanan vardiya, check-in/check-out hatırlatmaları ve hedefli duyurular mobil uygulamaya gider.</p></div><div className="wfx-toolbar">{permissions.manageNotifications ? <button type="button" className="secondary compact" onClick={() => setModal({ type: "notificationSettings", value: { ...settings } })}><Settings2 size={16} />Hatırlatma ayarları</button> : null}{permissions.manageAnnouncements ? <button type="button" onClick={() => setModal({ type: "announcement", value: { title: "", message: "", targetType: "all", targetValue: "", publishAt: new Date().toISOString().slice(0, 16) } })}><Megaphone size={17} />Yeni duyuru yayınla</button> : null}</div></header><div className="wfx-notification-policy"><article><Bell size={21} /><div><small>Vardiya yayınlandı</small><strong>{settings.shiftPublished ? "Anında bildirim açık" : "Kapalı"}</strong></div></article><article><Clock3 size={21} /><div><small>Check-in hatırlatması</small><strong>{settings.checkInReminder ? `${settings.checkInReminderMinutes} dk önce` : "Kapalı"}</strong></div></article><article><Clock3 size={21} /><div><small>Check-out hatırlatması</small><strong>{settings.checkOutReminder ? `${settings.checkOutReminderMinutes} dk önce` : "Kapalı"}</strong></div></article></div><div className="wfx-settings-list"><header><strong>Yayınlanan duyurular</strong></header>{(state.announcements || []).map((item) => <article key={item.id}><Megaphone size={20} /><div><strong>{item.title}</strong><small>{item.message}</small></div><span>{item.targetType === "all" ? "Tüm kullanıcılar" : item.targetValue}</span><span>{new Date(item.publishAt || item.createdAt).toLocaleString(localeCode)}</span><span className="wfx-status success">Yayında</span></article>)}{!(state.announcements || []).length ? <div className="wfx-empty-state"><Megaphone size={28} /><strong>Henüz duyuru yayınlanmadı</strong><p>Yeni duyuru yayınla ile tüm personele, depoya veya tek kişiye bildirim gönderebilirsiniz.</p></div> : null}</div></section>;
  }

  function renderTimesheet() {
    const reportTitle = timesheetFilter.mode === "person" ? state.people.find((item) => item.id === timesheetFilter.personId)?.name || "Kişi seçilmedi" : timesheetFilter.warehouse || "Depo seçilmedi";
    return <section className="wfx-panel wfx-print-panel"><header className="wfx-panel-head responsive no-print"><div><span>İmzaya hazır rapor</span><h2>Kişi veya depo bazlı puantaj</h2></div><div className="wfx-toolbar"><select value={timesheetFilter.mode} onChange={(e) => setTimesheetFilter({ ...timesheetFilter, mode: e.target.value })}><option value="warehouse">Depo bazlı</option><option value="person">Kişi bazlı</option></select>{timesheetFilter.mode === "warehouse" ? <select value={timesheetFilter.warehouse} onChange={(e) => setTimesheetFilter({ ...timesheetFilter, warehouse: e.target.value })}>{state.warehouses.map((item) => <option key={item.id}>{item.name}</option>)}</select> : <select value={timesheetFilter.personId} onChange={(e) => setTimesheetFilter({ ...timesheetFilter, personId: e.target.value })}><option value="">Kişi seç</option>{state.people.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}<input type="date" value={timesheetFilter.startDate} onChange={(e) => setTimesheetFilter({ ...timesheetFilter, startDate: e.target.value })} /><input type="date" value={timesheetFilter.endDate} onChange={(e) => setTimesheetFilter({ ...timesheetFilter, endDate: e.target.value })} />{permissions.export ? <button type="button" className="secondary compact" onClick={exportTimesheet}><FileSpreadsheet size={16} />CSV</button> : null}{permissions.print ? <button type="button" onClick={() => window.print()}><Printer size={16} />Yazdır / PDF</button> : null}</div></header><div className="wfx-print-document"><div className="wfx-print-title"><div><strong>OPEX WORKFORCE</strong><h1>PUANTAJ ÇİZELGESİ</h1></div><div><span>{reportTitle}</span><small>{timesheetFilter.startDate} – {timesheetFilter.endDate}</small></div></div><div className="wfx-print-summary"><span>Normal<strong>{formatMinutes(timesheetSummary.normalMinutes)}</strong></span><span>Gece<strong>{formatMinutes(timesheetSummary.nightMinutes)}</strong></span><span>Resmî Tatil<strong>{formatMinutes(timesheetSummary.holidayMinutes)}</strong></span><span>Fazla Mesai<strong>{formatMinutes(timesheetSummary.overtimeMinutes)}</strong></span><span>Eksik<strong>{formatMinutes(timesheetSummary.missingMinutes)}</strong></span><span>İzin<strong>{formatMinutes(timesheetSummary.leaveMinutes)}</strong></span></div><div className="wfx-table-wrap"><table className="wfx-print-table"><thead><tr><th>Tarih</th><th>Personel</th><th>Depo</th><th>Giriş</th><th>Çıkış</th><th>Normal</th><th>Gece</th><th>Resmî Tatil</th><th>Fazla</th><th>Eksik</th><th>İzin</th></tr></thead><tbody>{timesheetRows.map((row) => <tr key={row.id}><td>{row.date}</td><td>{row.name}<small>{row.personId}</small></td><td>{row.warehouse}</td><td>{row.checkIn}</td><td>{row.checkOut}</td><td>{formatMinutes(row.normalMinutes)}</td><td>{formatMinutes(row.nightMinutes)}</td><td>{formatMinutes(row.holidayMinutes)}</td><td>{formatMinutes(row.overtimeMinutes)}</td><td>{formatMinutes(row.missingMinutes)}</td><td>{row.leaveType || "—"}</td></tr>)}</tbody></table></div><div className="wfx-signatures"><div>Çalışan İmzası<span /></div><div>Depo Müdürü<span /></div><div>İK / Bordro<span /></div></div><footer>Oluşturulma: {new Date().toLocaleString("tr-TR")} · Sistem kayıt no: {uid("RPT")}</footer></div></section>;
  }

  function renderDevices() { return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Cihaz güvenliği</span><h2>Picker cihaz eşleşmeleri</h2><p>Tek aktif cihaz, donanım korumalı uygulama anahtarı ve sunucu doğrulamalı attestation kullanılır.</p></div></header><div className="wfx-security-note"><ShieldCheck size={18} />Telefon numarası veya kopyalanabilir cihaz bilgisi yeterli kabul edilmez. Uygulama ilk kayıtta cihaz içinde dışarı çıkarılamayan anahtar üretir; her check-in/out isteği sunucunun tek kullanımlık challenge değerini imzalar. Sıfırlama eski cihaz ve anahtarı derhal iptal eder.</div><div className="wfx-device-list">{state.devices.map((item) => <article key={item.id}><Smartphone size={21} /><div><strong>{item.person}</strong><small>{item.id} · {item.model}</small></div><div><strong>{item.os}</strong><small>Uygulama {item.app} · {item.attestationStatus || "Doğrulandı"}</small></div><span className={`wfx-status ${statusClass(item.integrity)}`}>{item.integrity}</span><div><strong>{item.lastSeen}</strong><small>Son görülme</small></div>{permissions.devices ? <button type="button" className="secondary compact wfx-device-reset" onClick={() => setModal({ type: "deviceReset", value: { ...item, reason: "" } })}><RefreshCw size={15} />Cihazı sıfırla</button> : null}</article>)}</div></section>; }

  function renderAudit() {
    const events = [...(state.audit || [])].reverse();
    const filtered = events.filter((row) => (!auditEventFilter || row.event === auditEventFilter) && (!auditQuery || JSON.stringify(row).toLocaleLowerCase("tr-TR").includes(auditQuery.toLocaleLowerCase("tr-TR"))));
    const eventNames = [...new Set(events.map((row) => row.event).filter(Boolean))].sort();
    const exportAudit = () => downloadText(`workforce_audit_${new Date().toISOString().slice(0, 10)}.csv`, `\ufeff${["Zaman;Olay;Kullanıcı;Kayıt;Detay", ...filtered.map((row) => [row.at, row.event, row.actor, row.recordId || row.recordIds?.join(",") || "", csvEscape(JSON.stringify(row))].join(";"))].join("\n")}`);
    return <section className="wfx-panel"><header className="wfx-panel-head responsive"><div><span>Adli iz ve hesap verebilirlik</span><h2>Workforce Audit Log</h2><p>Kim, ne zaman, hangi kayıt üzerinde ne yaptı; önceki ve sonraki değerlerle izlenir.</p></div><div className="wfx-toolbar"><label className="wfx-search"><Search size={16} /><input value={auditQuery} onChange={(event) => setAuditQuery(event.target.value)} placeholder="Kullanıcı, kayıt veya işlem ara…" /></label><select value={auditEventFilter} onChange={(event) => setAuditEventFilter(event.target.value)}><option value="">Tüm işlemler</option>{eventNames.map((event) => <option key={event}>{event}</option>)}</select>{permissions.export ? <button type="button" onClick={exportAudit}><Download size={16} />Audit CSV indir</button> : null}</div></header><div className="wfx-security-note"><ScrollText size={18} />Audit kayıtları arayüzden değiştirilemez veya silinemez. Canlı kurulumda sunucu tarafında append-only saklama, zaman damgası, istek kimliği ve bütünlük hash zinciri ile korunmalıdır.</div><div className="wfx-table-wrap"><table className="wfx-table wfx-audit-table"><thead><tr><th>Zaman</th><th>İşlem</th><th>Kullanıcı</th><th>Kayıt</th><th>Detay</th></tr></thead><tbody>{filtered.length ? filtered.map((row) => <tr key={row.id}><td><strong>{new Date(row.at).toLocaleString(localeCode)}</strong><small>{row.id}</small></td><td><span className="wfx-status neutral">{row.event}</span></td><td>{row.actor || "system"}</td><td>{row.recordId || row.recordIds?.join(", ") || "—"}</td><td><details><summary>İşlem ayrıntısı</summary><pre>{JSON.stringify(row, null, 2)}</pre></details></td></tr>) : <tr><td colSpan="5">Filtreye uygun audit kaydı bulunamadı.</td></tr>}</tbody></table></div></section>;
  }

  function renderPicker() { return <section className="wfx-picker-launch"><div><span>Picker mobile experience</span><h2>Vardiya yoksa check-in yok.</h2><p>Mobil uygulama aktif vardiyayı sunucudan doğrular. Vardiyalarım, arşiv, mola, check-in/out ve itiraz akışı hazır.</p><button type="button" onClick={() => navigate("/workforce/app")}><Smartphone size={18} />Picker uygulamasını aç <ChevronRight size={17} /></button></div><div className="wfx-phone-mini"><div className="notch" /><small>Bugünkü vardiya</small><strong>{pickerShifts[0].warehouse}</strong><span>{pickerShifts[0].planned}</span><b>Atanmış vardiya doğrulandı</b><button type="button">Check-in yapabilir</button></div></section>; }

  function renderModal() {
    if (!modal) return null;
    const setValue = (patch) => setModal({ ...modal, value: { ...modal.value, ...patch } });
    if (modal.type === "shift") return <Modal title={modal.value.id ? "Vardiyayı düzenle" : "Yeni vardiya oluştur"} eyebrow="Vardiya planı" onClose={() => setModal(null)} onSave={saveShift} saveLabel={modal.value.id ? "Güncelle" : "Vardiyayı oluştur"} saveDisabled={!modal.value.personId || !modal.value.warehouseId}><div className="wfx-form-grid"><FormField label="Personel"><select value={modal.value.personId} onChange={(e) => setValue({ personId: e.target.value })}><option value="">Personel seç</option>{state.people.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</select></FormField><FormField label="Depo"><select value={modal.value.warehouseId} onChange={(e) => setValue({ warehouseId: e.target.value })}><option value="">Depo seç</option>{state.warehouses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField><FormField label="Tarih"><input type="date" value={modal.value.date} onChange={(e) => setValue({ date: e.target.value })} /></FormField><FormField label="Başlangıç"><input type="time" value={modal.value.start} onChange={(e) => setValue({ start: e.target.value })} /></FormField><FormField label="Bitiş"><input type="time" value={modal.value.end} onChange={(e) => setValue({ end: e.target.value })} /></FormField><FormField label="Planlanan mola (dk)"><input type="number" value={modal.value.breakMinutes} onChange={(e) => setValue({ breakMinutes: e.target.value })} /></FormField><FormField label="Görev"><input value={modal.value.role} onChange={(e) => setValue({ role: e.target.value })} /></FormField></div><div className="wfx-security-note"><ShieldCheck size={17} />Bu vardiya oluşmadan ilgili gün için check-in kabul edilmez.</div></Modal>;
    if (modal.type === "warehouse") return <Modal title={modal.value.id ? "Depoyu düzenle" : "Yeni depo ekle"} eyebrow="Depo ve geofence" onClose={() => setModal(null)} onSave={saveWarehouse} saveDisabled={!modal.value.name || !modal.value.code}><div className="wfx-form-grid"><FormField label="Depo adı"><input value={modal.value.name} onChange={(e) => setValue({ name: e.target.value })} /></FormField><FormField label="Depo kodu"><input value={modal.value.code} onChange={(e) => setValue({ code: e.target.value.toUpperCase() })} /></FormField><FormField label="Bölge"><input value={modal.value.region} onChange={(e) => setValue({ region: e.target.value })} /></FormField><FormField label="Enlem"><input type="number" step="any" value={modal.value.latitude} onChange={(e) => setValue({ latitude: e.target.value })} /></FormField><FormField label="Boylam"><input type="number" step="any" value={modal.value.longitude} onChange={(e) => setValue({ longitude: e.target.value })} /></FormField><FormField label="Geofence yarıçapı (m)"><input type="number" value={modal.value.radius} onChange={(e) => setValue({ radius: e.target.value })} /></FormField><FormField label="Maks. GPS sapması (m)"><input type="number" value={modal.value.accuracy} onChange={(e) => setValue({ accuracy: e.target.value })} /></FormField><FormField label="Doğrulama"><select value={modal.value.method} onChange={(e) => setValue({ method: e.target.value })}><option>Konum + cihaz</option><option>Konum + cihaz + QR</option><option>Yönetici onayı</option></select></FormField><FormField label="Durum"><select value={modal.value.status} onChange={(e) => setValue({ status: e.target.value })}><option>Aktif</option><option>Pasif</option></select></FormField><FormField label="QR opsiyonu"><select value={modal.value.qrEnabled ? "true" : "false"} onChange={(e) => setValue({ qrEnabled: e.target.value === "true" })}><option value="false">Kapalı</option><option value="true">Açık</option></select></FormField><FormField label="Adres" wide><textarea value={modal.value.address} onChange={(e) => setValue({ address: e.target.value })} /></FormField></div></Modal>;
    if (modal.type === "warehouseBulk") return <Modal title="Seçilen depoları düzenle" eyebrow={`${warehouseSelection.length} depo`} onClose={() => setModal(null)} onSave={saveBulkWarehouses} saveLabel="Toplu güncelle"><div className="wfx-security-note"><Building2 size={17} />Boş bıraktığınız alanlar değiştirilmez. Değişiklik tüm seçili depolara audit kaydıyla uygulanır.</div><div className="wfx-form-grid"><FormField label="Bölge"><input value={modal.value.region} placeholder="Değiştirme" onChange={(e) => setValue({ region: e.target.value })} /></FormField><FormField label="Geofence yarıçapı (m)"><input type="number" value={modal.value.radius} placeholder="Değiştirme" onChange={(e) => setValue({ radius: e.target.value })} /></FormField><FormField label="Maks. GPS sapması (m)"><input type="number" value={modal.value.accuracy} placeholder="Değiştirme" onChange={(e) => setValue({ accuracy: e.target.value })} /></FormField><FormField label="Doğrulama"><select value={modal.value.method} onChange={(e) => setValue({ method: e.target.value })}><option value="">Değiştirme</option><option>Konum + cihaz</option><option>Konum + cihaz + QR</option><option>Yönetici onayı</option></select></FormField><FormField label="Durum"><select value={modal.value.status} onChange={(e) => setValue({ status: e.target.value })}><option value="">Değiştirme</option><option>Aktif</option><option>Pasif</option></select></FormField><FormField label="QR opsiyonu"><select value={String(modal.value.qrEnabled)} onChange={(e) => setValue({ qrEnabled: e.target.value })}><option value="">Değiştirme</option><option value="false">Kapalı</option><option value="true">Açık</option></select></FormField></div></Modal>;
    if (modal.type === "rule") return <Modal title={modal.value.id ? "Kuralın yeni sürümünü oluştur" : "Yeni çalışma kuralı"} eyebrow="Sürümlü kural motoru" onClose={() => setModal(null)} onSave={saveRule} saveLabel="Hesap motoruna bağla" saveDisabled={!modal.value.title || !modal.value.engineKey || !modal.value.effectiveFrom}><div className="wfx-security-note"><Settings2 size={17} />Kural türü, yazdığınız değerin hangi hesap veya blokajı etkileyeceğini belirler. Kayıt sonrası eski sürüm silinmez, pasif audit sürümü olarak korunur.</div><div className="wfx-form-grid"><FormField label="Kural adı" wide><input value={modal.value.title} onChange={(e) => setValue({ title: e.target.value })} /></FormField><FormField label="Hesap motoru kural türü"><select value={modal.value.engineKey} disabled={Boolean(modal.value.id)} onChange={(e) => setValue({ engineKey: e.target.value })}><option value="dailyMax">Günlük azami net çalışma</option><option value="weeklyNormal">Haftalık normal çalışma</option><option value="annualOvertime">Yıllık fazla çalışma</option><option value="betweenShifts">Vardiyalar arası dinlenme</option><option value="breakShort">0–4 saat çalışma molası</option><option value="breakMedium">4–7,5 saat çalışma molası</option><option value="breakLong">7,5 saat üzeri çalışma molası</option><option value="earlyCheckIn">Erken giriş penceresi</option></select></FormField><FormField label="Değer (dakika)"><input type="number" min="0" value={modal.value.value} onChange={(e) => setValue({ value: e.target.value })} /></FormField><FormField label="Seviye"><select value={modal.value.level} onChange={(e) => setValue({ level: e.target.value })}><option>Sert blok</option><option>Bordro</option><option>Kritik</option><option>Otomatik</option><option>Operasyon</option></select></FormField><FormField label="Başlangıç tarihi"><input type="date" value={modal.value.effectiveFrom} onChange={(e) => setValue({ effectiveFrom: e.target.value })} /></FormField><FormField label="Açıklama" wide><textarea value={modal.value.note} onChange={(e) => setValue({ note: e.target.value })} /></FormField></div></Modal>;
    if (modal.type === "deviceReset") return <Modal title="Cihaz eşleşmesini sıfırla" eyebrow="Yüksek güvenlikli işlem" onClose={() => setModal(null)} onSave={resetDevice} saveLabel="Eski cihazı iptal et" saveDisabled={!modal.value.reason?.trim()}><div className="wfx-security-note"><ShieldCheck size={17} />{modal.value.person} için {modal.value.id} cihazı ve imzalama anahtarı iptal edilir. Eski telefon yeniden check-in/out yapamaz; yeni telefon tek kullanımlık kayıtla eşleştirilir.</div><div className="wfx-form-grid"><FormField label="Sıfırlama gerekçesi" wide><textarea value={modal.value.reason} onChange={(e) => setValue({ reason: e.target.value })} placeholder="Telefon değişimi, kayıp cihaz veya güvenlik olayı…" /></FormField></div></Modal>;
    if (modal.type === "holiday") return <Modal title={modal.value.id ? "Resmî tatili düzenle" : "Resmî tatil ekle"} eyebrow="Saat bazlı tatil" onClose={() => setModal(null)} onSave={saveHoliday}><div className="wfx-form-grid"><FormField label="Tatil adı" wide><input value={modal.value.name} onChange={(e) => setValue({ name: e.target.value })} /></FormField><FormField label="Başlangıç tarihi"><input type="date" value={modal.value.startDate} onChange={(e) => setValue({ startDate: e.target.value })} /></FormField><FormField label="Başlangıç saati"><input type="time" value={modal.value.startTime} onChange={(e) => setValue({ startTime: e.target.value })} /></FormField><FormField label="Bitiş tarihi"><input type="date" value={modal.value.endDate} onChange={(e) => setValue({ endDate: e.target.value })} /></FormField><FormField label="Bitiş saati"><input type="time" value={modal.value.endTime} onChange={(e) => setValue({ endTime: e.target.value })} /></FormField><FormField label="Kapsam"><input value={modal.value.scope} onChange={(e) => setValue({ scope: e.target.value })} /></FormField><FormField label="Durum"><select value={modal.value.active ? "true" : "false"} onChange={(e) => setValue({ active: e.target.value === "true" })}><option value="true">Aktif</option><option value="false">Pasif</option></select></FormField></div><div className="wfx-security-note"><Clock3 size={17} />Vardiyanın yalnız bu zaman aralığıyla kesişen fiili çalışma dakikaları resmî tatil sayılır.</div></Modal>;
    if (modal.type === "leave") return <Modal title={modal.value.id ? "İzni düzenle" : "Çalışana izin gir"} eyebrow="İzin yönetimi" onClose={() => setModal(null)} onSave={saveLeave}><div className="wfx-form-grid"><FormField label="Personel"><select value={modal.value.personId} onChange={(e) => setValue({ personId: e.target.value })}><option value="">Personel seç</option>{state.people.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField><FormField label="İzin türü"><select value={modal.value.typeId} onChange={(e) => setValue({ typeId: e.target.value })}>{state.leaveTypes.filter((item) => item.active).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField><FormField label="Tarih"><input type="date" value={modal.value.date} onChange={(e) => setValue({ date: e.target.value })} /></FormField><FormField label="Süre (dakika)"><input type="number" value={modal.value.minutes} onChange={(e) => setValue({ minutes: e.target.value })} /></FormField><FormField label="Açıklama" wide><textarea value={modal.value.note} onChange={(e) => setValue({ note: e.target.value })} /></FormField></div></Modal>;
    if (modal.type === "leaveType") return <Modal title={modal.value.id ? "İzin türünü düzenle" : "İzin türü ekle"} eyebrow="Puantaj etkisi" onClose={() => setModal(null)} onSave={saveLeaveType}><div className="wfx-form-grid"><FormField label="İzin adı"><input value={modal.value.name} onChange={(e) => setValue({ name: e.target.value })} /></FormField><FormField label="Bordro kodu"><input value={modal.value.code} onChange={(e) => setValue({ code: e.target.value })} /></FormField><FormField label="Ücret durumu"><select value={modal.value.paid ? "true" : "false"} onChange={(e) => setValue({ paid: e.target.value === "true" })}><option value="true">Ücretli</option><option value="false">Ücretsiz</option></select></FormField><FormField label="Planlanan süreyi karşılar mı?"><select value={modal.value.creditsPayroll ? "true" : "false"} onChange={(e) => setValue({ creditsPayroll: e.target.value === "true" })}><option value="true">Evet, eksik mesai üretmez</option><option value="false">Hayır, çalışmaya eklenmez</option></select></FormField><FormField label="Haftalık toplama girer mi?"><select value={modal.value.countsWeekly ? "true" : "false"} onChange={(e) => setValue({ countsWeekly: e.target.value === "true" })}><option value="false">Hayır</option><option value="true">Evet</option></select></FormField><FormField label="Yıllık bakiyeden düşer mi?"><select value={modal.value.deductsBalance ? "true" : "false"} onChange={(e) => setValue({ deductsBalance: e.target.value === "true" })}><option value="false">Hayır</option><option value="true">Evet</option></select></FormField><FormField label="Belge zorunlu mu?"><select value={modal.value.requiresDocument ? "true" : "false"} onChange={(e) => setValue({ requiresDocument: e.target.value === "true" })}><option value="false">Hayır</option><option value="true">Evet</option></select></FormField></div></Modal>;
    if (modal.type === "notificationSettings") return <Modal title="Vardiya bildirimlerini ayarla" eyebrow="Otomatik hatırlatmalar" onClose={() => setModal(null)} onSave={saveNotificationSettings}><div className="wfx-form-grid"><FormField label="Vardiya yayınlandı bildirimi"><select value={modal.value.shiftPublished ? "true" : "false"} onChange={(e) => setValue({ shiftPublished: e.target.value === "true" })}><option value="true">Açık</option><option value="false">Kapalı</option></select></FormField><FormField label="Check-in hatırlatması"><select value={modal.value.checkInReminder ? "true" : "false"} onChange={(e) => setValue({ checkInReminder: e.target.value === "true" })}><option value="true">Açık</option><option value="false">Kapalı</option></select></FormField><FormField label="Vardiyadan kaç dakika önce?"><input type="number" min="0" max="1440" value={modal.value.checkInReminderMinutes} onChange={(e) => setValue({ checkInReminderMinutes: e.target.value })} /></FormField><FormField label="Check-out hatırlatması"><select value={modal.value.checkOutReminder ? "true" : "false"} onChange={(e) => setValue({ checkOutReminder: e.target.value === "true" })}><option value="true">Açık</option><option value="false">Kapalı</option></select></FormField><FormField label="Vardiya bitiminden kaç dakika önce?"><input type="number" min="0" max="1440" value={modal.value.checkOutReminderMinutes} onChange={(e) => setValue({ checkOutReminderMinutes: e.target.value })} /></FormField></div><div className="wfx-security-note"><Bell size={17} />Bildirimler vardiya yayınlandığında planlanır; saat değişirse yeni plana göre yeniden oluşturulur.</div></Modal>;
    if (modal.type === "announcement") return <Modal title="Yeni duyuru yayınla" eyebrow="Hedefli mobil bildirim" onClose={() => setModal(null)} onSave={saveAnnouncement} saveLabel="Duyuruyu yayınla" saveDisabled={!modal.value.title?.trim() || !modal.value.message?.trim()}><div className="wfx-form-grid"><FormField label="Duyuru başlığı" wide><input value={modal.value.title} onChange={(e) => setValue({ title: e.target.value })} placeholder="Örn. Vardiya planı güncellendi" /></FormField><FormField label="Hedef"><select value={modal.value.targetType} onChange={(e) => setValue({ targetType: e.target.value, targetValue: "" })}><option value="all">Tüm kullanıcılar</option><option value="warehouse">Tek depo</option><option value="person">Tek personel</option></select></FormField>{modal.value.targetType === "warehouse" ? <FormField label="Depo"><select value={modal.value.targetValue} onChange={(e) => setValue({ targetValue: e.target.value })}><option value="">Depo seç</option>{state.warehouses.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}</select></FormField> : null}{modal.value.targetType === "person" ? <FormField label="Personel"><select value={modal.value.targetValue} onChange={(e) => setValue({ targetValue: e.target.value })}><option value="">Personel seç</option>{state.people.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.id}</option>)}</select></FormField> : null}<FormField label="Yayın zamanı"><input type="datetime-local" value={modal.value.publishAt} onChange={(e) => setValue({ publishAt: e.target.value })} /></FormField><FormField label="Duyuru metni" wide><textarea value={modal.value.message} onChange={(e) => setValue({ message: e.target.value })} placeholder="Picker uygulamasında gösterilecek metin…" /></FormField></div></Modal>;
    if (modal.type === "managerTask") return <Modal title={modal.value.kind === "roster" ? "11 saat görevini düzelt" : modal.value.kind === "leave" ? "İzin talebini incele" : "Picker talebini incele"} eyebrow="Yönetici görevi" onClose={() => setModal(null)} onSave={saveManagerTask} saveLabel="Kararı kaydet" saveDisabled={!modal.value.managerNote?.trim()}><div className="wfx-security-note"><ShieldCheck size={17} />Ham kayıt korunur; karar, önceki/sonraki değer ve gerekçe audit log'a yazılır.</div><div className="wfx-form-grid">{modal.value.kind === "roster" ? <><FormField label="Düzeltilecek kayıt"><input value={`${modal.value.recordCount || 0} kayıt · ${modal.value.warehouse}`} disabled /></FormField><FormField label="Hesaba esas süre (dakika)"><input type="number" min="0" value={modal.value.targetMinutes} onChange={(e) => setValue({ targetMinutes: e.target.value })} /></FormField></> : modal.value.kind === "leave" ? <><FormField label="Karar"><select value={modal.value.decision} onChange={(e) => setValue({ decision: e.target.value })}><option>Onaylandı</option><option>Reddedildi</option></select></FormField><FormField label="İzin türü"><input value={modal.value.typeName || ""} disabled /></FormField><FormField label="Tarih aralığı"><input value={`${modal.value.startDate} – ${modal.value.endDate}`} disabled /></FormField></> : <><FormField label="Karar"><select value={modal.value.decision} onChange={(e) => setValue({ decision: e.target.value })}><option>Onaylandı</option><option>Reddedildi</option></select></FormField><FormField label="Talep edilen giriş"><input type="time" value={modal.value.requestedCheckIn || ""} onChange={(e) => setValue({ requestedCheckIn: e.target.value })} /></FormField><FormField label="Talep edilen çıkış"><input type="time" value={modal.value.requestedCheckOut || ""} onChange={(e) => setValue({ requestedCheckOut: e.target.value })} /></FormField></>}<FormField label="Yönetici açıklaması" wide><textarea value={modal.value.managerNote} onChange={(e) => setValue({ managerNote: e.target.value })} placeholder="Karar için kısa bir açıklama yazın…" /></FormField></div></Modal>;
    if (modal.type === "correction") return <Modal title="Puantajı manuel düzelt" eyebrow="Yetkili işlem" onClose={() => setModal(null)} onSave={saveCorrection} saveDisabled={!modal.value.reason?.trim()}><div className="wfx-security-note"><ShieldCheck size={17} />Ham mobil kayıt silinmez; öncesi/sonrası ve gerekçe audit kaydında tutulur.</div><div className="wfx-form-grid"><FormField label="Check-in"><input type="time" value={modal.value.checkIn === "—" ? "" : modal.value.checkIn} onChange={(e) => setValue({ checkIn: e.target.value })} /></FormField><FormField label="Check-out"><input type="time" value={modal.value.checkOut === "—" ? "" : modal.value.checkOut} onChange={(e) => setValue({ checkOut: e.target.value })} /></FormField><FormField label="Mola başlangıcı"><input type="time" value={modal.value.breakStart} onChange={(e) => setValue({ breakStart: e.target.value })} /></FormField><FormField label="Mola bitişi"><input type="time" value={modal.value.breakEnd} onChange={(e) => setValue({ breakEnd: e.target.value })} /></FormField><FormField label="Düzeltme gerekçesi" wide><textarea value={modal.value.reason} onChange={(e) => setValue({ reason: e.target.value })} placeholder="Kısa bir gerekçe yazın…" /></FormField></div></Modal>;
    return null;
  }

  const title = tabs.find((tab) => tab.id === activeTab)?.label || "Workforce";
  return <main ref={rootRef} dir={dir} className={`wfx-page wfx-theme-${theme}`}><aside className={`wfx-sidebar ${sidebarOpen ? "open" : ""}`}><div className="wfx-brand"><div>W</div><span><strong>Workforce</strong><small>OPEX Control Center</small></span></div><nav>{visibleTabs.map((tab) => { const Icon = tab.icon; return <button type="button" key={tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => { setActiveTab(tab.id); setSidebarOpen(false); }}><Icon size={18} />{tab.label}{activeTab === tab.id ? <ChevronRight size={15} /> : null}</button>; })}</nav><div className="wfx-sidebar-foot"><ShieldCheck size={17} /><span><strong>Yetki kontrollü</strong><small>{permissions.manualCorrection ? "Manuel düzeltme açık" : "Müdür operasyon modu"}</small></span></div></aside>{sidebarOpen ? <button className="wfx-sidebar-overlay" onClick={() => setSidebarOpen(false)} /> : null}<section className="wfx-content"><header className="wfx-topbar"><div className="wfx-title-row"><button type="button" className="wfx-mobile-menu" onClick={() => setSidebarOpen(true)}><Menu size={19} /></button><button type="button" className="wfx-back" onClick={() => navigate("/")}><ArrowLeft size={17} />Control Center</button><div><span>OPEX Workforce</span><h1>{title}</h1></div></div><div className="wfx-topbar-actions"><label className="wfx-language-control"><Languages size={16} /><span>Dil</span><select aria-label="Dil" value={locale} onChange={(event) => setLocale(event.target.value)}><option value="tr">Türkçe</option><option value="en">English</option><option value="de">Deutsch</option><option value="ar">العربية</option></select></label><button type="button" className="wfx-theme-toggle" title={theme === "dark" ? "Açık tema" : "Koyu tema"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}<span>{theme === "dark" ? "Açık tema" : "Koyu tema"}</span></button><div className="wfx-user"><div>{(user?.name || user?.email || "U")[0]}</div><span><strong>{user?.name || user?.email}</strong><small>{superAdmin ? "Super Admin" : "Yetkili Kullanıcı"}</small></span></div></div></header><div className="wfx-body">{activeTab === "dashboard" && renderDashboard()}{activeTab === "attendance" && renderAttendance()}{activeTab === "timesheet" && renderTimesheet()}{activeTab === "periodClose" && <WorkforcePeriodClose state={state} updateState={updateState} permissions={permissions} user={user} setNotice={setNotice} />}{activeTab === "users" && <WorkforcePeriodClose state={state} updateState={updateState} permissions={permissions} user={user} setNotice={setNotice} initialSection="employees" standalone />}{activeTab === "opexLab" && <WorkforceOpexLab state={state} updateState={updateState} permissions={permissions} user={user} setNotice={setNotice} />}{activeTab === "shifts" && renderShifts()}{activeTab === "approvals" && renderApprovals()}{activeTab === "managerTasks" && renderManagerTasks()}{activeTab === "communications" && renderCommunications()}{activeTab === "experience" && <WorkforceExperienceAdmin />}{activeTab === "systemConfig" && renderSystemConfig()}{activeTab === "leaves" && renderLeaves()}{activeTab === "warehouses" && renderWarehouses()}{activeTab === "rules" && renderRules()}{activeTab === "devices" && renderDevices()}{activeTab === "audit" && renderAudit()}{activeTab === "picker" && renderPicker()}</div></section>{renderModal()}{notice ? <div className="wfx-toast"><CheckCircle2 size={18} />{notice}</div> : null}</main>;
}
