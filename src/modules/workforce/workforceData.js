import { DEFAULT_STAFFING_NORMS } from "./staffingNorms.js";
import { generateTurkeyHolidays } from "./turkeyHolidays.js";

export const WORKFORCE_STORAGE_KEY = "opex_workforce_live_v3";
const LEGACY_STORAGE_KEY = "opex_workforce_live_v2";

export const people = [
  { id: "100184", name: "Erdi Aydın", nationalId: "", role: "Picker", warehouse: "Fulya (İstanbul)", manager: "Fulya Müdürü", hireDate: "2025-01-01", terminationDate: "", active: true },
  { id: "100221", name: "Efe Yılmaz", nationalId: "", role: "Picker", warehouse: "Fulya (İstanbul)", manager: "Fulya Müdürü", hireDate: "2025-01-01", terminationDate: "", active: true },
  { id: "100287", name: "Kerim Atayolu", nationalId: "", role: "Picker", warehouse: "Üsküdar (İstanbul)", manager: "Üsküdar Müdürü", hireDate: "2025-01-01", terminationDate: "", active: true },
  { id: "100344", name: "Çağrı Ayan", nationalId: "", role: "Picker", warehouse: "Şeref (Ankara)", manager: "Şeref Müdürü", hireDate: "2026-07-13", terminationDate: "", active: true },
  { id: "100415", name: "Emrecan Alver", nationalId: "", role: "Picker", warehouse: "Şemsettin Günaltay (İstanbul)", manager: "Şemsettin Müdürü", hireDate: "2025-01-01", terminationDate: "", active: true },
];

export const warehouses = [
  { id: "fulya", name: "Fulya (İstanbul)", code: "FUL", region: "İstanbul Avrupa", address: "Fulya, İstanbul", latitude: 41.0572, longitude: 28.9973, radius: 120, accuracy: 50, method: "Konum + cihaz", qrEnabled: false, status: "Aktif" },
  { id: "uskudar", name: "Üsküdar (İstanbul)", code: "USK", region: "İstanbul Anadolu", address: "Üsküdar, İstanbul", latitude: 41.0258, longitude: 29.0157, radius: 100, accuracy: 45, method: "Konum + cihaz", qrEnabled: false, status: "Aktif" },
  { id: "semt", name: "Şemsettin Günaltay (İstanbul)", code: "SGU", region: "İstanbul Anadolu", address: "Kadıköy, İstanbul", latitude: 40.9791, longitude: 29.0877, radius: 140, accuracy: 55, method: "Konum + cihaz", qrEnabled: false, status: "Aktif" },
  { id: "seref", name: "Şeref (Ankara)", code: "SRF", region: "İç Anadolu", address: "Ankara", latitude: 39.9334, longitude: 32.8597, radius: 120, accuracy: 50, method: "Konum + cihaz", qrEnabled: false, status: "Aktif" },
];

export const rules = [
  { id: "dailyMax", engineKey: "dailyMax", title: "Günlük azami net çalışma", value: 660, unit: "dakika", level: "Sert blok", active: true, effectiveFrom: "2026-01-01", note: "Yeni görev durur; gerçek çıkış saati kesilmez." },
  { id: "weeklyNormal", engineKey: "weeklyNormal", title: "Haftalık normal çalışma", value: 2700, unit: "dakika", level: "Bordro", active: true, effectiveFrom: "2026-01-01", note: "Üzeri fazla çalışma hesabına girer." },
  { id: "annualOvertime", engineKey: "annualOvertime", title: "Yıllık fazla çalışma", value: 16200, unit: "dakika", level: "Kritik", active: true, effectiveFrom: "2026-01-01", note: "Yaklaşım uyarısı ve İK eskalasyonu üretir." },
  { id: "betweenShifts", engineKey: "betweenShifts", title: "Vardiyalar arası dinlenme", value: 660, unit: "dakika", level: "Sert blok", active: true, effectiveFrom: "2026-01-01", note: "Yetersiz dinlenmede yeni check-in engellenir." },
  { id: "breakShort", engineKey: "breakShort", title: "0–4 saat çalışma molası", value: 15, unit: "dakika", level: "Otomatik", active: true, effectiveFrom: "2026-01-01", note: "Asgari mola hakedişi." },
  { id: "breakMedium", engineKey: "breakMedium", title: "4–7,5 saat çalışma molası", value: 30, unit: "dakika", level: "Otomatik", active: true, effectiveFrom: "2026-01-01", note: "Asgari mola hakedişi." },
  { id: "breakLong", engineKey: "breakLong", title: "7,5 saat üzeri çalışma molası", value: 60, unit: "dakika", level: "Otomatik", active: true, effectiveFrom: "2026-01-01", note: "Mola başlangıç ve bitişi kaydedilir." },
  { id: "earlyCheckIn", engineKey: "earlyCheckIn", title: "Erken giriş penceresi", value: 15, unit: "dakika", level: "Operasyon", active: true, effectiveFrom: "2026-01-01", note: "Daha erken giriş yönetici onayına düşer." },
];

export const holidays = generateTurkeyHolidays(2026, 2050);

export const leaveTypes = [
  { id: "weekly_off", code: "HAFTA_TATILI", name: "Haftalık İzin / Hafta Tatili", paid: true, creditsPayroll: false, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "annual", code: "YILLIK", name: "Yıllık İzin", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: true, requiresDocument: false, active: true },
  { id: "unpaid", code: "UCRETSIZ", name: "Ücretsiz İzin", paid: false, creditsPayroll: false, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "paternity", code: "BABALIK", name: "Babalık İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "maternity", code: "ANNELIK", name: "Annelik / Doğum İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "fieldhero", code: "SAHA_KAHRAMANI", name: "Saha Kahramanı İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "report", code: "RAPOR", name: "Sağlık Raporu", paid: false, creditsPayroll: false, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "marriage", code: "EVLILIK", name: "Evlilik İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "bereavement", code: "OLUM", name: "Ölüm İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "menstrual", code: "REGL", name: "Regl İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "absence", code: "DEVAMSIZLIK", name: "Devamsızlık", paid: false, creditsPayroll: false, excusesMissing: false, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "work_accident", code: "IS_KAZASI", name: "Hastalık İzni (İş Kazası)", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: true, active: true },
  { id: "administrative", code: "IDARI", name: "İdari İzin", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
  { id: "relocation", code: "TASINMA", name: "Taşınma İzni", paid: true, creditsPayroll: true, excusesMissing: true, countsWeekly: false, deductsBalance: false, requiresDocument: false, active: true },
];

export const shifts = [
  { id: "SHIFT-1407-001", personId: "100184", personName: "Erdi Aydın", warehouseId: "fulya", warehouse: "Fulya (İstanbul)", date: "2026-07-14", start: "08:00", end: "17:00", breakMinutes: 60, expectedMinutes: 480, role: "Picker", status: "Atandı", source: "Tekli", createdBy: "system" },
  { id: "SHIFT-1407-002", personId: "100221", personName: "Efe Yılmaz", warehouseId: "fulya", warehouse: "Fulya (İstanbul)", date: "2026-07-14", start: "07:00", end: "16:00", breakMinutes: 60, expectedMinutes: 480, role: "Picker", status: "Tamamlandı", source: "Toplu", createdBy: "system" },
  { id: "SHIFT-1407-003", personId: "100287", personName: "Kerim Atayolu", warehouseId: "uskudar", warehouse: "Üsküdar (İstanbul)", date: "2026-07-14", start: "08:00", end: "17:00", breakMinutes: 60, expectedMinutes: 480, role: "Picker", status: "Tamamlandı", source: "Toplu", createdBy: "system" },
  { id: "SHIFT-1407-004", personId: "100344", personName: "Çağrı Ayan", warehouseId: "seref", warehouse: "Şeref (Ankara)", date: "2026-07-14", start: "09:00", end: "18:00", breakMinutes: 60, expectedMinutes: 480, role: "Picker", status: "Gelmedi", source: "Toplu", createdBy: "system" },
  { id: "SHIFT-1307-005", personId: "100415", personName: "Emrecan Alver", warehouseId: "semt", warehouse: "Şemsettin Günaltay (İstanbul)", date: "2026-07-13", start: "14:00", end: "23:00", breakMinutes: 60, expectedMinutes: 480, role: "Picker", status: "Tamamlandı", source: "Toplu", createdBy: "system" },
];

export const attendance = [
  { id: "ATT-1407-001", shiftId: "SHIFT-1407-001", personId: "100184", name: "Erdi Aydın", role: "Picker", warehouse: "Fulya (İstanbul)", date: "14.07.2026", planned: "08:00–17:00", checkIn: "08:06", checkOut: "—", breaks: [], breakMinutes: 0, netMinutes: 244, expectedMinutes: 480, status: "Vardiyada", approval: "Canlı", location: "Doğrulandı", device: "iPhone 15 · Kayıtlı", source: "Mobil" },
  { id: "ATT-1407-002", shiftId: "SHIFT-1407-002", personId: "100221", name: "Efe Yılmaz", role: "Picker", warehouse: "Fulya (İstanbul)", date: "14.07.2026", planned: "07:00–16:00", checkIn: "06:58", checkOut: "16:11", breaks: [{ start: "12:00", end: "13:00" }], breakMinutes: 60, expectedMinutes: 480, status: "Tamamlandı", approval: "Onay bekliyor", location: "Doğrulandı", device: "Samsung A55 · Kayıtlı", source: "Mobil" },
  { id: "ATT-1407-003", shiftId: "SHIFT-1407-003", personId: "100287", name: "Kerim Atayolu", role: "Picker", warehouse: "Üsküdar (İstanbul)", date: "14.07.2026", planned: "08:00–17:00", checkIn: "08:24", checkOut: "16:42", breaks: [{ start: "12:30", end: "13:30" }], breakMinutes: 60, expectedMinutes: 480, status: "Eksik çalışma", approval: "İnceleme gerekli", location: "Doğrulandı", device: "Redmi Note 13 · Kayıtlı", source: "Mobil" },
  { id: "ATT-1407-004", shiftId: "SHIFT-1407-004", personId: "100344", name: "Çağrı Ayan", role: "Picker", warehouse: "Şeref (Ankara)", date: "14.07.2026", planned: "09:00–18:00", checkIn: "—", checkOut: "—", breaks: [], breakMinutes: 0, expectedMinutes: 480, status: "Gelmedi", approval: "İnceleme gerekli", location: "Kayıt yok", device: "Pixel 8 · Kayıtlı", source: "—" },
  { id: "ATT-1307-005", shiftId: "SHIFT-1307-005", personId: "100415", name: "Emrecan Alver", role: "Picker", warehouse: "Şemsettin Günaltay (İstanbul)", date: "13.07.2026", planned: "14:00–23:00", checkIn: "13:57", checkOut: "23:26", breaks: [{ start: "18:00", end: "19:00" }], breakMinutes: 60, expectedMinutes: 480, status: "Fazla mesai", approval: "Onay bekliyor", location: "Doğrulandı", device: "Samsung S23 · Kayıtlı", source: "Mobil" },
];

export const leaves = [
  { id: "LEV-1507-001", personId: "100344", warehouse: "Şeref (Ankara)", typeId: "annual", date: "2026-07-15", minutes: 450, approval: "Onaylandı", note: "Yıllık izin", enteredBy: "manager" },
  { id: "LEV-1607-002", personId: "100287", warehouse: "Üsküdar (İstanbul)", typeId: "unpaid", date: "2026-07-16", minutes: 450, approval: "Onaylandı", note: "Ücretsiz izin", enteredBy: "manager" },
];

export const devices = [
  { id: "DEV-9192", personId: "100184", person: "Erdi Aydın", model: "iPhone 15", os: "iOS 19.5", app: "1.0.0", integrity: "Güvenilir", attestationStatus: "App Attest doğrulandı", lastSeen: "14.07.2026 12:06", status: "Aktif" },
  { id: "DEV-4418", personId: "100221", person: "Efe Yılmaz", model: "Samsung A55", os: "Android 16", app: "1.0.0", integrity: "Güvenilir", attestationStatus: "Play Integrity doğrulandı", lastSeen: "14.07.2026 16:11", status: "Aktif" },
  { id: "DEV-7781", personId: "100287", person: "Kerim Atayolu", model: "Redmi Note 13", os: "Android 15", app: "0.9.8", integrity: "Güncelleme gerekli", attestationStatus: "Play Integrity doğrulandı", lastSeen: "14.07.2026 16:42", status: "Uyarı" },
  { id: "DEV-3054", personId: "100344", person: "Çağrı Ayan", model: "Pixel 8", os: "Android 16", app: "1.0.0", integrity: "Güvenilir", attestationStatus: "Play Integrity doğrulandı", lastSeen: "13.07.2026 18:03", status: "Aktif" },
];

export const pickerShifts = [
  { id: "SHIFT-1407-001", date: "14 Temmuz 2026, Salı", shortDate: "14", month: "Temmuz", day: "Salı", warehouse: "Fulya (İstanbul)", role: "Picker", planned: "08:00–17:00", actual: "08:06–Devam ediyor", checkIn: "08:06", checkOut: "—", breakText: "Henüz kullanılmadı", gross: "4 saat 04 dakika", net: "4 saat 04 dakika", difference: "Canlı vardiya", status: "Vardiyada", tone: "live", location: "Giriş konumu doğrulandı", device: "Kayıtlı cihaz" },
  { id: "SHIFT-1307", date: "13 Temmuz 2026, Pazartesi", shortDate: "13", month: "Temmuz", day: "Pzt", warehouse: "Fulya (İstanbul)", role: "Picker", planned: "08:00–17:00", actual: "07:59–17:12", checkIn: "07:59", checkOut: "17:12", breakText: "60 dakika", gross: "9 saat 13 dakika", net: "8 saat 13 dakika", difference: "+13 dakika", status: "Tamamlandı", tone: "done", location: "Giriş ve çıkış konumu doğrulandı", device: "Kayıtlı cihaz" },
  { id: "SHIFT-1207", date: "12 Temmuz 2026, Pazar", shortDate: "12", month: "Temmuz", day: "Paz", warehouse: "Fulya (İstanbul)", role: "Picker", planned: "09:00–18:00", actual: "Kayıt yok", checkIn: "—", checkOut: "—", breakText: "—", gross: "0 dakika", net: "0 dakika", difference: "8 saat eksik", status: "Gelmedi", tone: "missed", location: "Konum kaydı yok", device: "İşlem yapılmadı" },
  { id: "SHIFT-1107", date: "11 Temmuz 2026, Cumartesi", shortDate: "11", month: "Temmuz", day: "Cmt", warehouse: "Üsküdar (İstanbul)", role: "Geçici görevlendirme", planned: "14:00–23:00", actual: "13:57–23:21", checkIn: "13:57", checkOut: "23:21", breakText: "60 dakika", gross: "9 saat 24 dakika", net: "8 saat 24 dakika", difference: "+24 dakika", status: "Fazla mesai onayında", tone: "pending", location: "Giriş ve çıkış konumu doğrulandı", device: "Kayıtlı cihaz" },
];

export const DEFAULT_WORKFORCE_STATE = {
  version: 4,
  settings: { nightStart: "20:00", nightEnd: "06:00", requireAssignedShift: true, standardDayMinutes: 450, holidayOfficialThrough: 2035 },
  featureFlags: {
    breaks: true,
    leaveRequests: true,
    appeals: true,
    announcements: true,
    notifications: true,
    archive: true,
    managerTasks: true,
    qrCheckIn: false,
    liveBreakActivity: true,
    employeeExperience: true,
  },
  people,
  warehouses,
  rules,
  holidays,
  leaveTypes,
  leaves,
  shifts,
  attendance,
  devices,
  staffingNorms: DEFAULT_STAFFING_NORMS,
  rosterImport: null,
  rosterIdentityMap: {},
  rosterIdentityImport: null,
  employeeImport: null,
  employmentLifecycleImport: null,
  attendanceImport: null,
  userAccounts: [],
  rosterOverrides: {},
  rosterTasks: [],
  correctionRequests: [],
  leaveRequests: [],
  shiftBreakStates: {},
  announcements: [],
  announcementReceipts: {},
  notificationSettings: {
    shiftPublished: true,
    checkInReminder: true,
    checkInReminderMinutes: 15,
    checkOutReminder: true,
    checkOutReminderMinutes: 15,
  },
  periodCloseRuns: [],
  notifications: [
    { id: "NOT-1", personId: "100184", type: "shift", title: "Vardiyan atandı", message: "14 Temmuz 08:00–17:00 · Fulya (İstanbul)", createdAt: "2026-07-13T18:00:00+03:00", read: false },
    { id: "NOT-2", personId: "100184", type: "reminder", title: "Vardiyan başladı", message: "Konum ve kayıtlı cihazını doğrulayarak vardiyanı yönetebilirsin.", createdAt: "2026-07-14T08:00:00+03:00", read: false },
  ],
  audit: [],
};

function clone(value) { return JSON.parse(JSON.stringify(value)); }

function allowSensitivePilotStorage() {
  return (
    typeof window !== "undefined" &&
    import.meta.env.DEV
  );
}

function purgeSensitiveWorkforceStorage() {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.removeItem(
      WORKFORCE_STORAGE_KEY
    );

    window.localStorage.removeItem(
      LEGACY_STORAGE_KEY
    );
  } catch {
    // Browser storage may be unavailable.
  }
}

export function loadWorkforceState() {
  if (typeof window === "undefined") {
    return clone(DEFAULT_WORKFORCE_STATE);
  }

  if (!allowSensitivePilotStorage()) {
    purgeSensitiveWorkforceStorage();
    return clone(DEFAULT_WORKFORCE_STATE);
  }

  try {
    const stored = JSON.parse(
      window.localStorage.getItem(
        WORKFORCE_STORAGE_KEY
      ) ||
        window.localStorage.getItem(
          LEGACY_STORAGE_KEY
        )
    );

    if ([2, 3, 4].includes(stored?.version)) {
      const defaults = clone(
        DEFAULT_WORKFORCE_STATE
      );

      return {
        ...defaults,
        ...stored,
        version: 4,

        settings: {
          ...defaults.settings,
          ...(stored.settings || {}),
        },

        featureFlags: {
          ...defaults.featureFlags,
          ...(stored.featureFlags || {}),
        },

        notificationSettings: {
          ...defaults.notificationSettings,
          ...(stored.notificationSettings || {}),
        },

        people: (
          stored.people ||
          defaults.people
        ).map((person) => ({
          nationalId: "",
          hireDate: "",
          terminationDate: "",
          ...person,
        })),

        staffingNorms:
          stored.staffingNorms ||
          defaults.staffingNorms,

        holidays:
          stored.holidays?.some((item) =>
            item.id?.startsWith("TR-")
          )
            ? stored.holidays
            : defaults.holidays,
      };
    }
  } catch {
    // Fail closed to in-memory defaults.
  }

  return clone(DEFAULT_WORKFORCE_STATE);
}

export function saveWorkforceState(state) {
  if (!allowSensitivePilotStorage()) {
    purgeSensitiveWorkforceStorage();
    return;
  }

  try {
    window.localStorage.setItem(
      WORKFORCE_STORAGE_KEY,
      JSON.stringify({
        ...state,
        version: 4,
        savedAt: new Date().toISOString(),
      })
    );
  } catch (error) {
    console.warn(
      "Workforce DEV pilot storage limit reached",
      error
    );
  }
}

export function formatMinutes(value = 0) {
  const minutes = Math.max(0, Math.round(Number(value) || 0));
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  const locale = typeof window !== "undefined" ? window.localStorage.getItem("opex_workforce_locale") || "tr" : "tr";
  const units = { tr: { hour: "sa", minute: "dk" }, en: { hour: "hr", minute: "min" }, de: { hour: "Std.", minute: "Min." }, ar: { hour: "س", minute: "د" } }[locale] || { hour: "sa", minute: "dk" };
  if (!hours) return `${remainder} ${units.minute}`;
  return remainder ? `${hours} ${units.hour} ${remainder} ${units.minute}` : `${hours} ${units.hour}`;
}
