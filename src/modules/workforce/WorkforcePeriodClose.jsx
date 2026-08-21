import React, { useEffect, useMemo, useRef, useState } from "react";
import * as XLSX from "xlsx";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Download,
  FileSpreadsheet,
  Fingerprint,
  FlaskConical,
  KeyRound,
  Link2,
  LockKeyhole,
  Mail,
  PencilLine,
  Printer,
  Save,
  ShieldCheck,
  Trash2,
  Upload,
  UserPlus,
  UserRoundCog,
  UsersRound,
  X,
} from "lucide-react";

import { buildCumulativePayroll, summarizeCumulativePayroll, toIsoDate, toTrDate } from "./workforceEngine.js";
import { formatMinutes } from "./workforceData.js";
import { maskNationalId, parseAttendanceFile, parseEmployeeFile, parseEmploymentLifecycleFile, parseRosterFile, parseRosterIdentityFile, parseTimeOffFile } from "./workforceImporters.js";
import { buildRosterIdentityMappings, reconcileRosterRows, resolveWorkforcePerson } from "./workforceIdentity.js";
import { clearRosterRows, loadRosterRows, saveRosterRows } from "./workforceRosterStore.js";
import { importAttendanceRemote, importEmploymentLifecycleRemote, importLeavesRemote, upsertPeopleRemote } from "./workforceApi.js";

function csvEscape(value) { return `"${String(value ?? "").replaceAll('"', '""')}"`; }
function downloadCsv(filename, headers, rows) {
  const content = [headers, ...rows].map((row) => row.map(csvEscape).join(";")).join("\n");
  const url = URL.createObjectURL(new Blob([`\ufeff${content}`], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}
function downloadXlsx(filename, sheetName, headers, rows, decimalHourColumns = []) {
  const sheet = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  sheet["!freeze"] = { xSplit: 0, ySplit: 1 };
  sheet["!autofilter"] = { ref: sheet["!ref"] };
  sheet["!cols"] = headers.map((header, index) => ({ wch: Math.min(38, Math.max(String(header).length + 2, ...rows.slice(0, 250).map((row) => String(row[index] ?? "").length + 2))) }));
  decimalHourColumns.forEach((columnIndex) => rows.forEach((_, rowIndex) => {
    const cell = sheet[XLSX.utils.encode_cell({ r: rowIndex + 1, c: columnIndex })];
    if (cell && typeof cell.v === "number") cell.z = "0.##";
  }));
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, sheet, sheetName);
  XLSX.writeFile(workbook, filename);
}
function decimalHours(minutes) { return Number((Number(minutes || 0) / 60).toFixed(2)); }
function inPeriod(date, period) { return date >= period.startDate && date <= period.endDate; }
const MANAGER_ROLE_NAMES = new Set(["WAREHOUSE MANAGER", "STORE MANAGER", "DEPO MÜDÜRÜ", "MAĞAZA MÜDÜRÜ", "RIDER CAPTAIN"]);
function normalizeRole(value = "") { return String(value).trim().toLocaleUpperCase("tr-TR").replaceAll(/[_-]+/g, " ").replaceAll(/\s+/g, " "); }
function isManager(row) { return MANAGER_ROLE_NAMES.has(normalizeRole(row.title || row.role)); }
function clockMinutes(value) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
}
function rosterNightMinutes(row, effective) {
  const start = clockMinutes(row.start); let end = clockMinutes(row.end);
  if (start == null || end == null || effective <= 0) return 0;
  if (end <= start) end += 1440;
  const overlap = (from, to) => Math.max(0, Math.min(end, to) - Math.max(start, from));
  const rawNight = overlap(0, 360) + overlap(1200, 1800);
  const gross = Math.max(1, Number(row.grossMinutes) || end - start);
  return Math.min(effective, Math.round(rawNight * Math.min(1, effective / gross)));
}

const SECTION_TABS = [
  { id: "close", label: "Dönem Kapanışı" },
  { id: "employees", label: "Personel Ana Veri" },
  { id: "timeoff", label: "Toplu İzin" },
];

export function WorkforcePeriodClose({ state, updateState, permissions, user, setNotice, initialSection = "close", standalone = false }) {
  const [section, setSection] = useState(initialSection);
  const [period, setPeriod] = useState({ startDate: "2026-06-01", endDate: "2026-07-20", warehouse: "", personId: "" });
  const [selectedEmployees, setSelectedEmployees] = useState([]);
  const [employeeQuery, setEmployeeQuery] = useState("");
  const [editingPerson, setEditingPerson] = useState(null);
  const employeeRef = useRef(null);
  const employmentRef = useRef(null);
  const employeeRosterIdentityRef = useRef(null);
  const timeOffRef = useRef(null);
  const attendanceRef = useRef(null);
  const rows = useMemo(() => buildCumulativePayroll(state, period), [state, period]);
  const totals = useMemo(() => summarizeCumulativePayroll(rows), [rows]);
  const accountsByPerson = useMemo(() => new Map((state.userAccounts || []).map((account) => [String(account.personId), account])), [state.userAccounts]);
  const rosterIdsByPerson = useMemo(() => {
    const mapped = new Map();
    Object.values(state.rosterIdentityMap || {}).filter((record) => record.status === "Eşleşti" && record.hrPersonId).forEach((record) => {
      const personId = String(record.hrPersonId);
      if (!mapped.has(personId)) mapped.set(personId, []);
      mapped.get(personId).push(String(record.rosterPersonId));
    });
    return mapped;
  }, [state.rosterIdentityMap]);
  const visiblePeople = useMemo(() => state.people.filter((person) => [person.id, ...(person.rosterIds || []), person.name, person.email, person.warehouse].join(" ").toLocaleLowerCase("tr-TR").includes(employeeQuery.toLocaleLowerCase("tr-TR"))), [state.people, employeeQuery]);

  function displayNationalId(value) { return permissions.fullNationalId ? (value || "—") : maskNationalId(value); }

  async function importEmployees(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const imported = await parseEmployeeFile(file);
      const existingById = new Map(state.people.map((person) => [String(person.id), person]));
      const existingByTc = new Map();
      state.people.forEach((person) => {
        const tc = String(person.nationalId || "").replace(/\D/g, "");
        if (!tc || existingByTc.has(tc)) existingByTc.set(tc, null); else existingByTc.set(tc, person);
      });
      const prepared = imported.map((person) => {
        const tcMatch = person.nationalId?.length === 11 ? existingByTc.get(person.nationalId) : null;
        const existing = tcMatch || existingById.get(String(person.id));
        return {
          ...person,
          id: String(existing?.id || person.id || ""),
          rosterIds: [...new Set([...(existing?.rosterIds || []), ...(person.rosterIds || [])])],
          sourceEmployeeId: person.id && existing && String(person.id) !== String(existing.id) ? String(person.id) : existing?.sourceEmployeeId,
        };
      }).filter((person) => person.id);
      const summary = prepared.reduce((result, person) => {
        const existing = existingById.get(String(person.id));
        if (existing) result.updated += 1; else result.created += 1;
        if (person.terminationDate && !existing?.terminationDate) result.terminated += 1;
        if (person.warehouse && !state.warehouses.some((warehouse) => warehouse.name === person.warehouse)) result.unmatchedWarehouses.add(person.warehouse);
        return result;
      }, { created: 0, updated: 0, terminated: 0, unmatchedWarehouses: new Set() });
      const persistable = prepared.filter((person) => person.nationalId?.length === 11);
      const remoteSummary = persistable.length ? await upsertPeopleRemote(persistable, ({ processed, total }) => {
        setNotice(`Personel ana verisi yükleniyor: ${processed.toLocaleString("tr-TR")} / ${total.toLocaleString("tr-TR")}`);
      }) : { rosterConflicts: [] };
      updateState("people", (current) => {
        const byId = new Map(current.map((person) => [person.id, person]));
        prepared.forEach((person) => {
          const existing = byId.get(person.id);
          const next = { active: true, role: "Picker", ...(existing || {}), ...person, updatedAt: new Date().toISOString(), updatedBy: user?.email || "employee-import" };
          if (next.terminationDate) next.active = false;
          byId.set(person.id, next);
        });
        return [...byId.values()];
      }, { event: "EMPLOYEE_MASTER_UPSERTED", count: prepared.length, created: summary.created, updated: summary.updated, terminated: summary.terminated, unmatchedWarehouses: [...summary.unmatchedWarehouses], file: file.name, identityPriority: "TC > Employee ID" });
      updateState("employeeImport", { file: file.name, importedAt: new Date().toISOString(), importedBy: user?.email, total: prepared.length, created: summary.created, updated: summary.updated, terminated: summary.terminated, unmatchedWarehouses: [...summary.unmatchedWarehouses] }, { event: "EMPLOYEE_IMPORT_SUMMARY_SAVED", file: file.name });
      updateState("userAccounts", (current = []) => {
        const byPerson = new Map(current.map((account) => [String(account.personId), account]));
        prepared.forEach((person) => {
          const existing = byPerson.get(String(person.id));
          if (!existing && !person.createUser) return;
          byPerson.set(String(person.id), {
            ...(existing || {}), personId: String(person.id), email: person.email || existing?.email || "",
            status: person.terminationDate ? "Erişim kapalı" : existing?.status || "Davetiye gönderildi",
            createdAt: existing?.createdAt || new Date().toISOString(), updatedAt: new Date().toISOString(),
          });
        });
        return [...byPerson.values()];
      }, { event: "USER_ACCOUNTS_SYNCED_FROM_EMPLOYEE_IMPORT", count: prepared.filter((person) => person.createUser || person.terminationDate).length });
      const conflictCount = remoteSummary.rosterConflicts?.length || 0;
      setNotice(`${prepared.length} kişi TC öncelikli işlendi: ${summary.created} yeni, ${summary.updated} güncelleme, ${summary.terminated} yeni çıkış kaydı${conflictCount ? `; ${conflictCount} çakışan Roster ID bağlanmadı` : ""}.`);
    } catch (error) { setNotice(`Personel dosyası okunamadı: ${error.message}`); }
  }

  function downloadEmployeeTemplate() {
    downloadXlsx("workforce_personel_ana_veri_sablonu.xlsx", "Personel Ana Veri", ["Employee ID", "Roster ID", "TC", "Ad Soyad", "İşe Giriş Tarihi", "İşten Çıkış Tarihi", "Actual Warehouse", "İK Depo Kodu", "Unvan", "E-posta", "Telefon", "Kullanıcı Hesabı"], [["27057", "32137", "10009717724", "Murat Işılı", "2025-04-01", "", "Fulya (İstanbul)", "287", "Picker", "picker@company.com", "", "Evet"]]);
  }

  function downloadEmploymentTemplate() {
    downloadXlsx("workforce_ise_giris_cikis_sablonu.xlsx", "İşe Giriş Çıkış", ["Employee Number", "TC Kimlik Numarası", "Ad Soyad", "İşe Giriş Tarihi", "İşten Çıkış Tarihi"], [["27057", "10009717724", "Murat Işılı", "2025-04-01", ""]]);
  }

  async function importEmploymentLifecycle(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const imported = await parseEmploymentLifecycleFile(file);
      const bootstrap = [...new Map(imported.filter((row) => row.personId && row.nationalId?.length === 11 && row.personName && !resolveWorkforcePerson({ sourcePersonId: row.personId, nationalId: row.nationalId }, state.people, state.rosterIdentityMap || {}).person).map((row) => [row.nationalId, { id: String(row.personId), name: row.personName, nationalId: row.nationalId, role: "Çalışan", warehouse: "", hireDate: row.hireDate, terminationDate: row.terminationDate, active: !row.terminationDate }])).values()];
      if (bootstrap.length) await upsertPeopleRemote(bootstrap);
      const peopleForResolution = [...state.people, ...bootstrap];
      const resolved = imported.map((row) => ({ row, result: resolveWorkforcePerson({ sourcePersonId: row.personId, nationalId: row.nationalId }, peopleForResolution, state.rosterIdentityMap || {}) }));
      const matched = resolved.filter((item) => item.result.person);
      const unmatched = resolved.filter((item) => !item.result.person);
      if (matched.length) await importEmploymentLifecycleRemote(matched.map((item) => ({ personId: item.result.person.id, hireDate: item.row.hireDate, terminationDate: item.row.terminationDate, identityMethod: item.result.method })), file.name);
      updateState("people", (current) => {
        const byId = new Map(current.map((person) => [String(person.id), person]));
        bootstrap.forEach((person) => { if (!byId.has(String(person.id))) byId.set(String(person.id), person); });
        return [...byId.values()].map((person) => {
        const match = matched.find((item) => String(item.result.person.id) === String(person.id));
        if (!match) return person;
        const next = { ...person, ...(match.row.hireDate ? { hireDate: match.row.hireDate } : {}), ...(match.row.terminationDate ? { terminationDate: match.row.terminationDate, active: false } : {}), updatedAt: new Date().toISOString(), updatedBy: user?.email || "employment-import" };
        return next;
        });
      }, { event: "EMPLOYMENT_LIFECYCLE_IMPORTED", file: file.name, matched: matched.length, unmatched: unmatched.length, bootstrapped: bootstrap.length, identityPriority: "TC > Employee ID" });
      const terminatedIds = new Set(matched.filter((item) => item.row.terminationDate).map((item) => String(item.result.person.id)));
      if (terminatedIds.size) updateState("userAccounts", (current = []) => current.map((account) => terminatedIds.has(String(account.personId)) ? { ...account, status: "Erişim kapalı", updatedAt: new Date().toISOString() } : account), { event: "EMPLOYEE_ACCESS_CLOSED_FROM_LIFECYCLE_IMPORT", personIds: [...terminatedIds] });
      updateState("employmentLifecycleImport", { file: file.name, importedAt: new Date().toISOString(), importedBy: user?.email, total: imported.length, matched: matched.length, unmatched: unmatched.length }, { event: "EMPLOYMENT_LIFECYCLE_IMPORT_SUMMARY_SAVED", file: file.name });
      setNotice(`${matched.length} kişinin işe giriş/çıkış tarihi TC öncelikli güncellendi; ${unmatched.length} kayıt eşleşmedi.`);
    } catch (error) { setNotice(`İşe giriş/çıkış dosyası okunamadı: ${error.message}`); }
  }

  function downloadEmployeeRosterIdentityTemplate() {
    downloadXlsx("toplu_roster_id_tc_eslestirme_sablonu.xlsx", "Roster ID Eşleştirme", ["rider_id", "rider_name", "TCK", "contract_name", "IsActive", "phone_num", "email"], [["32137", "Adem Önder", "27473308464", "IN_HOUSE", "1", "+905551112233", "adem.onder@company.com"]]);
  }

  async function importEmployeeRosterIdentities(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const identityRows = await parseRosterIdentityFile(file);
      const result = buildRosterIdentityMappings(identityRows, state.people, state.rosterIdentityMap || {});
      updateState("rosterIdentityMap", result.mappings, { event: "BULK_ROSTER_IDS_RECONCILED_FROM_EMPLOYEE_MASTER", file: file.name, ...result.summary });
      updateState("rosterIdentityImport", { ...result.summary, file: file.name, source: "Personel Ana Veri / rider_id-TCK", importedAt: new Date().toISOString(), importedBy: user?.email }, { event: "ROSTER_IDENTITY_IMPORT_SUMMARY_SAVED", file: file.name });
      setNotice(`${result.summary.matched} rider_id TC üzerinden personele bağlandı; ${result.summary.unmatched} kayıt eşleşmedi${result.summary.ambiguous ? `, ${result.summary.ambiguous} kayıt belirsiz` : ""}.`);
    } catch (error) {
      setNotice(`Toplu Roster ID dosyası okunamadı: ${error.message}`);
    }
  }

  function createUserAccounts(personIds) {
    const selected = state.people.filter((person) => personIds.includes(String(person.id)));
    const eligible = selected.filter((person) => person.email && !person.terminationDate);
    updateState("userAccounts", (current = []) => {
      const byPerson = new Map(current.map((account) => [String(account.personId), account]));
      eligible.forEach((person) => {
        const existing = byPerson.get(String(person.id));
        byPerson.set(String(person.id), { ...(existing || {}), personId: String(person.id), email: person.email, status: existing?.status === "Aktif" ? "Aktif" : "Davetiye gönderildi", createdAt: existing?.createdAt || new Date().toISOString(), updatedAt: new Date().toISOString(), invitedBy: user?.email });
      });
      return [...byPerson.values()];
    }, { event: "PICKER_USER_ACCOUNTS_CREATED", personIds: eligible.map((person) => person.id) });
    setSelectedEmployees([]);
    setNotice(`${eligible.length} uygulama kullanıcısı oluşturuldu/güncellendi${selected.length > eligible.length ? `; ${selected.length - eligible.length} kişi e-posta veya aktif çalışma bilgisi olmadığı için atlandı` : ""}.`);
  }

  function createPasswordResetLinks(personIds) {
    const selected = state.people.filter((person) => personIds.includes(String(person.id)) && accountsByPerson.has(String(person.id)) && person.email && !person.terminationDate);
    const createdAt = new Date().toISOString();
    const links = selected.map((person) => ({ personId: String(person.id), name: person.name, email: person.email, url: `${window.location.origin}/password-reset?token=${window.crypto?.randomUUID?.() || `${Date.now()}-${person.id}`}` }));
    updateState("userAccounts", (current = []) => current.map((account) => {
      const link = links.find((item) => item.personId === String(account.personId));
      return link ? { ...account, resetUrl: link.url, resetRequestedAt: createdAt, resetRequestedBy: user?.email } : account;
    }), { event: "PASSWORD_RESET_LINKS_CREATED", personIds: links.map((item) => item.personId) });
    if (links.length === 1 && navigator.clipboard) navigator.clipboard.writeText(links[0].url).catch(() => {});
    if (links.length > 1) downloadCsv(`workforce_sifre_sifirlama_linkleri_${createdAt.slice(0, 10)}.csv`, ["Employee ID", "Ad Soyad", "E-posta", "Şifre Sıfırlama Linki"], links.map((item) => [item.personId, item.name, item.email, item.url]));
    setNotice(links.length === 1 ? "Şifre sıfırlama bağlantısı oluşturuldu ve panoya kopyalandı." : `${links.length} şifre sıfırlama bağlantısı güvenli aktarım için CSV olarak indirildi.`);
  }

  function savePerson() {
    if (!editingPerson?.id || !editingPerson?.name?.trim()) return;
    const warehouse = state.warehouses.find((item) => item.name === editingPerson.warehouse);
    const record = { ...editingPerson, warehouseCode: editingPerson.warehouseCode || warehouse?.code || "", active: !editingPerson.terminationDate, updatedAt: new Date().toISOString(), updatedBy: user?.email };
    updateState("people", (current) => current.map((person) => String(person.id) === String(record.id) ? record : person), { event: "EMPLOYEE_MASTER_UPDATED", personId: record.id, changedBy: user?.email });
    if (record.terminationDate) updateState("userAccounts", (current = []) => current.map((account) => String(account.personId) === String(record.id) ? { ...account, status: "Erişim kapalı", updatedAt: new Date().toISOString() } : account), { event: "EMPLOYEE_ACCESS_CLOSED", personId: record.id });
    setEditingPerson(null); setNotice("Personel ana verisi ve erişim yaşam döngüsü güncellendi.");
  }

  async function importTimeOff(event) {
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
      const accepted = [];
      const skipped = [];
      const unmatched = [];
      imported.rows.forEach((leave) => {
        const resolved = resolveWorkforcePerson(leave, peopleForResolution, state.rosterIdentityMap || {});
        if (!resolved.person) { unmatched.push({ ...leave, reason: resolved.reason }); return; }
        const sourceKey = `${resolved.person.id}|${leave.date}`;
        if (existingKeys.has(sourceKey)) { skipped.push(leave); return; }
        existingKeys.add(sourceKey);
        accepted.push({ ...leave, personId: String(resolved.person.id), sourcePersonId: leave.sourcePersonId, sourceKey, identityMethod: resolved.method, personName: resolved.person.name, warehouse: resolved.person.warehouse || "Eşleşmeyen personel", enteredBy: user?.email || "time-off-import", enteredAt: new Date().toISOString() });
      });
      const customTypes = [...new Map(accepted.filter((leave) => !state.leaveTypes.some((type) => type.id === leave.typeId)).map((leave) => [leave.typeId, {
        id: leave.typeId, code: leave.typeId.toLocaleUpperCase("tr-TR"), name: leave.category, paid: false, creditsPayroll: false,
        excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true,
      }])).values()];
      if (accepted.length) await importLeavesRemote(accepted, file.name);
      if (customTypes.length) updateState("leaveTypes", (current) => [...current, ...customTypes], { event: "LEAVE_TYPES_AUTO_CREATED", count: customTypes.length });
      if (accepted.length) updateState("leaves", (current) => [...current, ...accepted], { event: "TIME_OFF_IMPORTED", file: file.name, sourceRows: imported.sourceCount, accepted: accepted.length, skipped: skipped.length, unmatched: unmatched.length, identityPriority: "TC > Employee ID > Roster ID" });
      setNotice(`${accepted.length} izin günü TC öncelikli eklendi; ${bootstrap.length} kişi Time Off kimliğiyle oluşturuldu; ${skipped.length} kişi/gün mükerrer olduğu için atlandı; ${unmatched.length} kayıt eşleşmedi.`);
    } catch (error) { setNotice(`Time Off dosyası okunamadı: ${error.message}`); }
  }

  async function importAttendance(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const imported = await parseAttendanceFile(file);
      const existingByKey = new Map(state.attendance.map((row) => [`${row.personId}|${toIsoDate(row.date)}`, row]));
      const inserts = [];
      const replacements = new Map();
      let unmatched = 0;
      let protectedRows = 0;
      imported.rows.forEach((row) => {
        const resolved = resolveWorkforcePerson(row, state.people, state.rosterIdentityMap || {});
        if (!resolved.person) { unmatched += 1; return; }
        const key = `${resolved.person.id}|${row.date}`;
        const existing = existingByKey.get(key);
        if (existing && !String(existing.source || "").includes("Dosya")) { protectedRows += 1; return; }
        const shift = state.shifts.find((item) => String(item.personId) === String(resolved.person.id) && item.date === row.date && item.status !== "İptal");
        const record = {
          id: existing?.id || `ATT-FILE-${resolved.person.id}-${row.date}`,
          shiftId: shift?.id || "",
          personId: String(resolved.person.id), name: resolved.person.name, role: resolved.person.role || row.title || "Picker",
          warehouse: resolved.person.warehouse || row.warehouse, date: toTrDate(row.date),
          planned: shift ? `${shift.start}–${shift.end}` : "Dosyadan",
          checkIn: row.checkIn || "—", checkOut: row.checkOut || "—", breaks: [], breakMinutes: row.breakMinutes,
          netMinutes: row.netMinutes, expectedMinutes: shift?.expectedMinutes ?? row.expectedMinutes,
          status: row.errorStatus || (row.varianceMinutes > 0 ? "Fazla mesai" : row.varianceMinutes < 0 ? "Eksik çalışma" : "Tamamlandı"),
          approval: "Onay bekliyor", location: "Dosya kaydı", device: "—", source: `Puantaj Dosyası · ${file.name}`,
          nationalId: row.nationalId, sourcePersonId: row.sourcePersonId, identityMethod: resolved.method, importedAt: new Date().toISOString(), importedBy: user?.email,
        };
        if (existing) replacements.set(existing.id, record); else inserts.push(record);
      });
      const changedRows = [...replacements.values(), ...inserts];
      if (changedRows.length) await importAttendanceRemote(changedRows, file.name);
      if (changedRows.length) updateState("attendance", (current) => [...current.map((row) => replacements.get(row.id) || row), ...inserts], { event: "ATTENDANCE_FILE_IMPORTED", file: file.name, inserted: inserts.length, updated: replacements.size, protectedRows, unmatched, identityPriority: "TC > Employee ID > Roster ID" });
      updateState("attendanceImport", { file: file.name, importedAt: new Date().toISOString(), importedBy: user?.email, sourceRows: imported.sourceCount, inserted: inserts.length, updated: replacements.size, protectedRows, unmatched }, { event: "ATTENDANCE_IMPORT_SUMMARY_SAVED", file: file.name });
      setNotice(`${inserts.length} giriş/çıkış kaydı eklendi, ${replacements.size} önceki dosya kaydı güncellendi; ${protectedRows} mobil/sistem kaydı korundu; ${unmatched} kayıt eşleşmedi.`);
    } catch (error) { setNotice(`Giriş/çıkış dosyası okunamadı: ${error.message}`); }
  }

  function exportPayroll() {
    downloadCsv(`puantaj_kapanis_${period.startDate}_${period.endDate}.csv`, ["Employee ID", "Ad Soyad", "TC", "Depo", "İşe Giriş", "Çıkış", "Plan (saat)", "Fiili (saat)", "Normal (saat)", "Resmi Tatil (saat)", "Gece (saat)", "Fazla Mesai (saat)", "Eksik (saat)", "İzin (saat)"], rows.map((row) => [row.personId, row.name, displayNationalId(row.nationalId), row.warehouse, row.hireDate, row.terminationDate, decimalHours(row.expectedMinutes), decimalHours(row.workedMinutes), decimalHours(row.normalMinutes), decimalHours(row.holidayMinutes), decimalHours(row.nightMinutes), decimalHours(row.overtimeMinutes), decimalHours(row.missingMinutes), decimalHours(row.leaveMinutes)]));
  }

  function saveCloseRun() {
    const record = { id: `CLOSE-${Date.now()}`, ...period, people: rows.length, totals, createdAt: new Date().toISOString(), createdBy: user?.email || "unknown", status: "Taslak" };
    updateState("periodCloseRuns", (current) => [record, ...current], { event: "PAYROLL_CLOSE_DRAFT_CREATED", recordId: record.id });
    setNotice("Dönem kapanışı taslak olarak kaydedildi; ham kayıtlar değişmedi.");
  }

  return <section className="wfx-panel wfx-period-close">
    <header className="wfx-panel-head responsive"><div><span>{standalone ? "Kullanıcı ve erişim yönetimi" : "İK ve bordro"}</span><h2>{standalone ? "Picker personel ve uygulama kullanıcıları" : "Kümülatif dönem yönetimi"}</h2><p>{standalone ? "Employee ID tekil anahtarıyla personel ana verisini, uygulama hesabını ve erişim yaşam döngüsünü birlikte yönetin." : "Beklenen süre yalnız atanmış vardiyalardan ve çalışanın işe giriş-çıkış aralığından hesaplanır; boş güne otomatik saat yazılmaz."}</p></div></header>
    {!standalone ? <div className="wfx-subtabs">{SECTION_TABS.map((item) => <button type="button" key={item.id} className={section === item.id ? "active" : ""} onClick={() => setSection(item.id)}>{item.label}</button>)}</div> : null}

    {section === "close" ? <>
      <div className="wfx-action-strip no-print"><div><FileSpreadsheet size={22} /><span><strong>Kişi giriş–çıkış / puantaj yükleme</strong><small>TC başlığı farklı yazılsa da tanınır; eşleştirme sırası TC → Employee ID → Roster ID’dir. Mobil ve sistem kayıtları dosyayla ezilmez.</small></span></div><div className="wfx-toolbar">{permissions.manualCorrection || permissions.importRoster ? <button type="button" onClick={() => attendanceRef.current?.click()}><Upload size={16} />Giriş–çıkış dosyası yükle</button> : null}<input ref={attendanceRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importAttendance} /></div></div>
      {state.attendanceImport ? <div className="wfx-print-summary wfx-close-summary no-print"><span>Son puantaj dosyası<strong>{state.attendanceImport.file}</strong></span><span>Eklenen<strong>{state.attendanceImport.inserted}</strong></span><span>Güncellenen<strong>{state.attendanceImport.updated}</strong></span><span>Korunan sistem kaydı<strong>{state.attendanceImport.protectedRows}</strong></span><span>Eşleşmeyen<strong>{state.attendanceImport.unmatched}</strong></span></div> : null}
      <div className="wfx-close-filter no-print"><label>Başlangıç<input type="date" value={period.startDate} onChange={(event) => setPeriod({ ...period, startDate: event.target.value })} /></label><label>Kesim tarihi<input type="date" value={period.endDate} onChange={(event) => setPeriod({ ...period, endDate: event.target.value })} /></label><label>Depo<select value={period.warehouse} onChange={(event) => setPeriod({ ...period, warehouse: event.target.value })}><option value="">Tüm depolar</option>{[...new Set(state.people.map((person) => person.warehouse).filter(Boolean))].sort().map((warehouse) => <option key={warehouse}>{warehouse}</option>)}</select></label><label>Personel<select value={period.personId} onChange={(event) => setPeriod({ ...period, personId: event.target.value })}><option value="">Tüm kişiler</option>{state.people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><div className="wfx-toolbar">{permissions.export ? <button type="button" className="secondary compact" onClick={exportPayroll}><Download size={16} />İK CSV</button> : null}{permissions.print ? <button type="button" className="secondary compact" onClick={() => window.print()}><Printer size={16} />Yazdır / PDF</button> : null}{permissions.closePeriod ? <button type="button" onClick={saveCloseRun}><Save size={16} />Kapanış taslağı</button> : null}</div></div>
      <div className="wfx-print-document wfx-close-document"><div className="wfx-print-title"><div><strong>OPEX WORKFORCE</strong><h1>KÜMÜLATİF DÖNEM PUANTAJI</h1></div><div><span>{period.personId ? rows[0]?.name : period.warehouse || "Tüm Türkiye"}</span><small>{period.startDate} – {period.endDate}</small></div></div>
      <div className="wfx-print-summary wfx-close-summary"><span>Planlanan<strong>{formatMinutes(totals.expectedMinutes)}</strong></span><span>Fiili Çalışma<strong>{formatMinutes(totals.workedMinutes)}</strong></span><span>Normal<strong>{formatMinutes(totals.normalMinutes)}</strong></span><span>Resmî Tatil<strong>{formatMinutes(totals.holidayMinutes)}</strong></span><span>Fazla Mesai<strong>{formatMinutes(totals.overtimeMinutes)}</strong></span><span>İzin<strong>{formatMinutes(totals.leaveMinutes)}</strong></span></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Personel</th><th>TC</th><th>Depo</th><th>İşe Giriş / Çıkış</th><th>Plan</th><th>Fiili</th><th>Normal</th><th>Resmî</th><th>Gece</th><th>Fazla</th><th>Eksik</th><th>İzin</th></tr></thead><tbody>{rows.map((row) => <tr key={row.personId}><td><strong>{row.name}</strong><small>{row.personId} · {row.role}</small></td><td><span className="wfx-sensitive"><LockKeyhole size={12} />{displayNationalId(row.nationalId)}</span></td><td>{row.warehouse}</td><td><strong>{row.hireDate || "—"}</strong><small>{row.terminationDate ? `Çıkış: ${row.terminationDate}` : "Aktif"}</small></td><td>{formatMinutes(row.expectedMinutes)}</td><td>{formatMinutes(row.workedMinutes)}</td><td>{formatMinutes(row.normalMinutes)}</td><td className="wfx-purple">{formatMinutes(row.holidayMinutes)}</td><td>{formatMinutes(row.nightMinutes)}</td><td>{formatMinutes(row.overtimeMinutes)}</td><td className={row.missingMinutes ? "wfx-red" : ""}>{formatMinutes(row.missingMinutes)}</td><td>{formatMinutes(row.leaveMinutes)}</td></tr>)}</tbody></table></div>
      <div className="wfx-signatures"><div>Hazırlayan<span /></div><div>Operasyon Onayı<span /></div><div>İK / Bordro<span /></div></div></div>
      {!permissions.fullNationalId ? <div className="wfx-permission-info"><ShieldCheck size={17} />TC kimlik numarası yetkiniz nedeniyle ilk iki ve son iki hane olarak maskeleniyor.</div> : null}
    </> : null}

    {section === "employees" ? <>
      <div className="wfx-action-strip"><div><UserRoundCog size={22} /><span><strong>Personel ana verisi ve uygulama erişimi</strong><small>Employee ID ve Roster ID ayrı tutulur; TC güvenli eşleştirme anahtarıdır. Aynı Excel ile ad soyad, işe giriş/çıkış, depo ve erişim bilgileri toplu güncellenir.</small></span></div><span className="wfx-status live">{selectedEmployees.length} seçili · {state.people.reduce((total, person) => total + (person.rosterIds?.length || 0), 0) + rosterIdsByPerson.size} Roster ID</span></div>
      <div className="wfx-professional-actions">
        <button type="button" className="wfx-pro-action secondary" onClick={downloadEmployeeTemplate}><span className="icon"><FileSpreadsheet size={20} /></span><span><strong>Personel ana veri şablonunu indir</strong><small>Employee ID, Roster ID, TC, ad soyad ve giriş–çıkış tek dosyada</small></span><Download size={17} /></button>
        {permissions.manageEmployees ? <button type="button" className="wfx-pro-action primary" onClick={() => employeeRef.current?.click()}><span className="icon"><Upload size={20} /></span><span><strong>Toplu personel ana veri yükle</strong><small>CSV/XLSX · TC → Employee ID → Roster ID doğrulaması</small></span><Upload size={17} /></button> : null}
        <button type="button" className="wfx-pro-action secondary" onClick={downloadEmploymentTemplate}><span className="icon"><FileSpreadsheet size={20} /></span><span><strong>İşe giriş/çıkış şablonu</strong><small>TC, işe giriş ve işten çıkış tarihleri</small></span><Download size={17} /></button>
        {permissions.manageEmployees ? <button type="button" className="wfx-pro-action primary" onClick={() => employmentRef.current?.click()}><span className="icon"><Upload size={20} /></span><span><strong>İşe giriş/çıkış yükle</strong><small>Farklı kolon adlarını tanır; TC ile mevcut kişiyi bulur</small></span><Upload size={17} /></button> : null}
        {permissions.manageEmployees ? <button type="button" className="wfx-pro-action secondary" disabled={!selectedEmployees.length} onClick={() => createUserAccounts(selectedEmployees)}><span className="icon"><UserPlus size={20} /></span><span><strong>Uygulama kullanıcısı oluştur</strong><small>Seçilen aktif kişilere davet ve erişim tanımla</small></span><Mail size={17} /></button> : null}
        {permissions.manageEmployees ? <button type="button" className="wfx-pro-action secondary" disabled={!selectedEmployees.length} onClick={() => createPasswordResetLinks(selectedEmployees)}><span className="icon"><KeyRound size={20} /></span><span><strong>Şifre sıfırlama bağlantısı</strong><small>Tek kişide panoya, toplu seçimde güvenli CSV’ye aktar</small></span><Link2 size={17} /></button> : null}
        <button type="button" className="wfx-pro-action secondary" onClick={downloadEmployeeRosterIdentityTemplate}><span className="icon"><Fingerprint size={20} /></span><span><strong>Roster ID şablonunu indir</strong><small>rider_id + TCK formatı; gönderdiğiniz kolonlarla aynı</small></span><Download size={17} /></button>
        {permissions.manageEmployees || permissions.importRoster ? <button type="button" className="wfx-pro-action primary" onClick={() => employeeRosterIdentityRef.current?.click()}><span className="icon"><Fingerprint size={20} /></span><span><strong>Toplu Roster ID eşleştir</strong><small>CSV/XLSX · rider_id, rider_name, TCK, contract_name, IsActive, phone_num, email</small></span><Upload size={17} /></button> : null}
        <input ref={employeeRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importEmployees} />
        <input ref={employmentRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importEmploymentLifecycle} />
        <input ref={employeeRosterIdentityRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importEmployeeRosterIdentities} />
      </div>
      {state.employeeImport ? <div className="wfx-print-summary wfx-close-summary"><span>Son dosya<strong>{state.employeeImport.file}</strong></span><span>Toplam<strong>{state.employeeImport.total}</strong></span><span>Yeni kişi<strong>{state.employeeImport.created}</strong></span><span>Güncellenen<strong>{state.employeeImport.updated}</strong></span><span>Yeni çıkış<strong>{state.employeeImport.terminated}</strong></span><span>Eşleşmeyen depo<strong>{state.employeeImport.unmatchedWarehouses?.length || 0}</strong></span></div> : null}
      {state.employmentLifecycleImport ? <div className="wfx-print-summary wfx-close-summary"><span>Giriş/çıkış dosyası<strong>{state.employmentLifecycleImport.file}</strong></span><span>Toplam<strong>{state.employmentLifecycleImport.total}</strong></span><span>Eşleşen<strong>{state.employmentLifecycleImport.matched}</strong></span><span>Eşleşmeyen<strong>{state.employmentLifecycleImport.unmatched}</strong></span></div> : null}
      <div className="wfx-employee-toolbar"><label className="wfx-search"><UsersRound size={16} /><input value={employeeQuery} onChange={(event) => setEmployeeQuery(event.target.value)} placeholder="Employee ID, Roster ID, ad, e-posta veya depo ara…" /></label><small>TC yetkisi olmayan kullanıcılar yalnız ilk 2 ve son 2 haneyi görür.</small></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th className="wfx-check-cell"><input aria-label="Tüm kişileri seç" type="checkbox" checked={Boolean(visiblePeople.length && visiblePeople.every((person) => selectedEmployees.includes(String(person.id))))} onChange={() => setSelectedEmployees(visiblePeople.every((person) => selectedEmployees.includes(String(person.id))) ? selectedEmployees.filter((id) => !visiblePeople.some((person) => String(person.id) === id)) : [...new Set([...selectedEmployees, ...visiblePeople.map((person) => String(person.id))])])} /></th><th>Employee ID</th><th>Roster ID</th><th>Ad Soyad</th><th>TC</th><th>E-posta / Uygulama</th><th>Actual Warehouse</th><th>İK Kodu / Unvan</th><th>İşe Giriş / Çıkış</th><th>Erişim</th><th>İşlem</th></tr></thead><tbody>{visiblePeople.map((person) => { const account = accountsByPerson.get(String(person.id)); const selected = selectedEmployees.includes(String(person.id)); return <tr key={person.id} className={selected ? "is-selected" : ""}><td className="wfx-check-cell"><input aria-label={`${person.name} seç`} type="checkbox" checked={selected} onChange={() => setSelectedEmployees((current) => current.includes(String(person.id)) ? current.filter((id) => id !== String(person.id)) : [...current, String(person.id)])} /></td><td><strong>{person.id}</strong></td><td><strong>{person.rosterIds?.join(", ") || "—"}</strong><small>{person.rosterIds?.length > 1 ? "Geçmiş ID'ler korunuyor" : "Operasyon kimliği"}</small></td><td><strong>{person.name}</strong><small>{person.phone || "Telefon yok"}</small></td><td><span className="wfx-sensitive"><LockKeyhole size={12} />{displayNationalId(person.nationalId)}</span></td><td><strong>{person.email || "E-posta yok"}</strong><small>{account?.resetRequestedAt ? `Son sıfırlama: ${account.resetRequestedAt.slice(0, 16).replace("T", " ")}` : "Sıfırlama bağlantısı yok"}</small></td><td><strong>{person.warehouse || "—"}</strong><small>{person.sourceWarehouse && person.sourceWarehouse !== person.warehouse ? `Kaynak: ${person.sourceWarehouse}` : ""}</small></td><td><strong>{person.warehouseCode || "—"}</strong><small>{person.role}</small></td><td><strong>{person.hireDate || "—"}</strong><small>{person.terminationDate ? `Çıkış: ${person.terminationDate}` : "Aktif çalışan"}</small></td><td><span className={`wfx-status ${person.terminationDate ? "danger" : account ? account.status === "Aktif" ? "success" : "warning" : "neutral"}`}>{person.terminationDate ? "Erişim kapalı" : account?.status || "Oluşturulmadı"}</span></td><td><div className="wfx-row-actions">{permissions.manageEmployees ? <button type="button" onClick={() => setEditingPerson({ ...person })}><PencilLine size={15} />Düzenle</button> : null}{permissions.manageEmployees && !person.terminationDate ? <button type="button" className="secondary compact" disabled={!person.email} onClick={() => createUserAccounts([String(person.id)])}>{account ? "Erişimi güncelle" : "Kullanıcı oluştur"}</button> : null}{permissions.manageEmployees && account && !person.terminationDate ? <button type="button" className="secondary compact" onClick={() => createPasswordResetLinks([String(person.id)])}><KeyRound size={15} />Şifre linki</button> : null}</div></td></tr>; })}</tbody></table></div>
      {editingPerson ? <div className="wfx-modal-backdrop" role="presentation" onMouseDown={() => setEditingPerson(null)}><section className="wfx-modal wide" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><span>Personel ana verisi</span><h2>{editingPerson.name} kaydını düzenle</h2></div><button type="button" className="icon" onClick={() => setEditingPerson(null)}><X size={18} /></button></header><div className="wfx-form-grid"><label>Employee ID<input value={editingPerson.id} disabled /></label><label>Ad Soyad<input value={editingPerson.name || ""} onChange={(event) => setEditingPerson({ ...editingPerson, name: event.target.value })} /></label><label>TC Kimlik<input value={editingPerson.nationalId || ""} disabled={!permissions.fullNationalId} onChange={(event) => setEditingPerson({ ...editingPerson, nationalId: event.target.value.replace(/\D/g, "").slice(0, 11) })} /></label><label>E-posta<input type="email" value={editingPerson.email || ""} onChange={(event) => setEditingPerson({ ...editingPerson, email: event.target.value })} /></label><label>Telefon<input value={editingPerson.phone || ""} onChange={(event) => setEditingPerson({ ...editingPerson, phone: event.target.value })} /></label><label>Actual Warehouse<select value={editingPerson.warehouse || ""} onChange={(event) => setEditingPerson({ ...editingPerson, warehouse: event.target.value })}><option value="">Depo seç</option>{state.warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.name}>{warehouse.name}</option>)}</select></label><label>İK Depo Kodu<input value={editingPerson.warehouseCode || ""} onChange={(event) => setEditingPerson({ ...editingPerson, warehouseCode: event.target.value })} /></label><label>Unvan<input value={editingPerson.role || ""} onChange={(event) => setEditingPerson({ ...editingPerson, role: event.target.value })} placeholder="Mağaza Görevlisi, Mağaza Müdürü…" /></label><label>İşe Giriş<input type="date" value={editingPerson.hireDate || ""} onChange={(event) => setEditingPerson({ ...editingPerson, hireDate: event.target.value })} /></label><label>İşten Ayrılış<input type="date" value={editingPerson.terminationDate || ""} onChange={(event) => setEditingPerson({ ...editingPerson, terminationDate: event.target.value })} /></label></div><footer><button type="button" className="secondary" onClick={() => setEditingPerson(null)}>Vazgeç</button><button type="button" onClick={savePerson}><Save size={16} />Personeli güncelle</button></footer></section></div> : null}
    </> : null}

    {section === "timeoff" ? <>
      <div className="wfx-action-strip"><div><FileSpreadsheet size={22} /><span><strong>Time Off Used toplu yükleme</strong><small>TC → Employee Number → Roster ID sırasıyla eşleşir; kolon adı ve büyük/küçük harf farkı önemsenmez. Müdürün girdiği aynı kişi/gün ikinci kez eklenmez.</small></span></div><div className="wfx-toolbar">{permissions.importTimeOff ? <button type="button" onClick={() => timeOffRef.current?.click()}><Upload size={16} />Time Off Excel yükle</button> : null}<input ref={timeOffRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importTimeOff} /></div></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Personel</th><th>Tarih</th><th>Depo</th><th>İzin</th><th>Süre</th><th>Kaynak</th><th>Onay</th></tr></thead><tbody>{[...state.leaves].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 300).map((leave) => { const person = state.people.find((item) => item.id === leave.personId); const type = state.leaveTypes.find((item) => item.id === leave.typeId); return <tr key={leave.id}><td><strong>{person?.name || leave.personName || "Eşleşmeyen"}</strong><small>{leave.personId}</small></td><td>{leave.date}</td><td>{leave.warehouse}</td><td>{type?.name || leave.category || leave.typeId}</td><td>{formatMinutes(leave.minutes)}</td><td>{leave.source || "Müdür girişi"}</td><td><span className="wfx-status success">{leave.approval}</span></td></tr>; })}</tbody></table></div>
    </> : null}
  </section>;
}

export function WorkforceOpexLab({ state, updateState, permissions, user, setNotice }) {
  const [section, setSection] = useState("lab");
  const [period, setPeriod] = useState({ startDate: "2026-06-01", endDate: "2026-07-20", regionalManager: "", regionalExecutive: "", warehouse: "", personId: "", title: "" });
  const [rosterRows, setRosterRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAnomalies, setSelectedAnomalies] = useState([]);
  const rosterRef = useRef(null);
  const identityRef = useRef(null);

  useEffect(() => { loadRosterRows().then(setRosterRows).finally(() => setLoading(false)); }, []);
  const rosterIsTemporarySource = Boolean(rosterRows.length && state.rosterImport && state.rosterImport.temporaryActive !== false);
  const hasTemporaryRosterData = Boolean(rosterRows.length || state.rosterImport || Object.keys(state.rosterIdentityMap || {}).length || Object.keys(state.rosterOverrides || {}).length || (state.rosterTasks || []).length);
  const reconciledRosterRows = useMemo(() => reconcileRosterRows(rosterRows, state), [rosterRows, state.rosterIdentityMap, state.people]);
  const periodRows = useMemo(() => reconciledRosterRows.filter((row) => inPeriod(row.date, period)), [reconciledRosterRows, period]);
  const identityMappings = useMemo(() => Object.values(state.rosterIdentityMap || {}).sort((a, b) => a.rosterPersonName.localeCompare(b.rosterPersonName, "tr")), [state.rosterIdentityMap]);
  const identityAudit = useMemo(() => {
    const rawPeople = [...new Map(rosterRows.map((row) => [String(row.personId), row])).values()];
    const reconciledByRosterId = new Map(reconciledRosterRows.map((row) => [String(row.rosterPersonId || row.personId), row]));
    return rawPeople.map((row) => {
      const rosterPersonId = String(row.personId);
      const reconciled = reconciledByRosterId.get(rosterPersonId);
      const mapping = (state.rosterIdentityMap || {})[rosterPersonId];
      return {
        rosterPersonId, rosterPersonName: row.personName, title: row.title, warehouse: row.warehouse,
        hrPersonId: reconciled?.identityStatus === "Eşleşti" ? reconciled.personId : "",
        hrPersonName: reconciled?.identityStatus === "Eşleşti" ? reconciled.personName : "",
        nationalId: mapping?.nationalId || row.nationalId || "", method: reconciled?.identityMethod || mapping?.method || "",
        status: reconciled?.identityStatus || mapping?.status || "Eşleşmedi", reason: reconciled?.identityStatus === "Eşleşti" ? "" : mapping?.reason || "TC eşleştirme dosyasında bulunamadı",
      };
    }).sort((a, b) => a.status.localeCompare(b.status, "tr") || a.rosterPersonName.localeCompare(b.rosterPersonName, "tr"));
  }, [rosterRows, reconciledRosterRows, state.rosterIdentityMap]);
  const leaveKeys = useMemo(() => new Set(state.leaves.map((leave) => `${leave.personId}|${leave.date}`)), [state.leaves]);
  const anomalies = useMemo(() => periodRows.filter((row) => row.anomaly), [periodRows]);
  const overrides = state.rosterOverrides || {};
  const effectiveMinutes = (row) => leaveKeys.has(`${row.personId}|${row.date}`) ? 0 : Number(overrides[row.sourceKey]?.normalizedMinutes ?? row.netMinutes);
  const anomalyKeys = useMemo(() => new Set(anomalies.map((row) => row.sourceKey)), [anomalies]);
  const selectedAnomalyRows = useMemo(() => anomalies.filter((row) => selectedAnomalies.includes(row.sourceKey)), [anomalies, selectedAnomalies]);
  const rosterTasks = state.rosterTasks || [];
  const managerByWarehouse = useMemo(() => {
    const managers = new Map();
    periodRows.filter(isManager).forEach((row) => managers.set(row.warehouse, { id: row.personId, name: row.personName, source: row.title || "Depo yöneticisi" }));
    state.people.filter((person) => isManager(person)).forEach((person) => managers.set(person.warehouse, { id: person.id, name: person.name, source: "Personel ana verisi" }));
    state.staffingNorms.forEach((row) => { if (!managers.has(row.warehouse)) managers.set(row.warehouse, { id: "", name: row.regionalExecutive, source: "BY / Regional Executive" }); });
    return managers;
  }, [periodRows, state.people, state.staffingNorms]);

  const payrollRows = useMemo(() => {
    const peopleById = new Map(state.people.map((person) => [String(person.id), person]));
    const leaveTypes = new Map(state.leaveTypes.map((type) => [type.id, type]));
    const daily = new Map();
    const ensureDay = (personId, date, fallback = {}) => {
      const key = `${personId}|${date}`;
      if (!daily.has(key)) daily.set(key, {
        key, personId: String(personId), date, personName: fallback.personName || peopleById.get(String(personId))?.name || "Eşleşmeyen personel",
        warehouse: fallback.warehouse || peopleById.get(String(personId))?.warehouse || "Eşleşmeyen depo", title: fallback.title || peopleById.get(String(personId))?.role || "—",
        rawMinutes: 0, effectiveMinutes: 0, holidayMinutes: 0, nightMinutes: 0, shiftCount: 0, anomalyCount: 0, simulationCount: 0,
        leaveMinutes: 0, paidLeaveMinutes: 0, unpaidLeaveMinutes: 0, leaveLabels: new Set(), rosterIds: new Set(), hasRoster: false,
      });
      return daily.get(key);
    };

    periodRows.forEach((row) => {
      const target = ensureDay(row.personId, row.date, row);
      const effective = effectiveMinutes(row);
      target.personName = row.personName || target.personName; target.warehouse = row.warehouse || target.warehouse; target.title = row.title || target.title;
      target.rawMinutes += Number(row.netMinutes) || 0; target.effectiveMinutes += effective;
      target.holidayMinutes += Math.min(effective, Number(row.holidayMinutes) || 0);
      target.nightMinutes += rosterNightMinutes(row, effective); target.shiftCount += 1; target.hasRoster = true;
      target.rosterIds.add(String(row.rosterPersonId || row.personId));
      target.anomalyCount += row.anomaly ? 1 : 0; target.simulationCount += overrides[row.sourceKey] ? 1 : 0;
    });

    state.leaves.filter((leave) => inPeriod(leave.date, period)).forEach((leave) => {
      const target = ensureDay(leave.personId, leave.date, leave);
      const type = leaveTypes.get(leave.typeId); const minutes = Number(leave.minutes) || 0;
      target.leaveMinutes += minutes;
      if (type?.paid || type?.creditsPayroll) target.paidLeaveMinutes += minutes; else target.unpaidLeaveMinutes += minutes;
      target.leaveLabels.add(type?.name || leave.category || leave.typeId || "İzin");
    });

    const people = new Map();
    [...daily.values()].forEach((day) => {
      if (period.warehouse && day.warehouse !== period.warehouse) return;
      if (period.personId && day.personId !== period.personId) return;
      if (period.title && day.title !== period.title) return;
      if (!people.has(day.personId)) people.set(day.personId, {
        personId: day.personId, personName: day.personName, warehouse: day.warehouse, title: day.title,
        shiftCount: 0, workedDays: 0, leaveDays: 0, rawMinutes: 0, workedMinutes: 0, normalMinutes: 0, holidayMinutes: 0,
        nightMinutes: 0, overtimeMinutes: 0, leaveMinutes: 0, paidLeaveMinutes: 0, unpaidLeaveMinutes: 0,
        conflictDays: 0, anomalyCount: 0, simulationCount: 0, leaveLabels: new Set(), rosterIds: new Set(),
      });
      const target = people.get(day.personId);
      const nonHoliday = Math.max(0, day.effectiveMinutes - day.holidayMinutes);
      target.shiftCount += day.shiftCount; target.workedDays += day.effectiveMinutes > 0 ? 1 : 0; target.leaveDays += day.leaveMinutes > 0 ? 1 : 0;
      target.rawMinutes += day.rawMinutes; target.workedMinutes += day.effectiveMinutes;
      target.normalMinutes += Math.min(450, nonHoliday); target.overtimeMinutes += Math.max(0, nonHoliday - 450);
      target.holidayMinutes += day.holidayMinutes; target.nightMinutes += Math.min(day.effectiveMinutes, day.nightMinutes);
      target.leaveMinutes += day.leaveMinutes; target.paidLeaveMinutes += day.paidLeaveMinutes; target.unpaidLeaveMinutes += day.unpaidLeaveMinutes;
      target.conflictDays += day.hasRoster && day.leaveMinutes > 0 ? 1 : 0; target.anomalyCount += day.anomalyCount; target.simulationCount += day.simulationCount;
      day.leaveLabels.forEach((label) => target.leaveLabels.add(label));
      day.rosterIds.forEach((id) => target.rosterIds.add(id));
    });
    return [...people.values()].map((row) => ({ ...row, leaveLabels: [...row.leaveLabels].join(", ") || "—", rosterIds: [...row.rosterIds].join(", ") || "—" })).sort((a, b) => a.personName.localeCompare(b.personName, "tr"));
  }, [periodRows, period, state.people, state.leaves, state.leaveTypes, overrides, leaveKeys]);

  const payrollTotals = useMemo(() => payrollRows.reduce((total, row) => ({
    people: total.people + 1, workedMinutes: total.workedMinutes + row.workedMinutes, normalMinutes: total.normalMinutes + row.normalMinutes,
    holidayMinutes: total.holidayMinutes + row.holidayMinutes, overtimeMinutes: total.overtimeMinutes + row.overtimeMinutes,
    leaveMinutes: total.leaveMinutes + row.leaveMinutes, anomalyCount: total.anomalyCount + row.anomalyCount,
  }), { people: 0, workedMinutes: 0, normalMinutes: 0, holidayMinutes: 0, overtimeMinutes: 0, leaveMinutes: 0, anomalyCount: 0 }), [payrollRows]);

  async function importRoster(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    setLoading(true);
    try {
      const result = await parseRosterFile(file);
      await saveRosterRows(result.rows);
      setRosterRows(result.rows);
      updateState("rosterImport", { ...result.summary, file: file.name, importedAt: new Date().toISOString(), importedBy: user?.email, temporaryActive: true }, { event: "TEMPORARY_ROSTER_IMPORTED", ...result.summary, file: file.name, temporaryActive: true });
      const inlineIdentities = [...new Map(result.rows.filter((row) => row.nationalId).map((row) => [String(row.personId), { rosterPersonId: String(row.personId), rosterPersonName: row.personName, nationalId: row.nationalId, email: row.email, contract: row.contract, active: row.isActive }])).values()];
      if (inlineIdentities.length) {
        const identityResult = buildRosterIdentityMappings(inlineIdentities, state.people, state.rosterIdentityMap || {});
        updateState("rosterIdentityMap", identityResult.mappings, { event: "ROSTER_INLINE_TC_RECONCILED", file: file.name, ...identityResult.summary });
        updateState("rosterIdentityImport", { ...identityResult.summary, file: file.name, source: "Roster içi TCK", importedAt: new Date().toISOString(), importedBy: user?.email }, { event: "ROSTER_INLINE_TC_IMPORT_SUMMARY_SAVED", file: file.name });
      }
      setNotice(`${result.summary.total.toLocaleString("tr-TR")} roster satırı geçici kaynak olarak yüklendi; ${result.summary.anomalies} adet 11 saat üstü kayıt ayrı incelemeye alındı.`);
    } catch (error) { setNotice(`Roster dosyası okunamadı: ${error.message}`); }
    finally { setLoading(false); }
  }

  function toggleTemporaryRosterSource() {
    if (!state.rosterImport || !rosterRows.length) return;
    const nextActive = !rosterIsTemporarySource;
    updateState("rosterImport", (current) => ({ ...current, temporaryActive: nextActive, sourceChangedAt: new Date().toISOString(), sourceChangedBy: user?.email || user?.name }), { event: nextActive ? "TEMPORARY_ROSTER_SOURCE_ENABLED" : "CHECKIN_SOURCE_RESTORED", temporaryActive: nextActive });
    setNotice(nextActive ? "Workforce Analytics geçici olarak roster verisini kullanıyor." : "Ana analiz kaynağı check-in/check-out puantajına döndü; roster verisi silinmedi.");
  }

  async function deleteTemporaryRosterData() {
    if (!hasTemporaryRosterData) return;
    const confirmed = window.confirm("Geçici OPEX Roster Lab verileri silinsin mi? Roster satırları, TC/ID eşleştirmeleri, simülasyonlar ve roster görevleri silinir. Personel, izin, depo, norm ve check-in/check-out puantajı korunur.");
    if (!confirmed) return;
    try {
      const counts = {
        rosterRows: rosterRows.length,
        identityMappings: Object.keys(state.rosterIdentityMap || {}).length,
        simulations: Object.keys(state.rosterOverrides || {}).length,
        tasks: (state.rosterTasks || []).length,
      };
      await clearRosterRows();
      setRosterRows([]);
      setSelectedAnomalies([]);
      setSection("lab");
      updateState("rosterImport", null, { event: "TEMPORARY_ROSTER_DATA_PURGED", ...counts, preserved: ["people", "leaves", "warehouses", "staffingNorms", "attendance"] });
      updateState("rosterIdentityMap", {});
      updateState("rosterIdentityImport", null);
      updateState("rosterOverrides", {});
      updateState("rosterTasks", []);
      updateState("notifications", (current = []) => current.filter((notification) => notification.type !== "roster-task"));
      setNotice("Geçici roster laboratuvarı temizlendi. Ana kaynak check-in/check-out; personel, izin, depo, norm ve puantaj kayıtları korundu.");
    } catch (error) {
      setNotice(`Geçici roster verileri silinemedi: ${error.message}`);
    }
  }

  function downloadIdentityTemplate() {
    downloadXlsx("roster_id_tc_otomatik_eslestirme_sablonu.xlsx", "Roster TC Eşleştirme", ["rider_id", "rider_name", "TCK", "contract_name", "IsActive", "phone_num", "email"], [["38911", "ABDULKADİR GÜLŞEN", "11111111111", "IN_HOUSE", "1", "+905551112233", "picker@company.com"]]);
  }

  async function importRosterIdentities(event) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try {
      const rows = await parseRosterIdentityFile(file);
      const result = buildRosterIdentityMappings(rows, state.people, state.rosterIdentityMap || {});
      updateState("rosterIdentityMap", result.mappings, { event: "ROSTER_IDENTITIES_RECONCILED", file: file.name, ...result.summary });
      updateState("rosterIdentityImport", { ...result.summary, file: file.name, importedAt: new Date().toISOString(), importedBy: user?.email }, { event: "ROSTER_IDENTITY_IMPORT_SUMMARY_SAVED", file: file.name });
      setNotice(`${result.summary.matched} roster kimliği TC ile İK kaydına bağlandı; ${result.summary.unmatched} kayıt eşleşmedi${result.summary.ambiguous ? `, ${result.summary.ambiguous} kayıt belirsiz` : ""}.`);
    } catch (error) { setNotice(`Roster kimlik dosyası okunamadı: ${error.message}`); }
  }

  function normalizeRows(rows) {
    const next = { ...overrides };
    rows.forEach((row) => { next[row.sourceKey] = { normalizedMinutes: 450, reason: "OPEX roster simülasyonu - 11 saat üstü şüpheli kayıt", actor: user?.email, at: new Date().toISOString(), simulationOnly: true }; });
    updateState("rosterOverrides", next, { event: "ROSTER_SIMULATION_NORMALIZED", count: rows.length, simulationOnly: true });
    setNotice(`${rows.length} şüpheli kayıt yalnız OPEX simülasyonunda 7,5 saate çekildi; ham roster ve bordro değişmedi.`);
  }

  function toggleAllAnomalies() {
    const allSelected = anomalies.length && anomalies.every((row) => selectedAnomalies.includes(row.sourceKey));
    setSelectedAnomalies(allSelected ? selectedAnomalies.filter((key) => !anomalyKeys.has(key)) : [...new Set([...selectedAnomalies, ...anomalies.map((row) => row.sourceKey)])]);
  }

  function assignTasks(rows) {
    if (!rows.length) return;
    const alreadyAssigned = new Set(rosterTasks.filter((task) => task.status === "Açık").flatMap((task) => task.recordKeys || []));
    const assignableRows = rows.filter((row) => !alreadyAssigned.has(row.sourceKey));
    if (!assignableRows.length) { setNotice("Seçilen kayıtların tamamı zaten açık bir yönetici görevinde."); return; }
    const grouped = new Map();
    assignableRows.forEach((row) => { if (!grouped.has(row.warehouse)) grouped.set(row.warehouse, []); grouped.get(row.warehouse).push(row); });
    const createdAt = new Date().toISOString();
    const tasks = [...grouped.entries()].map(([warehouse, records]) => {
      const manager = managerByWarehouse.get(warehouse) || { id: "", name: "Yönetici eşleşmesi bekliyor", source: "Eşleşmedi" };
      return {
        id: `RTASK-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, type: "ROSTER_CORRECTION", title: "11 saat üstü roster düzeltmesi",
        warehouse, assigneeId: manager.id, assigneeName: manager.name, assigneeSource: manager.source, status: "Açık", priority: "Yüksek",
        recordKeys: records.map((row) => row.sourceKey), recordCount: records.length, periodStart: period.startDate, periodEnd: period.endDate,
        createdAt, createdBy: user?.email || user?.name || "unknown", note: "Ham kayıt kontrol edilmeli; gerekiyorsa gerekçeli düzeltme uygulanmalı.",
      };
    });
    updateState("rosterTasks", (current = []) => [...tasks, ...current], { event: "ROSTER_CORRECTION_TASKS_ASSIGNED", taskIds: tasks.map((task) => task.id), recordCount: assignableRows.length });
    const notifications = tasks.filter((task) => task.assigneeId).map((task) => ({ id: `NOT-${task.id}`, personId: task.assigneeId, type: "roster-task", title: "Roster düzeltme görevi", message: `${task.warehouse} · ${task.recordCount} kayıt · ${task.periodStart}–${task.periodEnd}`, createdAt, read: false }));
    if (notifications.length) updateState("notifications", (current = []) => [...notifications, ...current], { event: "ROSTER_TASK_NOTIFICATIONS_CREATED", count: notifications.length });
    setSelectedAnomalies([]);
    setNotice(`${assignableRows.length} kayıt için ${tasks.length} depo yöneticisi görevi oluşturuldu${assignableRows.length < rows.length ? `; ${rows.length - assignableRows.length} mükerrer kayıt atlandı` : ""}.`);
  }

  function completeTask(task) {
    updateState("rosterTasks", (current = []) => current.map((row) => row.id === task.id ? { ...row, status: "Tamamlandı", completedAt: new Date().toISOString(), completedBy: user?.email || user?.name } : row), { event: "ROSTER_CORRECTION_TASK_COMPLETED", taskId: task.id });
    setNotice(`${task.warehouse} görevi tamamlandı olarak kapatıldı.`);
  }

  const normAnalytics = useMemo(() => {
    const byWarehouse = new Map();
    periodRows.filter((row) => !isManager(row)).forEach((row) => {
      if (!byWarehouse.has(row.warehouse)) byWarehouse.set(row.warehouse, { people: new Set(), minutes: 0, overtime: 0, holiday: 0, anomalies: 0 });
      const target = byWarehouse.get(row.warehouse); const effective = effectiveMinutes(row);
      target.people.add(row.personId); target.minutes += effective; target.holiday += Math.min(effective, row.holidayMinutes); target.overtime += Math.max(0, effective - row.holidayMinutes - 450); target.anomalies += row.anomaly ? 1 : 0;
    });
    return state.staffingNorms.map((norm) => {
      const value = byWarehouse.get(norm.warehouse) || { people: new Set(), minutes: 0, overtime: 0, holiday: 0, anomalies: 0 };
      const headcount = value.people.size;
      return { ...norm, headcount, gap: headcount - norm.norm, totalMinutes: value.minutes, overtimeMinutes: value.overtime, holidayMinutes: value.holiday, anomalies: value.anomalies, risk: headcount >= norm.norm && value.overtime > 0 ? "Norm yeterli / mesai var" : headcount < norm.norm ? "Norm altı" : "Dengeli" };
    }).filter((row) => (!period.regionalManager || row.regionalManager === period.regionalManager) && (!period.regionalExecutive || row.regionalExecutive === period.regionalExecutive) && (!period.warehouse || row.warehouse === period.warehouse));
  }, [periodRows, period, state.staffingNorms, overrides, leaveKeys]);

  function exportSimulation() {
    downloadCsv(`opex_roster_simulasyon_${period.startDate}_${period.endDate}.csv`, ["Depo", "Tarih", "Employee ID", "Ad Soyad", "Unvan", "Ham Net dk", "Efektif dk", "Resmi dk", "11 Saat Uyarısı", "İzin Çakışması", "Simülasyon"], periodRows.map((row) => [row.warehouse, row.date, row.personId, row.personName, row.title, row.netMinutes, effectiveMinutes(row), row.holidayMinutes, row.anomaly, leaveKeys.has(`${row.personId}|${row.date}`) ? "İzin var" : "", overrides[row.sourceKey] ? "7.5 saate normalize" : "Ham"]));
  }

  function exportElevenHourRecords() {
    downloadXlsx(`opex_11_saat_kayitlari_${period.startDate}_${period.endDate}.xlsx`, "11 Saat Kayıtları", [
      "Employee ID", "Ad Soyad", "Unvan", "Depo", "Tarih", "Roster Başlangıç", "Roster Bitiş", "Ham Net (saat)", "Hesaba Esas (saat)", "Resmî Tatil (saat)", "İzin Çakışması", "Simülasyon", "Görev Durumu",
    ], anomalies.map((row) => {
      const task = rosterTasks.find((item) => (item.recordKeys || []).includes(row.sourceKey) && item.status === "Açık");
      return [row.personId, row.personName, row.title, row.warehouse, row.date, row.start, row.end, decimalHours(row.netMinutes), decimalHours(effectiveMinutes(row)), decimalHours(row.holidayMinutes), leaveKeys.has(`${row.personId}|${row.date}`) ? "İzin var" : "Yok", overrides[row.sourceKey] ? "7,5 saat" : "Ham", task ? `${task.status} · ${task.assigneeName}` : "Atanmadı"];
    }), [7, 8, 9]);
    setNotice(`${anomalies.length} adet 11 saat üstü kayıt Excel olarak indirildi.`);
  }

  function exportPersonPayroll() {
    downloadXlsx(`opex_kisi_bazli_mesai_${period.startDate}_${period.endDate}.xlsx`, "Kişi Bazlı Mesai", [
      "Employee ID", "Roster Employee ID", "Ad Soyad", "Unvan", "Depo", "Vardiya Satırı", "Çalışılan Gün", "İzin Günü", "Ham Net (saat)", "Hesaba Esas (saat)",
      "Normal (saat)", "Resmî Tatil (saat)", "Gece - yaklaşık (saat)", "Fazla Mesai (saat)", "İzin (saat)", "Ücretli İzin (saat)", "Ücretsiz İzin (saat)",
      "İzin Türleri", "Roster/İzin Çakışması", "11 Saat Uyarısı", "7,5 Saat Simülasyonu", "Dönem Başlangıcı", "Dönem Sonu",
    ], payrollRows.map((row) => [row.personId, row.rosterIds, row.personName, row.title, row.warehouse, row.shiftCount, row.workedDays, row.leaveDays, decimalHours(row.rawMinutes), decimalHours(row.workedMinutes),
      decimalHours(row.normalMinutes), decimalHours(row.holidayMinutes), decimalHours(row.nightMinutes), decimalHours(row.overtimeMinutes), decimalHours(row.leaveMinutes), decimalHours(row.paidLeaveMinutes), decimalHours(row.unpaidLeaveMinutes),
      row.leaveLabels, row.conflictDays, row.anomalyCount, row.simulationCount, period.startDate, period.endDate]), [8, 9, 10, 11, 12, 13, 14, 15, 16]);
    setNotice(`${payrollRows.length} kişinin dönem mesai hesabı İK uyumlu ondalık saatlerle Excel olarak indirildi.`);
  }

  function updateNorm(id, patch) { updateState("staffingNorms", (rows) => rows.map((row) => row.id === id ? { ...row, ...patch } : row), { event: "STAFFING_NORM_UPDATED", recordId: id, patch }); }

  return <section className="wfx-panel wfx-opex-lab">
    <header className="wfx-panel-head responsive"><div><span>OPEX geçiş alanı</span><h2>Geçici Roster Lab, dönem mesaisi ve norm analizi</h2><p>Ana ürün check-in/check-out puantajıdır. Bu laboratuvar yalnız mobil uygulamaya geçiş tamamlanana kadar roster ile deneme ve karşılaştırma yapmak içindir.</p></div><div className="wfx-toolbar">{permissions.importRoster ? <button type="button" className="secondary compact" onClick={() => rosterRef.current?.click()}><Upload size={16} />Geçici roster yükle</button> : null}<input ref={rosterRef} hidden type="file" accept=".csv,.xlsx,.xls,text/csv" onChange={importRoster} />{section === "identity" ? <><button type="button" className="secondary compact" onClick={downloadIdentityTemplate}><Download size={16} />TC ile otomatik eşleştirme şablonu</button>{permissions.importRoster ? <button type="button" onClick={() => identityRef.current?.click()}><Fingerprint size={16} />Roster TC yükle</button> : null}<input ref={identityRef} hidden type="file" accept=".csv,.xlsx,.xls" onChange={importRosterIdentities} /></> : null}{section === "lab" && anomalies.length && permissions.export ? <button type="button" className="secondary compact" onClick={exportElevenHourRecords}><Download size={16} />11 Saat Kayıtları Excel</button> : null}{section === "lab" && periodRows.length ? <button type="button" className="secondary compact" onClick={exportSimulation}><Download size={16} />Simülasyon CSV</button> : null}{section !== "identity" && payrollRows.length && permissions.export ? <button type="button" onClick={exportPersonPayroll}><FileSpreadsheet size={16} />Tüm Dönem Mesai Excel</button> : null}</div></header>
    <div className={`wfx-action-strip responsive wfx-roster-source ${rosterIsTemporarySource ? "is-temporary" : "is-live"}`}><div><CheckCircle2 size={22} /><span><strong>{rosterIsTemporarySource ? "Geçici analiz kaynağı: Roster" : "Ana analiz kaynağı: Check-in / Check-out"}</strong><small>{rosterIsTemporarySource ? "Workforce Analytics geçiş süresince roster + izin + norm kullanıyor. Gerçek puantaj kayıtları korunuyor." : "Dashboard ve ana puantaj gerçek giriş/çıkış kayıtlarını kullanır. Roster Lab bağımsız test alanıdır."}</small></span></div><div className="wfx-toolbar"><span className={`wfx-status ${rosterIsTemporarySource ? "warning" : "live"}`}>{rosterIsTemporarySource ? "Geçici aktif" : "Ana sistem"}</span>{rosterRows.length ? <button type="button" className="secondary compact" onClick={toggleTemporaryRosterSource}>{rosterIsTemporarySource ? "Check-in/out’a dön" : "Roster’ı geçici kaynak yap"}</button> : null}{hasTemporaryRosterData && (permissions.importRoster || permissions.overrideRoster) ? <button type="button" className="secondary compact danger-outline" onClick={deleteTemporaryRosterData}><Trash2 size={16} />Geçici verileri sil</button> : null}</div></div>
    <div className="wfx-subtabs"><button type="button" className={section === "lab" ? "active" : ""} onClick={() => setSection("lab")}>11 Saat Kontrolü</button><button type="button" className={section === "payroll" ? "active" : ""} onClick={() => setSection("payroll")}>Dönem Mesai Hesabı</button><button type="button" className={section === "norms" ? "active" : ""} onClick={() => setSection("norms")}>BY / Norm Raporu</button><button type="button" className={section === "identity" ? "active" : ""} onClick={() => setSection("identity")}><Fingerprint size={15} />Kimlik Eşleştirme</button></div>
    {section !== "identity" ? <div className="wfx-close-filter"><label>Başlangıç<input type="date" value={period.startDate} onChange={(event) => setPeriod({ ...period, startDate: event.target.value })} /></label><label>Kesim tarihi<input type="date" value={period.endDate} onChange={(event) => setPeriod({ ...period, endDate: event.target.value })} /></label>{section === "norms" ? <><label>Regional Manager<select value={period.regionalManager} onChange={(event) => setPeriod({ ...period, regionalManager: event.target.value })}><option value="">Tümü</option>{[...new Set(state.staffingNorms.map((row) => row.regionalManager))].map((value) => <option key={value}>{value}</option>)}</select></label><label>BY / Regional Executive<select value={period.regionalExecutive} onChange={(event) => setPeriod({ ...period, regionalExecutive: event.target.value })}><option value="">Tümü</option>{[...new Set(state.staffingNorms.map((row) => row.regionalExecutive))].map((value) => <option key={value}>{value}</option>)}</select></label></> : null}{section === "payroll" ? <><label>Depo<select value={period.warehouse} onChange={(event) => setPeriod({ ...period, warehouse: event.target.value })}><option value="">Tüm depolar</option>{[...new Set(periodRows.map((row) => row.warehouse).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr")).map((value) => <option key={value}>{value}</option>)}</select></label><label>Personel<select value={period.personId} onChange={(event) => setPeriod({ ...period, personId: event.target.value })}><option value="">Tüm kişiler</option>{[...new Map(periodRows.map((row) => [row.personId, row])).values()].sort((a, b) => a.personName.localeCompare(b.personName, "tr")).map((row) => <option key={row.personId} value={row.personId}>{row.personName} · {row.personId}</option>)}</select></label><label>Unvan<select value={period.title} onChange={(event) => setPeriod({ ...period, title: event.target.value })}><option value="">Tüm unvanlar</option>{[...new Set(periodRows.map((row) => row.title).filter(Boolean))].sort().map((value) => <option key={value}>{value}</option>)}</select></label></> : null}</div> : null}

    {section === "identity" ? <>
      <div className="wfx-print-summary wfx-close-summary"><span>Roster çalışanı<strong>{identityAudit.length.toLocaleString("tr-TR")}</strong></span><span>Eşleşen<strong>{identityAudit.filter((row) => row.status === "Eşleşti").length.toLocaleString("tr-TR")}</strong></span><span>Eşleşmeyen<strong>{identityAudit.filter((row) => row.status !== "Eşleşti").length.toLocaleString("tr-TR")}</strong></span><span>TC ile<strong>{identityAudit.filter((row) => row.method === "TC").length.toLocaleString("tr-TR")}</strong></span><span>Aynı ID<strong>{identityAudit.filter((row) => row.method === "Aynı Employee ID").length.toLocaleString("tr-TR")}</strong></span><span>Son dosya<strong>{state.rosterIdentityImport?.file || "—"}</strong></span></div>
      <div className="wfx-security-note"><Fingerprint size={18} />HR Employee ID girmeniz gerekmez. Standart akışta `rider_id` ham roster anahtarı olarak korunur; sistem `TCK` alanını İK personel ana verisindeki TC ile eşleştirip İK Employee ID sonucunu kendisi üretir. TC yoksa eski dosyalar için HR Employee ID / tekil e-posta yedeği desteklenir; isim benzerliği tek başına otomatik eşleştirme yapmaz.</div>
      <div className="wfx-action-strip responsive"><div><Fingerprint size={22} /><span><strong>Roster–İK kimlik köprüsü</strong><small>Gönderdiğiniz `rider_id, rider_name, TCK, contract_name, IsActive, phone_num, email` formatı doğrudan kabul edilir; HR Employee ID doldurmanız gerekmez.</small></span></div><div className="wfx-toolbar"><button type="button" className="secondary compact" onClick={downloadIdentityTemplate}><Download size={16} />TC şablonu indir</button>{permissions.importRoster ? <button type="button" onClick={() => identityRef.current?.click()}><Upload size={16} />CSV/XLSX TC yükle</button> : null}</div></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Roster personeli</th><th>Roster ID</th><th>TC</th><th>İK personeli</th><th>İK Employee ID</th><th>Depo / Unvan</th><th>Eşleşme yöntemi</th><th>Durum</th></tr></thead><tbody>{(identityAudit.length ? identityAudit : identityMappings).map((row) => <tr key={row.rosterPersonId}><td><strong>{row.rosterPersonName}</strong></td><td>{row.rosterPersonId}</td><td><span className="wfx-sensitive"><LockKeyhole size={12} />{permissions.fullNationalId ? row.nationalId || "—" : maskNationalId(row.nationalId)}</span></td><td><strong>{row.hrPersonName || "—"}</strong><small>{row.reason || "Kimlikler birleştirildi"}</small></td><td>{row.hrPersonId || "—"}</td><td><strong>{row.warehouse || "—"}</strong><small>{row.title || "—"}</small></td><td>{row.method || "—"}</td><td><span className={`wfx-status ${row.status === "Eşleşti" ? "success" : row.status === "Belirsiz" ? "warning" : "danger"}`}>{row.status}</span></td></tr>)}</tbody></table></div>
    </> : null}

    {loading && section !== "identity" ? <div className="wfx-loading">Roster okunuyor…</div> : null}
    {!loading && !rosterRows.length ? <div className="wfx-empty-state"><FlaskConical size={30} /><h3>Roster laboratuvarı boş</h3><p>Aylık Puantaj CSV’sini yüklediğinde ham kayıtlar tarayıcı veritabanında tutulur ve 11 saat kontrolleri burada açılır.</p></div> : null}
    {section === "lab" && rosterRows.length ? <>
      <div className="wfx-print-summary wfx-close-summary"><span>Satır<strong>{periodRows.length.toLocaleString("tr-TR")}</strong></span><span>Çalışan<strong>{new Set(periodRows.map((row) => row.personId)).size.toLocaleString("tr-TR")}</strong></span><span>Depo<strong>{new Set(periodRows.map((row) => row.warehouse)).size}</strong></span><span>11 Saat Üstü<strong>{anomalies.length}</strong></span><span>İzin Çakışması<strong>{periodRows.filter((row) => leaveKeys.has(`${row.personId}|${row.date}`)).length}</strong></span><span>Simülasyon Düzeltmesi<strong>{anomalies.filter((row) => overrides[row.sourceKey]).length}</strong></span></div>
      <div className="wfx-security-note"><AlertTriangle size={18} />11 saat kontrolü net çalışma üzerinden hesaplanır: Günlük Toplam − Günlük Mola. 20 saat gibi şüpheli kayıtlar otomatik olarak bordrodan silinmez. Aşağıdaki 7,5 saat işlemi yalnız test/simülasyondur ve audit kaydı üretir.</div>
      <div className="wfx-action-strip responsive"><div><FlaskConical size={22} /><span><strong>11 saat üstü kayıtlar</strong><small>{anomalies.length} kayıt manuel karar bekliyor · {selectedAnomalyRows.length} seçili</small></span></div><div className="wfx-toolbar"><button type="button" className="secondary compact" onClick={toggleAllAnomalies}>{anomalies.length && anomalies.every((row) => selectedAnomalies.includes(row.sourceKey)) ? "Seçimi temizle" : "Tümünü seç"}</button>{selectedAnomalyRows.length && permissions.assignRosterTask ? <button type="button" className="secondary compact" onClick={() => assignTasks(selectedAnomalyRows)}><ClipboardCheck size={16} />Yöneticisine görev ata</button> : null}{selectedAnomalyRows.length && permissions.overrideRoster ? <button type="button" onClick={() => { normalizeRows(selectedAnomalyRows); setSelectedAnomalies([]); }}>Seçilenleri 7,5 saate çek</button> : null}</div></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th className="wfx-check-cell"><input aria-label="Tümünü seç" type="checkbox" checked={Boolean(anomalies.length && anomalies.every((row) => selectedAnomalies.includes(row.sourceKey)))} onChange={toggleAllAnomalies} /></th><th>Personel</th><th>Depo / Tarih</th><th>Roster</th><th>Ham Net</th><th>Resmî</th><th>İzin</th><th>Simülasyon</th><th>İşlem</th></tr></thead><tbody>{anomalies.slice(0, 500).map((row) => { const overridden = overrides[row.sourceKey]; const hasLeave = leaveKeys.has(`${row.personId}|${row.date}`); const checked = selectedAnomalies.includes(row.sourceKey); return <tr key={row.id} className={checked ? "is-selected" : ""}><td className="wfx-check-cell"><input aria-label={`${row.personName} kaydını seç`} type="checkbox" checked={checked} onChange={() => setSelectedAnomalies((current) => current.includes(row.sourceKey) ? current.filter((key) => key !== row.sourceKey) : [...current, row.sourceKey])} /></td><td><strong>{row.personName}</strong><small>{row.personId} · {row.title}</small></td><td><strong>{row.warehouse}</strong><small>{row.date}</small></td><td>{row.start}–{row.end}</td><td className="wfx-red">{formatMinutes(row.netMinutes)}</td><td>{formatMinutes(row.holidayMinutes)}</td><td>{hasLeave ? <span className="wfx-status warning">İzin çakışması</span> : "—"}</td><td><strong>{formatMinutes(effectiveMinutes(row))}</strong><small>{overridden ? "7,5 saat önerisi" : "Ham değer"}</small></td><td>{permissions.overrideRoster ? <button type="button" className="secondary compact" onClick={() => normalizeRows([row])}>{overridden ? "Yeniden uygula" : "7,5 sa test et"}</button> : null}</td></tr>; })}</tbody></table></div>
      <div className="wfx-action-strip"><div><ClipboardCheck size={22} /><span><strong>Yönetici düzeltme görevleri</strong><small>Açık görevler ilgili depo yöneticisi veya BY’ye atanır; ham roster değişmez.</small></span></div><span className="wfx-status warning">{rosterTasks.filter((task) => task.status === "Açık").length} açık</span></div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Görev</th><th>Depo</th><th>Atanan Yönetici</th><th>Kayıt</th><th>Dönem</th><th>Durum</th><th>İşlem</th></tr></thead><tbody>{rosterTasks.length ? rosterTasks.slice(0, 200).map((task) => <tr key={task.id}><td><strong>{task.title}</strong><small>{task.id} · {task.priority}</small></td><td>{task.warehouse}</td><td><strong>{task.assigneeName}</strong><small>{task.assigneeSource}</small></td><td>{task.recordCount}</td><td>{task.periodStart} – {task.periodEnd}</td><td><span className={`wfx-status ${task.status === "Tamamlandı" ? "success" : "warning"}`}>{task.status}</span></td><td>{task.status !== "Tamamlandı" && permissions.assignRosterTask ? <button type="button" className="secondary compact" onClick={() => completeTask(task)}>Tamamlandı işaretle</button> : "—"}</td></tr>) : <tr><td colSpan="7">Henüz yönetici görevi oluşturulmadı.</td></tr>}</tbody></table></div>
    </> : null}

    {section === "payroll" && rosterRows.length ? <>
      <div className="wfx-print-summary wfx-close-summary"><span>Çalışan<strong>{payrollTotals.people.toLocaleString("tr-TR")}</strong></span><span>Hesaba Esas<strong>{formatMinutes(payrollTotals.workedMinutes)}</strong></span><span>Normal<strong>{formatMinutes(payrollTotals.normalMinutes)}</strong></span><span>Resmî Tatil<strong>{formatMinutes(payrollTotals.holidayMinutes)}</strong></span><span>Fazla Mesai<strong>{formatMinutes(payrollTotals.overtimeMinutes)}</strong></span><span>İzin<strong>{formatMinutes(payrollTotals.leaveMinutes)}</strong></span></div>
      <div className="wfx-security-note"><CheckCircle2 size={18} />Bu tablo yalnız 11 saat üstünü değil, seçilen dönemde roster veya izin kaydı bulunan herkesi kapsar. Fazla mesai kişi/gün bazında resmî tatil hariç 7,5 saatin üstünden hesaplanır; roster ile çakışan izin günü OPEX hesabında çalışmadan düşer, ham net ayrıca korunur. Gece süresi mola zamanları bilinmediği için oransal yaklaşıktır.</div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Personel</th><th>Depo / Unvan</th><th>Vardiya / Gün</th><th>Ham Net</th><th>Hesaba Esas</th><th>Normal</th><th>Resmî</th><th>Gece</th><th>Fazla</th><th>İzin</th><th>Kontroller</th></tr></thead><tbody>{payrollRows.map((row) => <tr key={row.personId}><td><strong>{row.personName}</strong><small>İK: {row.personId} · Roster: {row.rosterIds}</small></td><td><strong>{row.warehouse}</strong><small>{row.title}</small></td><td><strong>{row.shiftCount} / {row.workedDays}</strong><small>{row.leaveDays} izin günü</small></td><td>{formatMinutes(row.rawMinutes)}</td><td><strong>{formatMinutes(row.workedMinutes)}</strong></td><td>{formatMinutes(row.normalMinutes)}</td><td className="wfx-purple">{formatMinutes(row.holidayMinutes)}</td><td>{formatMinutes(row.nightMinutes)}</td><td className={row.overtimeMinutes ? "wfx-purple" : ""}>{formatMinutes(row.overtimeMinutes)}</td><td><strong>{formatMinutes(row.leaveMinutes)}</strong><small>{row.leaveLabels}</small></td><td><span className={`wfx-status ${row.conflictDays || row.anomalyCount ? "warning" : "success"}`}>{row.conflictDays || row.anomalyCount ? "İnceleme" : "Temiz"}</span><small>{row.conflictDays} izin çakışması · {row.anomalyCount} adet 11 saat · {row.simulationCount} simülasyon</small></td></tr>)}</tbody></table></div>
    </> : null}

    {section === "norms" && rosterRows.length ? <>
      <div className="wfx-security-note"><UsersRound size={18} />Depo müdürü ve rider captain norm/headcount hesabına dahil edilmez. “Gereksiz mesai” sinyali, roster döneminde norm kadar picker görülmesine rağmen fazla mesai oluşmasıdır; nihai karar değildir.</div>
      <div className="wfx-table-wrap"><table className="wfx-table"><thead><tr><th>Regional Manager</th><th>BY / Regional Executive</th><th>Depo</th><th>Norm</th><th>Picker</th><th>Fark</th><th>Toplam</th><th>Resmî</th><th>Fazla</th><th>11 Saat</th><th>Yorum</th></tr></thead><tbody>{normAnalytics.map((row) => <tr key={row.id}><td>{permissions.manageNorms ? <input className="wfx-inline-input" value={row.regionalManager} onChange={(event) => updateNorm(row.id, { regionalManager: event.target.value })} /> : row.regionalManager}</td><td>{permissions.manageNorms ? <input className="wfx-inline-input" value={row.regionalExecutive} onChange={(event) => updateNorm(row.id, { regionalExecutive: event.target.value })} /> : row.regionalExecutive}</td><td><strong>{row.warehouse}</strong></td><td>{permissions.manageNorms ? <input className="wfx-inline-input number" type="number" value={row.norm} onChange={(event) => updateNorm(row.id, { norm: Number(event.target.value) })} /> : row.norm}</td><td>{row.headcount}</td><td className={row.gap < 0 ? "wfx-red" : ""}>{row.gap > 0 ? `+${row.gap}` : row.gap}</td><td>{formatMinutes(row.totalMinutes)}</td><td>{formatMinutes(row.holidayMinutes)}</td><td className={row.overtimeMinutes ? "wfx-purple" : ""}>{formatMinutes(row.overtimeMinutes)}</td><td>{row.anomalies}</td><td><span className={`wfx-status ${row.risk.includes("mesai") ? "warning" : row.risk === "Norm altı" ? "danger" : "success"}`}>{row.risk}</span></td></tr>)}</tbody></table></div>
    </> : null}
  </section>;
}
