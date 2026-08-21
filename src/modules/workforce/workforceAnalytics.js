import { reconcileRosterRows } from "./workforceIdentity.js";

const MANAGER_TITLES = new Set(["WAREHOUSE MANAGER", "STORE MANAGER", "DEPO MÜDÜRÜ", "MAĞAZA MÜDÜRÜ", "RIDER CAPTAIN"]);

function isManager(title = "") {
  const normalized = String(title).trim().toLocaleUpperCase("tr-TR").replaceAll(/[_-]+/g, " ").replaceAll(/\s+/g, " ");
  return MANAGER_TITLES.has(normalized);
}

function attendanceDate(value = "") {
  const match = String(value).match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value).slice(0, 10);
}

function percent(value, total) {
  return total > 0 ? Math.round((value / total) * 1000) / 10 : 0;
}

function clamp(value, min = 0, max = 100) {
  return Math.min(max, Math.max(min, value));
}

function emptyWarehouse(row) {
  return {
    warehouse: row.warehouse,
    regionalManager: row.regionalManager || "Eşleşmeyen",
    regionalExecutive: row.regionalExecutive || "Eşleşmeyen",
    norm: Number(row.norm) || 0,
    people: new Set(),
    totalMinutes: 0,
    normalMinutes: 0,
    holidayMinutes: 0,
    overtimeMinutes: 0,
    shiftDays: 0,
    workedDays: 0,
    leaveDays: 0,
    noCheckInDays: 0,
    anomalyCount: 0,
    leaveConflicts: 0,
  };
}

export function buildWorkforceAnalytics({ state, attendance = [], rosterRows = [], period }) {
  const norms = (state.staffingNorms || []).filter((row) => row.active !== false);
  const normByWarehouse = new Map(norms.map((row) => [row.warehouse, row]));
  const leaveKeys = new Set((state.leaves || []).map((row) => `${row.personId}|${row.date}`));
  const overrides = state.rosterOverrides || {};
  const hasRoster = rosterRows.length > 0;
  const rawSourceRows = hasRoster ? rosterRows : attendance.map((row) => ({
    sourceKey: row.id,
    personId: row.personId,
    personName: row.name,
    title: row.role,
    warehouse: row.warehouse,
    date: attendanceDate(row.date),
    netMinutes: Number(row.netMinutes) || 0,
    holidayMinutes: Number(row.holidayMinutes) || 0,
    grossMinutes: Number(row.netMinutes) + Number(row.breakMinutes || 0),
    anomaly: Number(row.netMinutes) + Number(row.breakMinutes || 0) > 660 ? "11 saat üstü" : "",
  }));
  const sourceRows = reconcileRosterRows(rawSourceRows, state);

  const normPasses = (row) => (!period.regionalManager || row?.regionalManager === period.regionalManager)
    && (!period.regionalExecutive || row?.regionalExecutive === period.regionalExecutive)
    && (!period.warehouse || row?.warehouse === period.warehouse);
  const rowPasses = (row) => {
    const norm = normByWarehouse.get(row.warehouse);
    return row.date >= period.startDate && row.date <= period.endDate
      && (!period.warehouse || row.warehouse === period.warehouse)
      && (!period.regionalManager || norm?.regionalManager === period.regionalManager)
      && (!period.regionalExecutive || norm?.regionalExecutive === period.regionalExecutive);
  };

  const periodRows = sourceRows.filter(rowPasses);
  const daily = new Map();
  periodRows.forEach((row) => {
    if (!row.personId || !row.warehouse || !row.date || isManager(row.title)) return;
    const key = `${row.personId}|${row.date}|${row.warehouse}`;
    const target = daily.get(key) || {
      personId: String(row.personId),
      personName: row.personName || "—",
      warehouse: row.warehouse,
      date: row.date,
      title: row.title || "—",
      minutes: 0,
      holidayMinutes: 0,
      anomalyCount: 0,
      hasLeave: leaveKeys.has(`${row.personId}|${row.date}`),
    };
    const rowMinutes = Number(overrides[row.sourceKey]?.normalizedMinutes ?? row.netMinutes) || 0;
    target.minutes += target.hasLeave ? 0 : rowMinutes;
    target.holidayMinutes += target.hasLeave ? 0 : Number(row.holidayMinutes || 0);
    target.anomalyCount += row.anomaly || Number(row.grossMinutes || 0) > 660 ? 1 : 0;
    target.leaveConflict = target.hasLeave && rowMinutes > 0;
    daily.set(key, target);
  });

  const metrics = new Map();
  const ensureMetric = (warehouse) => {
    if (!metrics.has(warehouse)) {
      const norm = normByWarehouse.get(warehouse) || { warehouse, norm: 0, regionalManager: "Eşleşmeyen", regionalExecutive: "Eşleşmeyen" };
      metrics.set(warehouse, emptyWarehouse(norm));
    }
    return metrics.get(warehouse);
  };

  if (hasRoster) norms.filter(normPasses).forEach((row) => ensureMetric(row.warehouse));
  daily.forEach((day) => {
    const target = ensureMetric(day.warehouse);
    const holiday = Math.min(day.minutes, day.holidayMinutes);
    const nonHoliday = Math.max(0, day.minutes - holiday);
    const overtime = Math.max(0, nonHoliday - Number(state.settings?.standardDayMinutes || 450));
    target.people.add(day.personId);
    target.totalMinutes += day.minutes;
    target.normalMinutes += Math.min(Number(state.settings?.standardDayMinutes || 450), nonHoliday);
    target.holidayMinutes += holiday;
    target.overtimeMinutes += overtime;
    target.shiftDays += 1;
    target.workedDays += day.minutes > 0 ? 1 : 0;
    target.leaveDays += day.hasLeave ? 1 : 0;
    target.noCheckInDays += day.minutes > 0 || day.hasLeave ? 0 : 1;
    target.anomalyCount += day.anomalyCount;
    target.leaveConflicts += day.leaveConflict ? 1 : 0;
  });

  const activePeopleByWarehouse = new Map();
  if (state.employeeImport) {
    (state.people || []).forEach((person) => {
      if (!person.warehouse || isManager(person.role)) return;
      const employed = (!person.hireDate || person.hireDate <= period.endDate)
        && (!person.terminationDate || person.terminationDate >= period.startDate);
      if (!employed) return;
      if (!activePeopleByWarehouse.has(person.warehouse)) activePeopleByWarehouse.set(person.warehouse, new Set());
      activePeopleByWarehouse.get(person.warehouse).add(String(person.id));
    });
  }

  const warehouses = [...metrics.values()].map((row) => {
    const headcount = activePeopleByWarehouse.get(row.warehouse)?.size ?? row.people.size;
    const normGap = Math.max(0, row.norm - headcount);
    const normGapRate = row.norm ? normGap / row.norm : 0;
    const overtimeRate = row.totalMinutes ? row.overtimeMinutes / row.totalMinutes : 0;
    const operationalDays = Math.max(0, row.shiftDays - row.leaveDays);
    const noCheckInRate = operationalDays ? row.noCheckInDays / operationalDays : 0;
    const anomalyRate = row.shiftDays ? row.anomalyCount / row.shiftDays : 0;
    const calculatedPressure = normGapRate * 45
      + Math.min(1, overtimeRate * 5) * 20
      + noCheckInRate * 30
      + Math.min(1, anomalyRate * 8) * 5;
    const pressureScore = Math.round(clamp(row.norm > 0 && row.shiftDays === 0 ? 80 : operationalDays > 0 && row.workedDays === 0 ? Math.max(70, calculatedPressure) : calculatedPressure));
    const risk = pressureScore >= 65 ? "critical" : pressureScore >= 38 ? "warning" : "healthy";
    return {
      ...row,
      people: undefined,
      headcount,
      normGap,
      capacityRate: percent(headcount, row.norm),
      overtimeRate: percent(row.overtimeMinutes, row.totalMinutes),
      checkInRate: percent(row.workedDays, operationalDays),
      pressureScore,
      risk,
    };
  }).sort((a, b) => b.pressureScore - a.pressureScore || b.overtimeMinutes - a.overtimeMinutes);

  const executiveMap = new Map();
  warehouses.forEach((row) => {
    const key = `${row.regionalManager}|${row.regionalExecutive}`;
    const target = executiveMap.get(key) || {
      regionalManager: row.regionalManager,
      regionalExecutive: row.regionalExecutive,
      warehouses: 0,
      norm: 0,
      headcount: 0,
      overtimeMinutes: 0,
      totalMinutes: 0,
      normBelow: 0,
      critical: 0,
      scoreTotal: 0,
    };
    target.warehouses += 1;
    target.norm += row.norm;
    target.headcount += row.headcount;
    target.overtimeMinutes += row.overtimeMinutes;
    target.totalMinutes += row.totalMinutes;
    target.normBelow += row.normGap > 0 ? 1 : 0;
    target.critical += row.risk === "critical" ? 1 : 0;
    target.scoreTotal += row.pressureScore;
    executiveMap.set(key, target);
  });
  const executives = [...executiveMap.values()].map((row) => ({
    ...row,
    overtimeRate: percent(row.overtimeMinutes, row.totalMinutes),
    capacityRate: percent(row.headcount, row.norm),
    pressureScore: row.warehouses ? Math.round(row.scoreTotal / row.warehouses) : 0,
  })).sort((a, b) => b.overtimeMinutes - a.overtimeMinutes);

  const trendMap = new Map();
  daily.forEach((day) => {
    const holiday = Math.min(day.minutes, day.holidayMinutes);
    const nonHoliday = Math.max(0, day.minutes - holiday);
    const overtime = Math.max(0, nonHoliday - Number(state.settings?.standardDayMinutes || 450));
    const target = trendMap.get(day.date) || { date: day.date, overtimeMinutes: 0, totalMinutes: 0, noCheckIn: 0 };
    target.overtimeMinutes += overtime;
    target.totalMinutes += day.minutes;
    target.noCheckIn += day.minutes > 0 || day.hasLeave ? 0 : 1;
    trendMap.set(day.date, target);
  });
  const trend = [...trendMap.values()].sort((a, b) => a.date.localeCompare(b.date));

  const totals = warehouses.reduce((target, row) => ({
    norm: target.norm + row.norm,
    headcount: target.headcount + row.headcount,
    totalMinutes: target.totalMinutes + row.totalMinutes,
    overtimeMinutes: target.overtimeMinutes + row.overtimeMinutes,
    holidayMinutes: target.holidayMinutes + row.holidayMinutes,
    noCheckInDays: target.noCheckInDays + row.noCheckInDays,
    leaveDays: target.leaveDays + row.leaveDays,
    shiftDays: target.shiftDays + row.shiftDays,
    normBelow: target.normBelow + (row.normGap > 0 ? 1 : 0),
    critical: target.critical + (row.risk === "critical" ? 1 : 0),
    anomalies: target.anomalies + row.anomalyCount,
  }), { norm: 0, headcount: 0, totalMinutes: 0, overtimeMinutes: 0, holidayMinutes: 0, noCheckInDays: 0, leaveDays: 0, shiftDays: 0, normBelow: 0, critical: 0, anomalies: 0 });
  totals.overtimeRate = percent(totals.overtimeMinutes, totals.totalMinutes);
  totals.checkInRate = percent(Math.max(0, totals.shiftDays - totals.leaveDays - totals.noCheckInDays), Math.max(0, totals.shiftDays - totals.leaveDays));
  totals.capacityRate = percent(totals.headcount, totals.norm);

  const avoidable = warehouses.filter((row) => row.norm > 0 && row.headcount >= row.norm && row.overtimeMinutes > 0)
    .sort((a, b) => b.overtimeMinutes - a.overtimeMinutes);
  const unmapped = warehouses.filter((row) => !row.norm).length;
  const insights = [
    { id: "capacity", tone: totals.normBelow ? "danger" : "success", value: totals.normBelow, label: "Norm altında depo", detail: `${warehouses.length} deponun ${totals.normBelow} tanesi dönem normunun altında.` },
    { id: "avoidable", tone: avoidable.length ? "warning" : "success", value: avoidable.length, label: "Norm yeterli, mesai var", detail: "Kadro yeterliyken oluşan mesai; vardiya dağılımı ve izin planı incelenmeli." },
    { id: "checkin", tone: totals.checkInRate < 95 ? "danger" : "success", value: `${totals.checkInRate}%`, label: "Check-in başarı oranı", detail: `${totals.noCheckInDays} planlı kişi-günde fiili çalışma kaydı oluşmadı.` },
    { id: "anomaly", tone: totals.anomalies ? "warning" : "success", value: totals.anomalies, label: "11 saat anomalisi", detail: "Yasal risk ve veri kalitesi için ayrıca incelenmesi gereken kayıtlar." },
    { id: "mapping", tone: unmapped ? "warning" : "success", value: unmapped, label: "Norm eşleşmesi yok", detail: "Depo–BY eşlemesi bulunmayan kayıtlar karşılaştırma dışında kalabilir." },
  ];

  return {
    source: hasRoster ? "roster" : "attendance",
    sourceRows: periodRows.length,
    warehouses,
    executives,
    trend,
    totals,
    avoidable,
    insights,
  };
}
