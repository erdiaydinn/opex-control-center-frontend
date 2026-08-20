import * as XLSX from "xlsx";

import { normalizeHeader, normalizeNationalId } from "../workforce/workforceImporters.js";
import { normalizeWarehouseName } from "../workforce/staffingNorms.js";


function cell(row, ...aliases) {
  const accepted = new Set(aliases.map(normalizeHeader));
  const key = Object.keys(row || {}).find((value) => accepted.has(normalizeHeader(value)));
  return key == null ? "" : row[key];
}

function decimal(value, fallback = 1) {
  const parsed = Number(String(value ?? "").trim().replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function activeValue(value) {
  const text = String(value ?? "").trim().toLocaleLowerCase("tr-TR");
  if (!text) return true;
  if (["0", "false", "no", "hayır", "hayir", "inactive", "pasif", "terminated", "ayrıldı", "ayrildi"].includes(text)) return false;
  return true;
}

async function rowsFromFile(file) {
  let workbook;
  if (/\.xlsx?$/i.test(file.name)) {
    workbook = XLSX.read(await file.arrayBuffer(), { type: "array", cellDates: false });
  } else {
    workbook = XLSX.read(await file.text(), { type: "string", cellDates: false });
  }
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  return XLSX.utils.sheet_to_json(sheet, { defval: "", raw: true });
}

export async function parseRecruitmentHrActualFile(file) {
  const sourceRows = await rowsFromFile(file);
  const rows = sourceRows.map((row) => {
    const employeeId = String(cell(
      row,
      "employee id", "employee number", "employee no", "hr employee id", "personel id",
      "sicil no", "sicil numarası", "sap id", "worker id",
    ) || "").trim();
    const tckn = normalizeNationalId(cell(
      row,
      "tckn", "tck", "tc", "tc kimlik no", "tc kimlik numarası", "national id", "national identity number",
    ));
    const warehouse = normalizeWarehouseName(cell(
      row,
      "warehouse", "warehouse name", "depo", "depo adı", "depo adi", "store", "store name",
      "location", "lokasyon", "vendor", "vendor name",
    ));
    const position = String(cell(
      row,
      "position", "position name", "job title", "title", "role", "unvan", "ünvan", "contract name",
    ) || "").trim();
    const fte = decimal(cell(row, "fte", "fte value", "full time equivalent", "fte oranı", "fte orani"), 1);
    const active = activeValue(cell(row, "active", "is active", "isactive", "status", "employee status", "aktif", "durum"));
    return {
      employee_id: employeeId || null,
      tckn: tckn.length === 11 ? tckn : null,
      warehouse,
      position,
      fte: Math.max(0, Math.min(2, fte)),
      active,
    };
  }).filter((row) => (row.employee_id || row.tckn) && row.warehouse);

  return {
    rows,
    sourceCount: sourceRows.length,
    ignoredCount: Math.max(0, sourceRows.length - rows.length),
  };
}
