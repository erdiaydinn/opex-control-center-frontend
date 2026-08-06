import * as XLSX from "xlsx";
import { normalizeWarehouseName, resolveHrWarehouse } from "./staffingNorms.js";

function safeNumber(value) {
  const normalized = String(value ?? "0").replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function timeText(value) {
  return String(value || "").slice(0, 5);
}

function dateToIso(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  const text = String(value || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const parts = text.split(/[./-]/);
  if (parts.length === 3) {
    if (parts[0].length === 4) return `${parts[0]}-${parts[1].padStart(2, "0")}-${parts[2].padStart(2, "0")}`;
    return `${parts[2]}-${parts[1].padStart(2, "0")}-${parts[0].padStart(2, "0")}`;
  }
  return "";
}

function enumerateDates(start, end) {
  const rows = [];
  const cursor = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  while (cursor <= last) {
    rows.push(dateToIso(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return rows;
}

export function parseDelimited(text, delimiter = null) {
  const clean = String(text || "").replace(/^\ufeff/, "");
  const separator = delimiter || (clean.slice(0, clean.indexOf("\n")).includes(";") ? ";" : ",");
  const matrix = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < clean.length; index += 1) {
    const char = clean[index];
    if (char === '"') {
      if (quoted && clean[index + 1] === '"') { cell += '"'; index += 1; }
      else quoted = !quoted;
    } else if (char === separator && !quoted) {
      row.push(cell.trim()); cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && clean[index + 1] === "\n") index += 1;
      row.push(cell.trim()); cell = "";
      if (row.some((value) => value !== "")) matrix.push(row);
      row = [];
    } else cell += char;
  }
  if (cell || row.length) { row.push(cell.trim()); matrix.push(row); }
  if (!matrix.length) return [];
  const headers = matrix.shift().map((value) => value.trim().toLocaleLowerCase("tr-TR"));
  return matrix.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

export async function parseRosterFile(file) {
  const text = await file.text();
  const sourceRows = parseDelimited(text);
  const rows = sourceRows.map((row, index) => {
    const grossMinutes = Math.round(safeNumber(row.toplam_calisma) / 60);
    const breakMinutes = Math.round(safeNumber(row.mola_sn) / 60);
    const netMinutes = Math.max(0, grossMinutes - breakMinutes);
    const holidayMinutes = Math.round(safeNumber(row.bayram_mesai_net_sn) / 60);
    const personId = String(row.picker_id || row.rider_id || row.employee_id || "").trim();
    const nationalId = String(row.tck || row.tc || row.tckn || row["tc kimlik no"] || "").replace(/\D/g, "");
    const date = dateToIso(row.shift_date);
    return {
      id: `ROSTER-${personId}-${date}-${index}`,
      sourceKey: `${personId}|${date}|${timeText(row.baslangic)}|${timeText(row.bitis)}`,
      warehouse: normalizeWarehouseName(row.vendor_name),
      date,
      personId,
      personName: String(row.rider_name || row.picker_name || row.name || "").trim(),
      nationalId,
      email: String(row.email || "").trim(),
      title: String(row.title || "").trim(),
      start: timeText(row.baslangic),
      end: timeText(row.bitis),
      grossMinutes,
      breakMinutes,
      netMinutes,
      holidayMinutes,
      normalMinutes: Math.max(0, netMinutes - holidayMinutes),
      overtimeMinutes: Math.max(0, netMinutes - holidayMinutes - 450),
      isActive: String(row.isactive) === "1",
      shiftState: row.shift_state_tr,
      contract: row.contract_name,
      holidayDetail: row.bayram_mesai_detay,
      anomaly: grossMinutes > 660 ? "11 saat üstü roster" : "",
      source: "Roster CSV",
    };
  }).filter((row) => row.personId && row.date);
  return {
    rows,
    summary: {
      total: rows.length,
      people: new Set(rows.map((row) => row.personId)).size,
      warehouses: new Set(rows.map((row) => row.warehouse)).size,
      managers: rows.filter((row) => row.title === "WAREHOUSE_MANAGER").length,
      anomalies: rows.filter((row) => row.anomaly).length,
    },
  };
}

const CATEGORY_TO_TYPE = {
  "yıllık izin": "annual",
  "ücretsiz izin": "unpaid",
  "ücretsiz": "unpaid",
  "babalık izni": "paternity",
  "babalık": "paternity",
  "evlilik izni": "marriage",
  "evlilik": "marriage",
  "yas izni": "bereavement",
  "yas": "bereavement",
  "hastalık izni (raporlu)": "report",
  "hastalık izni (iş kazası)": "work_accident",
  "iş kazası": "work_accident",
  "regl izni": "menstrual",
  "regl": "menstrual",
  "devamsızlık": "absence",
  "idari izin": "administrative",
  "idari": "administrative",
  "taşınma izni": "relocation",
  "taşınma": "relocation",
  "saha kahramanları günü": "fieldhero",
};

export async function parseTimeOffFile(file) {
  const bytes = await file.arrayBuffer();
  const workbook = XLSX.read(bytes, { type: "array", cellDates: true });
  const sheet = workbook.Sheets["Time Off Used"] || workbook.Sheets[workbook.SheetNames[0]];
  const sourceRows = XLSX.utils.sheet_to_json(sheet, { defval: "", raw: true });
  const rows = [];
  sourceRows.forEach((source, index) => {
    const personId = String(source["Employee Number"] || "").trim();
    const personName = String(source.Name || "").split(",").reverse().join(" ").trim();
    const category = String(source.Category || "").trim();
    const start = dateToIso(source.From);
    const end = dateToIso(source.To) || start;
    if (!personId || !start) return;
    enumerateDates(start, end).forEach((date) => {
      rows.push({
        id: `TO-${personId}-${date}-${index}`,
        personId,
        personName,
        category,
        typeId: CATEGORY_TO_TYPE[category.toLocaleLowerCase("tr-TR")] || `custom_${category.toLocaleLowerCase("tr-TR").replaceAll(/[^a-z0-9çğıöşü]+/g, "_")}`,
        date,
        minutes: 450,
        approval: "Onaylandı",
        note: source.Notes || category,
        requestedAt: dateToIso(source.Requested),
        approvedAt: dateToIso(source.Approved),
        source: "Time Off Used",
        sourceKey: `${personId}|${date}`,
      });
    });
  });
  return { rows, sourceCount: sourceRows.length };
}

export async function parseEmployeeFile(file) {
  let sourceRows;
  if (/\.xlsx?$/i.test(file.name)) {
    const bytes = await file.arrayBuffer();
    const workbook = XLSX.read(bytes, { type: "array", cellDates: true });
    sourceRows = XLSX.utils.sheet_to_json(workbook.Sheets[workbook.SheetNames[0]], { defval: "", raw: true });
  } else sourceRows = parseDelimited(await file.text());
  const normalizeHeader = (value) => String(value || "").toLocaleLowerCase("tr-TR").replaceAll("ı", "i").trim().replaceAll(/[_\s]+/g, " ");
  const get = (row, ...names) => {
    const keys = Object.keys(row);
    const normalizedNames = names.map(normalizeHeader);
    const found = keys.find((key) => normalizedNames.includes(normalizeHeader(key)));
    return found ? row[found] : "";
  };
  return sourceRows.map((row) => {
    const id = String(get(row, "employee id", "employee number", "personel id", "sicil no", "employee id sap") || "").trim();
    const name = String(get(row, "name", "employee name", "ad soyad", "personel adı", "personel adi") || "").trim();
    const nationalId = String(get(row, "national id", "tc", "tc kimlik no", "tc kimlik numarası", "tckn") || "").replace(/\D/g, "");
    const actualWarehouse = get(row, "actual warehouse", "actual warehouse name", "warehouse", "warehouse name", "depo", "depo adı", "depo adi", "vendor name", "dmart name used in hr");
    const explicitWarehouseCode = get(row, "hr warehouse code", "ik depo kodu", "ik kodu", "warehouse code", "depo kodu");
    const { warehouse, warehouseCode } = resolveHrWarehouse(actualWarehouse, explicitWarehouseCode);
    const role = String(get(row, "title", "unvan", "role", "job title") || "").trim();
    const hireDate = dateToIso(get(row, "hire date", "start date", "işe giriş tarihi", "ise giris tarihi", "giriş tarihi", "giris tarihi"));
    const terminationDate = dateToIso(get(row, "termination date", "exit date", "end date", "işten çıkış tarihi", "isten cikis tarihi", "çıkış tarihi", "cikis tarihi"));
    const email = String(get(row, "email", "e-posta", "eposta") || "").trim();
    const phone = String(get(row, "phone", "telefon", "telefon numarası", "telefon numarasi") || "").trim();
    const accountValue = String(get(row, "kullanıcı hesabı", "kullanici hesabi", "uygulama kullanıcısı", "uygulama kullanicisi", "create user", "app user") || "").trim().toLocaleLowerCase("tr-TR");
    const createUser = ["evet", "yes", "ja", "نعم", "true", "1", "x"].includes(accountValue);
    return {
      id, name, ...(nationalId ? { nationalId } : {}), ...(warehouse ? { warehouse } : {}), ...(warehouseCode ? { warehouseCode } : {}),
      ...(role ? { role } : {}), ...(hireDate ? { hireDate } : {}), ...(terminationDate ? { terminationDate, active: false } : {}),
      ...(email ? { email } : {}), ...(phone ? { phone } : {}), ...(createUser ? { createUser: true } : {}), sourceWarehouse: String(actualWarehouse || "").trim(),
    };
  }).filter((row) => row.id && row.name);
}

export async function parseRosterIdentityFile(file) {
  let sourceRows;
  if (/\.xlsx?$/i.test(file.name)) {
    const bytes = await file.arrayBuffer();
    const workbook = XLSX.read(bytes, { type: "array", cellDates: true });
    sourceRows = XLSX.utils.sheet_to_json(workbook.Sheets[workbook.SheetNames[0]], { defval: "", raw: true });
  } else sourceRows = parseDelimited(await file.text());
  const normalizeHeader = (value) => String(value || "").toLocaleLowerCase("tr-TR").replaceAll("ı", "i").trim().replaceAll(/[_\s]+/g, " ");
  const get = (row, ...names) => {
    const keys = Object.keys(row);
    const normalizedNames = names.map(normalizeHeader);
    const found = keys.find((key) => normalizedNames.includes(normalizeHeader(key)));
    return found ? row[found] : "";
  };
  return sourceRows.map((row) => {
    const rosterPersonId = String(get(row, "roster employee id", "roster id", "picker id", "rider id", "rider_id", "picker_id") || "").trim();
    const hrPersonId = String(get(row, "hr employee id", "ik employee id", "ik personel id", "sap employee id") || "").trim();
    const nationalId = String(get(row, "tck", "tc", "tckn", "national id", "tc kimlik no", "tc kimlik numarası") || "").replace(/\D/g, "");
    const rosterPersonName = String(get(row, "rider name", "rider_name", "picker name", "roster name", "ad soyad", "name") || "").trim();
    const email = String(get(row, "email", "e-posta", "eposta") || "").trim();
    const phone = String(get(row, "phone num", "phone_num", "phone", "telefon", "telefon numarası", "telefon numarasi") || "").trim();
    const contract = String(get(row, "contract name", "contract_name", "contract") || "").trim();
    const activeText = String(get(row, "isactive", "is active", "active", "aktif") || "").trim().toLocaleLowerCase("tr-TR");
    return { rosterPersonId, hrPersonId, nationalId, rosterPersonName, email, phone, contract, active: ["1", "true", "evet", "yes", "aktif"].includes(activeText) };
  }).filter((row) => row.rosterPersonId && (row.nationalId || row.hrPersonId || row.email));
}

export function maskNationalId(value) {
  const id = String(value || "").replace(/\D/g, "");
  if (!id) return "—";
  if (id.length <= 4) return id;
  return `${id.slice(0, 2)}${"*".repeat(Math.max(1, id.length - 4))}${id.slice(-2)}`;
}
