import * as XLSX from "xlsx";
import { normalizeWarehouseName, resolveHrWarehouse } from "./staffingNorms.js";

function safeNumber(value) {
  const normalized = String(value ?? "0").replace(",", ".");
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function normalizeHeader(value = "") {
  return String(value)
    .trim()
    .toLocaleLowerCase("tr-TR")
    .replaceAll("ı", "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/^t c k n(?= |$)/, "tckn")
    .replace(/^t c(?= |$)/, "tc");
}

export function normalizeNationalId(value = "") {
  if (typeof value === "number" && Number.isFinite(value)) return String(Math.trunc(value));
  const text = String(value ?? "").trim();
  if (/^\d+(?:[.,]\d+)?e\+?\d+$/i.test(text)) {
    const numeric = Number(text.replace(",", "."));
    if (Number.isSafeInteger(numeric)) return String(numeric);
  }
  return text.replace(/\D/g, "");
}

function cell(row, ...aliases) {
  const accepted = new Set(aliases.map(normalizeHeader));
  const wantsNationalId = [...accepted].some((name) => ["tc", "tck", "tckn", "national id", "national identity number"].includes(name) || name.includes("kimlik"));
  const found = Object.keys(row || {}).find((key) => {
    const normalized = normalizeHeader(key);
    if (accepted.has(normalized)) return true;
    return wantsNationalId && (
      /^(tc|tck|tckn)$/.test(normalized) ||
      (normalized.includes("kimlik") && /(^| )(no|numara|number)( |$)/.test(normalized)) ||
      normalized.includes("national identity") ||
      normalized.includes("citizen id")
    );
  });
  return found == null ? "" : row[found];
}

async function readTabularFile(file, preferredSheet = "") {
  if (/\.xlsx?$/i.test(file.name)) {
    const bytes = await file.arrayBuffer();
    const workbook = XLSX.read(bytes, { type: "array", cellDates: false });
    const sheet = (preferredSheet && workbook.Sheets[preferredSheet]) || workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json(sheet, { defval: "", raw: true });
  }
  return parseDelimited(await file.text());
}

function timeText(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return `${String(value.getHours()).padStart(2, "0")}:${String(value.getMinutes()).padStart(2, "0")}`;
  if (typeof value === "number" && Number.isFinite(value) && value >= 0 && value < 2) {
    const minutes = Math.round(value * 1440) % 1440;
    return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
  }
  const match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})/);
  return match ? `${String(Number(match[1])).padStart(2, "0")}:${match[2]}` : "";
}

function dateToIso(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    const parsed = XLSX.SSF.parse_date_code(value);
    if (!parsed || !parsed.y || !parsed.m || !parsed.d) return "";
    const month = String(parsed.m).padStart(2, "0");
    const day = String(parsed.d).padStart(2, "0");
    return `${parsed.y}-${month}-${day}`;
  }
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
  const sourceRows = await readTabularFile(file);
  const rows = sourceRows.map((row, index) => {
    const grossSeconds = cell(row, "toplam_calisma", "toplam çalışma saniye", "total work seconds");
    const breakSeconds = cell(row, "mola_sn", "mola sn", "break seconds");
    const grossMinutes = grossSeconds !== ""
      ? Math.round(safeNumber(grossSeconds) / 60)
      : durationMinutes(cell(row, "günlük toplam", "gunluk toplam", "daily total", "total work", "toplam çalışma", "toplam sure", "toplam süre"));
    const breakMinutes = breakSeconds !== ""
      ? Math.round(safeNumber(breakSeconds) / 60)
      : durationMinutes(cell(row, "günlük mola", "gunluk mola", "break", "break duration", "mola", "mola süresi"));
    const varianceMinutes = durationMinutes(cell(row, "günlük mesai", "gunluk mesai", "overtime", "mesai", "fazla mesai", "fark"), true);
    const netMinutes = Math.max(0, grossMinutes - breakMinutes);
    const holidayMinutes = Math.round(safeNumber(cell(row, "bayram_mesai_net_sn", "bayram mesai net sn")) / 60);
    const personId = String(cell(row, "picker_id", "picker id", "rider_id", "rider id", "employee_id", "employee id", "employee number") || "").trim();
    const nationalId = normalizeNationalId(cell(row, "tck", "tc", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası", "national id", "national identity number"));
    const date = dateToIso(cell(row, "shift_date", "shift date", "vardiya tarihi", "tarih", "date"));
    return {
      id: `ROSTER-${personId}-${date}-${index}`,
      sourceKey: `${personId}|${date}|${timeText(row.baslangic)}|${timeText(row.bitis)}`,
      warehouse: normalizeWarehouseName(cell(row, "vendor_name", "vendor name", "warehouse", "warehouse name", "depo", "depo adı")),
      date,
      personId,
      personName: String(cell(row, "rider_name", "rider name", "picker_name", "picker name", "name", "ad soyad") || "").trim(),
      nationalId,
      email: String(cell(row, "email", "e posta", "eposta") || "").trim(),
      title: String(cell(row, "title", "unvan", "role", "job title") || "").trim(),
      start: timeText(cell(row, "baslangic", "başlangıç", "start", "check in", "giriş saati")),
      end: timeText(cell(row, "bitis", "bitiş", "end", "check out", "çıkış saati")),
      grossMinutes,
      breakMinutes,
      netMinutes,
      varianceMinutes,
      holidayMinutes,
      normalMinutes: Math.max(0, netMinutes - holidayMinutes),
      overtimeMinutes: Math.max(0, netMinutes - holidayMinutes - 450),
      isActive: String(cell(row, "isactive", "is active", "aktif")) === "1",
      shiftState: cell(row, "shift_state_tr", "shift state tr", "vardiya durumu"),
      contract: cell(row, "contract_name", "contract name", "contract"),
      holidayDetail: cell(row, "bayram_mesai_detay", "bayram mesai detay"),
      anomaly: netMinutes > 660 ? "11 saat üstü roster" : "",
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
  "annual leave": "annual",
  "yıllık izin": "annual",
  "unpaid leave": "unpaid",
  "ücretsiz izin": "unpaid",
  "ücretsiz": "unpaid",
  "paternity leave": "paternity",
  "babalık izni": "paternity",
  "babalık": "paternity",
  "marriage leave": "marriage",
  "evlilik izni": "marriage",
  "evlilik": "marriage",
  "bereavement leave": "bereavement",
  "yas izni": "bereavement",
  "yas": "bereavement",
  "sick leave": "report",
  "hastalık izni": "report",
  "raporlu": "report",
  "work accident": "work_accident",
  "iş kazası": "work_accident",
  "menstrual leave": "menstrual",
  "regl izni": "menstrual",
  "regl": "menstrual",
  "absence": "absence",
  "devamsızlık": "absence",
  "administrative leave": "administrative",
  "idari izin": "administrative",
  "idari": "administrative",
  "relocation leave": "relocation",
  "taşınma izni": "relocation",
  "taşınma": "relocation",
  "saha kahramanları günü": "fieldhero",
};

function resolveTimeOffType(category = "") {
  const normalized = String(category).trim().toLocaleLowerCase("tr-TR");
  if (CATEGORY_TO_TYPE[normalized]) return CATEGORY_TO_TYPE[normalized];
  const alias = Object.keys(CATEGORY_TO_TYPE)
    .sort((left, right) => right.length - left.length)
    .find((candidate) => normalized.includes(candidate));
  if (alias) return CATEGORY_TO_TYPE[alias];
  const custom = normalized.replaceAll(/[^a-z0-9çğıöşü]+/g, "_").replace(/^_+|_+$/g, "");
  return custom ? `custom_${custom}` : "custom_unknown";
}

async function parseTimeOffFileLocal(file) {
  const sourceRows = await readTabularFile(file, "Time Off Used");
  const rows = [];
  let invalidCount = 0;
  sourceRows.forEach((source, index) => {
    const personId = String(cell(source, "employee number", "employee no", "employee id", "hr employee id", "personel id", "sicil no", "sicil numarası", "sap id") || "").trim();
    const rawNationalId = normalizeNationalId(cell(source, "tc", "tck", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası", "national id", "national identity number"));
    const rawName = String(cell(source, "name", "worker", "employee name", "ad soyad", "personel adı", "personel adi") || "").trim();
    const personName = rawName.includes(",") ? rawName.split(",").reverse().join(" ").trim() : rawName;
    const category = String(cell(source, "category", "leave category", "izin türü", "izin tipi", "time off type") || "").trim();
    const singleDateValue = cell(source, "time off date", "leave date", "izin tarihi");
    const singleDate = dateToIso(singleDateValue);
    const start = singleDate || dateToIso(cell(source, "from", "start", "start date", "başlangıç", "başlangıç tarihi", "izin başlangıç"));
    const end = singleDate || dateToIso(cell(source, "to", "end", "end date", "bitiş", "bitiş tarihi", "izin bitiş")) || start;
    const isDmSingleDate = Boolean(singleDate && personId);
    const nationalId = isDmSingleDate ? "" : rawNationalId;
    const sourcePersonId = nationalId.length === 11 ? "" : personId;
    if ((!personId && nationalId.length !== 11) || !start || !category) { invalidCount += 1; return; }
    const explicitMinutes = durationMinutes(cell(source, "leave minutes", "time off minutes", "izin dakika", "süre dakika"));
    const explicitHours = safeNumber(cell(source, "leave hours", "time off hours", "izin saati", "izin saat"));
    const leaveMinutes = explicitMinutes || (explicitHours > 0 ? Math.round(explicitHours * 60) : 0);
    enumerateDates(start, end).forEach((date) => {
      rows.push({
        id: `TO-${personId || "TC"}-${date}-${index}`,
        personId,
        sourcePersonId,
        ...(nationalId ? { nationalId } : {}),
        personName,
        category,
        typeId: resolveTimeOffType(category),
        date,
        minutes: leaveMinutes,
        approval: "Onaylandı",
        note: cell(source, "notes", "note", "not", "açıklama") || category,
        requestedAt: dateToIso(cell(source, "requested", "request date", "talep tarihi")),
        approvedAt: dateToIso(cell(source, "approved", "approval date", "onay tarihi")),
        source: isDmSingleDate ? "DM Time Off" : "Time Off Used",
        sourceKey: `${personId || "TC"}|${date}`,
      });
    });
  });
  return { rows, sourceCount: sourceRows.length, invalidCount, parser: "node-test-local" };
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + chunkSize, bytes.length)));
  }
  return btoa(binary);
}

export async function parseTimeOffFile(file) {
  // Node-based unit tests keep the deterministic local parser. Browser runtime
  // always delegates untrusted XLSX/CSV parsing to the authenticated backend.
  if (typeof window === "undefined" || typeof btoa === "undefined") return parseTimeOffFileLocal(file);
  const { apiPost } = await import("../../api/client.js");
  const bytes = new Uint8Array(await file.arrayBuffer());
  const parsed = await apiPost("/workforce/time-off/parse", {
    file_name: file.name,
    content_base64: bytesToBase64(bytes),
  });
  return {
    rows: (parsed.rows || []).map((row) => ({
      id: row.id,
      personId: String(row.person_id || ""),
      sourcePersonId: String(row.source_person_id || ""),
      personName: row.person_name || "",
      category: row.category || "",
      typeId: row.type_id || "custom_unknown",
      date: row.date,
      minutes: Number(row.minutes || 0),
      approval: row.approval || "Onaylandı",
      note: row.note || "",
      requestedAt: row.requested_at || "",
      approvedAt: row.approved_at || "",
      source: row.source || "Time Off Used",
      sourceKey: row.source_key || `${row.person_id || ""}|${row.date || ""}`,
      identityMethod: row.identity_method || "",
      identityResolution: row.identity_resolution || "",
    })),
    sourceCount: Number(parsed.source_count || 0),
    invalidCount: Number(parsed.invalid_count || 0),
    identityResolvedCount: Number(parsed.identity_resolved_count || 0),
    identityUnmatchedCount: Number(parsed.identity_unmatched_count || 0),
    sensitiveOnlyUnmatchedCount: Number(parsed.sensitive_only_unmatched_count || 0),
    parser: parsed.parser || "secure-server-timeoff-v1",
    rawNationalIdReturned: parsed.raw_national_id_returned === true,
  };
}

export async function parseEmployeeFile(file) {
  const sourceRows = await readTabularFile(file);
  return sourceRows.map((row) => {
    const id = String(cell(row, "employee id", "employee number", "employee no", "personel id", "sicil no", "sicil numarası", "employee id sap", "sap id") || "").trim();
    const rosterIds = String(cell(row, "roster id", "rooster id", "roster employee id", "rooster employee id", "rider id", "rider_id", "picker id", "picker_id") || "")
      .split(/[,;|\n]+/).map((value) => value.trim()).filter(Boolean);
    const name = String(cell(row, "name", "employee name", "ad soyad", "personel adı", "personel adi") || "").trim();
    const nationalId = normalizeNationalId(cell(row, "national id", "national identity number", "tc", "tck", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası"));
    const actualWarehouse = cell(row, "actual warehouse", "actual warehouse name", "warehouse", "warehouse name", "depo", "depo adı", "depo adi", "vendor name", "dmart name used in hr");
    const explicitWarehouseCode = cell(row, "hr warehouse code", "ik depo kodu", "ik kodu", "warehouse code", "depo kodu");
    const { warehouse, warehouseCode } = resolveHrWarehouse(actualWarehouse, explicitWarehouseCode);
    const role = String(cell(row, "title", "unvan", "role", "job title") || "").trim();
    const hireDate = dateToIso(cell(row, "hire date", "employment start date", "start date", "işe giriş tarihi", "ise giris tarihi", "giriş tarihi", "giris tarihi"));
    const terminationDate = dateToIso(cell(row, "termination date", "employment end date", "exit date", "leaving date", "end date", "işten çıkış tarihi", "isten cikis tarihi", "çıkış tarihi", "cikis tarihi", "ayrılış tarihi"));
    const email = String(cell(row, "email", "e-posta", "eposta") || "").trim();
    const phone = String(cell(row, "phone", "telefon", "telefon numarası", "telefon numarasi") || "").trim();
    const accountValue = String(cell(row, "kullanıcı hesabı", "kullanici hesabi", "uygulama kullanıcısı", "uygulama kullanicisi", "create user", "app user") || "").trim().toLocaleLowerCase("tr-TR");
    const createUser = ["evet", "yes", "ja", "نعم", "true", "1", "x"].includes(accountValue);
    return {
      id, name, ...(rosterIds.length ? { rosterIds: [...new Set(rosterIds)] } : {}), ...(nationalId ? { nationalId } : {}), ...(warehouse ? { warehouse } : {}), ...(warehouseCode ? { warehouseCode } : {}),
      ...(role ? { role } : {}), ...(hireDate ? { hireDate } : {}), ...(terminationDate ? { terminationDate, active: false } : {}),
      ...(email ? { email } : {}), ...(phone ? { phone } : {}), ...(createUser ? { createUser: true } : {}), sourceWarehouse: String(actualWarehouse || "").trim(),
    };
  }).filter((row) => (row.id || row.nationalId?.length === 11) && row.name);
}

export async function parseEmploymentLifecycleFile(file) {
  const sourceRows = await readTabularFile(file);
  return sourceRows.map((row, index) => ({
    sourceRow: index + 2,
    personId: String(cell(row, "employee id", "employee number", "employee no", "personel id", "sicil no", "sicil numarası", "sap id") || "").trim(),
    nationalId: normalizeNationalId(cell(row, "tc", "tck", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası", "national id", "national identity number")),
    personName: String(cell(row, "name", "employee name", "ad soyad", "personel adı", "personel adi") || "").trim(),
    hireDate: dateToIso(cell(row, "hire date", "employment start date", "start date", "işe giriş tarihi", "ise giris tarihi", "giriş tarihi", "giris tarihi")),
    terminationDate: dateToIso(cell(row, "termination date", "employment end date", "exit date", "leaving date", "end date", "işten çıkış tarihi", "isten cikis tarihi", "çıkış tarihi", "cikis tarihi", "ayrılış tarihi")),
  })).filter((row) => (row.personId || row.nationalId.length === 11) && (row.hireDate || row.terminationDate));
}

export async function parseRosterIdentityFile(file) {
  const sourceRows = await readTabularFile(file);
  return sourceRows.map((row) => {
    const rosterPersonId = String(cell(row, "roster employee id", "roster id", "picker id", "rider id", "rider_id", "picker_id") || "").trim();
    const hrPersonId = String(cell(row, "hr employee id", "ik employee id", "ik personel id", "sap employee id", "employee number") || "").trim();
    const nationalId = normalizeNationalId(cell(row, "tck", "tc", "tckn", "national id", "national identity number", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası"));
    const rosterPersonName = String(cell(row, "rider name", "rider_name", "picker name", "roster name", "ad soyad", "name") || "").trim();
    const email = String(cell(row, "email", "e-posta", "eposta") || "").trim();
    const phone = String(cell(row, "phone num", "phone_num", "phone", "telefon", "telefon numarası", "telefon numarasi") || "").trim();
    const contract = String(cell(row, "contract name", "contract_name", "contract") || "").trim();
    const activeText = String(cell(row, "isactive", "is active", "active", "aktif") || "").trim().toLocaleLowerCase("tr-TR");
    return { rosterPersonId, hrPersonId, nationalId, rosterPersonName, email, phone, contract, active: ["1", "true", "evet", "yes", "aktif"].includes(activeText) };
  }).filter((row) => row.rosterPersonId && (row.nationalId || row.hrPersonId || row.email));
}

function durationMinutes(value, allowSigned = false) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    // SheetJS may materialize an Excel duration as a date near its epoch.
    // The full serial-day distance preserves values above 24 hours (26:00, etc.).
    if (value.getUTCFullYear() < 1910) {
      const excelEpoch = Date.UTC(1899, 11, 30);
      const localDateAtUtc = Date.UTC(value.getFullYear(), value.getMonth(), value.getDate());
      const dayMinutes = Math.round((localDateAtUtc - excelEpoch) / 60000);
      return dayMinutes + value.getHours() * 60 + value.getMinutes() + Math.round(value.getSeconds() / 60);
    }
    return value.getHours() * 60 + value.getMinutes();
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    if (Math.abs(value) < 2) return Math.round(value * 1440);
    return Math.round(value);
  }
  const text = String(value ?? "").trim();
  if (!text) return 0;
  const sign = allowSigned && text.startsWith("-") ? -1 : 1;
  const cleaned = text.replace(/^[+-]/, "");
  const match = cleaned.match(/^(\d{1,3}):(\d{2})(?::(\d{2}))?$/);
  if (match) return sign * (Number(match[1]) * 60 + Number(match[2]) + Math.round(Number(match[3] || 0) / 60));
  return sign * Math.round(safeNumber(cleaned) * 60);
}

export async function parseAttendanceFile(file) {
  const sourceRows = await readTabularFile(file);
  const rows = sourceRows.map((source, index) => {
    const sourcePersonId = String(cell(source, "employee number", "employee id", "employee no", "personel id", "sicil no", "picker id", "picker_id", "rider id", "rider_id") || "").trim();
    const nationalId = normalizeNationalId(cell(source, "tc", "tck", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası", "national id", "national identity number"));
    const date = dateToIso(cell(source, "shift date", "shift_date", "date", "tarih", "vardiya tarihi", "çalışma tarihi"));
    const checkIn = timeText(cell(source, "check in", "check_in", "giriş", "giriş saati", "ilk giriş", "başlangıç", "baslangic"));
    const checkOut = timeText(cell(source, "check out", "check_out", "çıkış", "çıkış saati", "son çıkış", "bitiş", "bitis"));
    const grossMinutes = durationMinutes(cell(source, "günlük toplam", "gunluk toplam", "daily total", "total work", "toplam çalışma", "toplam sure", "toplam süre"));
    const breakMinutes = durationMinutes(cell(source, "günlük mola", "gunluk mola", "break", "break duration", "mola", "mola süresi"));
    const varianceMinutes = durationMinutes(cell(source, "günlük mesai", "gunluk mesai", "overtime", "mesai", "fazla mesai", "fark"), true);
    const netMinutes = Math.max(0, grossMinutes - breakMinutes);
    const expectedMinutes = Math.max(0, netMinutes - varianceMinutes);
    return {
      sourceRow: index + 2, sourcePersonId, nationalId, date, checkIn, checkOut, grossMinutes, breakMinutes, netMinutes,
      expectedMinutes, varianceMinutes,
      personName: String(cell(source, "name", "employee name", "ad soyad", "rider name", "rider_name", "picker name") || "").trim(),
      warehouse: normalizeWarehouseName(cell(source, "vendor name", "vendor_name", "warehouse", "warehouse name", "depo", "depo adı")),
      title: String(cell(source, "title", "unvan", "role", "job title") || "").trim(),
      errorStatus: String(cell(source, "hata durumu", "error status", "error", "hata") || "").trim(),
    };
  }).filter((row) => (row.sourcePersonId || row.nationalId.length === 11) && row.date && ((row.checkIn && row.checkOut) || row.grossMinutes > 0));
  return { rows, sourceCount: sourceRows.length };
}

export function maskNationalId(value) {
  const id = normalizeNationalId(value);
  if (!id) return "—";
  if (id.length <= 4) return id;
  return `${id.slice(0, 2)}${"*".repeat(Math.max(1, id.length - 4))}${id.slice(-2)}`;
}
