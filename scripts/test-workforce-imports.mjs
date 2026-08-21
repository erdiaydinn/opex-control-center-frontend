import assert from "node:assert/strict";
import * as XLSX from "xlsx";

import {
  normalizeHeader,
  normalizeNationalId,
  parseAttendanceFile,
  parseEmployeeFile,
  parseEmploymentLifecycleFile,
  parseRosterFile,
  parseTimeOffFile,
} from "../src/modules/workforce/workforceImporters.js";
import { resolveWorkforcePerson } from "../src/modules/workforce/workforceIdentity.js";

function workbookFile(name, sheetName, rows) {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(rows), sheetName);
  const bytes = XLSX.write(workbook, { type: "array", bookType: "xlsx" });
  return new File([bytes], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

assert.equal(normalizeHeader(" T.C. KİMLİK_NUMARASI "), "tc kimlik numarasi");
assert.equal(normalizeHeader("  Tc-KİMLİK / NO.  "), "tc kimlik no");
assert.equal(normalizeNationalId(10009717724), "10009717724");
assert.equal(normalizeNationalId("1.0009717724E+10"), "10009717724");

const people = [{ id: "HR-77", name: "Murat Işılı", nationalId: "10009717724", warehouse: "Fulya (İstanbul)", role: "Picker" }];

const employeeMaster = await parseEmployeeFile(workbookFile("personel.xlsx", "Personel Ana Veri", [{
  "eMpLoYeE___NuMbEr": "HR-77",
  "Roster ID": "ROSTER-998",
  "T.C. KİMLİK NUMARASI": "10009717724",
  "Ad Soyad": "Murat Işılı",
  "İşe Giriş Tarihi": "01.04.2025",
  "İşten Çıkış Tarihi": "",
}]));
assert.deepEqual(employeeMaster[0].rosterIds, ["ROSTER-998"]);
assert.equal(employeeMaster[0].id, "HR-77");
assert.equal(employeeMaster[0].hireDate, "2025-04-01");
assert.equal(resolveWorkforcePerson({ sourcePersonId: "ROSTER-998" }, employeeMaster).person.id, "HR-77");
assert.equal(resolveWorkforcePerson({ sourcePersonId: "ROSTER-998" }, employeeMaster).method, "Roster ID");

const hostileHeaders = await parseEmployeeFile(workbookFile("hostile.xlsx", "People", [{
  " SİCİL---NUMARASI ": "HR-88",
  "tC_kİmLiK--No": "10009717725",
  "PERSONEL   ADI": "Kolon Testi",
  "DEPO___ADI": "Fulya (İstanbul)",
} ]));
assert.equal(hostileHeaders[0].id, "HR-88");
assert.equal(hostileHeaders[0].nationalId, "10009717725");

const timeOff = await parseTimeOffFile(workbookFile("izin.xlsx", "Time Off Used", [{
  "Employee Number": "27057",
  "T.C. KİMLİK NUMARASI": 10009717724,
  NAME: "IŞILI, Murat",
  CATEGORY: "Hastalık İzni (Raporlu)",
  FROM: new Date(2026, 6, 28),
  TO: new Date(2026, 7, 3),
}]));
assert.equal(timeOff.rows.length, 7);
assert.equal(timeOff.rows[0].nationalId, "10009717724");
assert.equal(timeOff.rows[0].sourcePersonId, "");
assert.equal(timeOff.rows[0].typeId, "report");
assert.equal(resolveWorkforcePerson(timeOff.rows[0], people).person.id, "HR-77");
assert.equal(resolveWorkforcePerson(timeOff.rows[0], people).method, "TC");

const dmTimeOff = await parseTimeOffFile(workbookFile("dm-izin.xlsx", "DM Time Off", [
  {
    TCKN: "53917234228",
    "Employee ID": "2021-11-0092",
    Worker: "Alper Sezen",
    "Time off Type": "TUR Annual Leave - Yıllık İzin",
    "Time Off Date": "01.06.2026",
  },
  {
    TCKN: "69658132178",
    "Employee ID": "2021-12-6341",
    Worker: "Hasan Koca",
    "Time off Type": "TUR Sick Leave (w.o notice) - Hastalık İzni (Raporlu)",
    "Time Off Date": "05.06.2026",
  },
]));
assert.equal(dmTimeOff.rows.length, 2);
assert.equal(dmTimeOff.invalidCount, 0);
assert.deepEqual(dmTimeOff.rows.map((row) => row.typeId), ["annual", "report"]);
assert.deepEqual(dmTimeOff.rows.map((row) => row.date), ["2026-06-01", "2026-06-05"]);
assert.equal(dmTimeOff.rows[0].personName, "Alper Sezen");
assert.equal(dmTimeOff.rows[0].sourcePersonId, "2021-11-0092");
assert.equal(dmTimeOff.rows[0].nationalId, undefined);
assert.equal(dmTimeOff.rows[0].minutes, 0);
assert.equal(dmTimeOff.rows[0].source, "DM Time Off");

const lifecycle = await parseEmploymentLifecycleFile(workbookFile("giris-cikis.xlsx", "Personel", [{
  "KİMLİK NO": "10009717724",
  "İŞE GİRİŞ TARİHİ": new Date(2025, 3, 1),
  "İŞTEN ÇIKIŞ TARİHİ": new Date(2026, 7, 31),
}]));
assert.deepEqual(lifecycle.map(({ hireDate, terminationDate }) => ({ hireDate, terminationDate })), [{ hireDate: "2025-04-01", terminationDate: "2026-08-31" }]);

const attendance = await parseAttendanceFile(workbookFile("puantaj.xlsx", "Puantaj", [{
  TC: 10009717724,
  SHIFT_DATE: "15.07.2026",
  "Günlük Toplam": "8:45:00",
  "Günlük Mola": "1:00:00",
  "Günlük Mesai": "0:15:00",
}]));
assert.equal(attendance.rows[0].netMinutes, 465);
assert.equal(attendance.rows[0].expectedMinutes, 450);
assert.equal(resolveWorkforcePerson(attendance.rows[0], people).person.id, "HR-77");

const rosterWorkbook = XLSX.utils.book_new();
const rosterSheet = XLSX.utils.json_to_sheet([{
  picker_id: "40382",
  TC: "10888862898",
  rider_name: "CİHAN ATİK",
  vendor_name: "Yenikent (İstanbul)",
  shift_date: "05.07.2026",
  "Günlük Toplam": 26 / 24,
  "Günlük Mola": 1 / 24,
  "Günlük Mesai": 17.5 / 24,
}]);
rosterSheet.F2.z = "[h]:mm:ss";
rosterSheet.G2.z = "[h]:mm:ss";
rosterSheet.H2.z = "[h]:mm:ss";
XLSX.utils.book_append_sheet(rosterWorkbook, rosterSheet, "Roster");
const rosterBytes = XLSX.write(rosterWorkbook, { type: "array", bookType: "xlsx" });
const roster = await parseRosterFile(new File([rosterBytes], "roster.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
assert.equal(roster.rows[0].grossMinutes, 1560);
assert.equal(roster.rows[0].breakMinutes, 60);
assert.equal(roster.rows[0].netMinutes, 1500);
assert.equal(roster.rows[0].varianceMinutes, 1050);
assert.equal(roster.rows[0].anomaly, "11 saat üstü roster");
assert.equal(roster.summary.anomalies, 1);

const legacyRoster = await parseRosterFile(workbookFile("legacy-roster.xlsx", "Roster", [
  { picker_id: "1", shift_date: "05.07.2026", toplam_calisma: 11 * 3600, mola_sn: 0 },
  { picker_id: "2", shift_date: "05.07.2026", toplam_calisma: 11 * 3600 + 60, mola_sn: 0 },
]));
assert.equal(legacyRoster.rows[0].anomaly, "");
assert.equal(legacyRoster.rows[1].anomaly, "11 saat üstü roster");
assert.equal(legacyRoster.summary.anomalies, 1);

const ambiguous = resolveWorkforcePerson({ nationalId: "10009717724" }, [...people, { ...people[0], id: "HR-88" }]);
assert.equal(ambiguous.status, "Belirsiz");

console.log("workforce import tests passed");
