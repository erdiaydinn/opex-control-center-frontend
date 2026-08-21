const DAY_MS = 24 * 60 * 60 * 1000;

export function parseTrDate(dateValue) {
  const [day, month, year] = String(dateValue || "").split(".").map(Number);
  if (!day || !month || !year) return null;
  return new Date(year, month - 1, day);
}

export function toTrDate(isoDate) {
  const [year, month, day] = String(isoDate || "").split("-");
  return year && month && day ? `${day}.${month}.${year}` : isoDate;
}

export function toIsoDate(trDate) {
  const [day, month, year] = String(trDate || "").split(".");
  return year && month && day ? `${year}-${month}-${day}` : trDate;
}

export function clockToMinutes(clock) {
  if (!clock || clock === "—") return null;
  const [hour, minute] = String(clock).split(":").map(Number);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return hour * 60 + minute;
}

export function dateTime(dateValue, clock) {
  const base = parseTrDate(dateValue);
  const minute = clockToMinutes(clock);
  if (!base || minute === null) return null;
  base.setHours(Math.floor(minute / 60), minute % 60, 0, 0);
  return base;
}

export function intervalMinutes(start, end) {
  if (!start || !end) return 0;
  return Math.max(0, Math.round((end.getTime() - start.getTime()) / 60000));
}

export function overlapMinutes(startA, endA, startB, endB) {
  if (![startA, endA, startB, endB].every(Boolean)) return 0;
  const start = Math.max(startA.getTime(), startB.getTime());
  const end = Math.min(endA.getTime(), endB.getTime());
  return Math.max(0, Math.round((end - start) / 60000));
}

function normalizeEnd(start, end) {
  if (start && end && end <= start) return new Date(end.getTime() + DAY_MS);
  return end;
}

function holidayIntervals(holidays = []) {
  return holidays.filter((item) => item.active !== false).map((item) => ({
    ...item,
    startAt: new Date(item.startAt),
    endAt: new Date(item.endAt),
  }));
}

function breakIntervals(row, shiftStart) {
  if (Array.isArray(row.breaks) && row.breaks.length) {
    return row.breaks.map((item) => {
      const start = dateTime(row.date, item.start);
      let end = dateTime(row.date, item.end);
      end = normalizeEnd(start, end);
      return { start, end };
    }).filter((item) => item.start && item.end);
  }
  if (row.breakMinutes && shiftStart) {
    const end = new Date(shiftStart.getTime() + Number(row.breakMinutes) * 60000);
    return [{ start: shiftStart, end, estimated: true }];
  }
  return [];
}

function subtractBreakOverlap(minutes, targetStart, targetEnd, breaks) {
  const breakInTarget = breaks.reduce((sum, item) => sum + overlapMinutes(targetStart, targetEnd, item.start, item.end), 0);
  return Math.max(0, minutes - breakInTarget);
}

function calculateNightMinutes(workStart, workEnd, breaks, nightStart = "20:00", nightEnd = "06:00") {
  if (!workStart || !workEnd) return 0;
  const startMinute = clockToMinutes(nightStart) ?? 1200;
  const endMinute = clockToMinutes(nightEnd) ?? 360;
  let cursor = new Date(workStart.getFullYear(), workStart.getMonth(), workStart.getDate() - 1);
  const limit = new Date(workEnd.getFullYear(), workEnd.getMonth(), workEnd.getDate() + 1);
  let total = 0;

  while (cursor <= limit) {
    const nightFrom = new Date(cursor);
    nightFrom.setHours(Math.floor(startMinute / 60), startMinute % 60, 0, 0);
    const nightTo = new Date(cursor);
    nightTo.setHours(Math.floor(endMinute / 60), endMinute % 60, 0, 0);
    if (nightTo <= nightFrom) nightTo.setDate(nightTo.getDate() + 1);
    const overlap = overlapMinutes(workStart, workEnd, nightFrom, nightTo);
    total += subtractBreakOverlap(overlap, nightFrom, nightTo, breaks);
    cursor.setDate(cursor.getDate() + 1);
  }
  return Math.min(total, intervalMinutes(workStart, workEnd));
}

export function calculateAttendance(row, holidays = [], settings = {}) {
  const workStart = dateTime(row.date, row.checkIn);
  let workEnd = dateTime(row.date, row.checkOut);
  workEnd = normalizeEnd(workStart, workEnd);
  if (!workStart || !workEnd) {
    const existingNet = Number(row.netMinutes || 0);
    return {
      ...row,
      grossMinutes: existingNet,
      netMinutes: existingNet,
      normalMinutes: existingNet,
      holidayMinutes: 0,
      nightMinutes: 0,
      missingMinutes: row.status === "Vardiyada" ? 0 : Math.max(0, Number(row.expectedMinutes || 0) - existingNet),
      overtimeMinutes: Math.max(0, existingNet - Number(row.expectedMinutes || 0)),
    };
  }
  const breaks = breakIntervals(row, workStart);
  const grossMinutes = intervalMinutes(workStart, workEnd);
  const explicitBreakMinutes = breaks.reduce((sum, item) => sum + intervalMinutes(item.start, item.end), 0);
  const breakMinutes = explicitBreakMinutes || Number(row.breakMinutes || 0);
  const workedMinutes = Math.max(0, grossMinutes - breakMinutes);

  let holidayMinutes = 0;
  holidayIntervals(holidays).forEach((holiday) => {
    const overlap = overlapMinutes(workStart, workEnd, holiday.startAt, holiday.endAt);
    holidayMinutes += subtractBreakOverlap(overlap, holiday.startAt, holiday.endAt, breaks);
  });
  holidayMinutes = Math.min(workedMinutes, holidayMinutes);

  const nightMinutes = Math.min(
    workedMinutes,
    calculateNightMinutes(workStart, workEnd, breaks, settings.nightStart, settings.nightEnd)
  );
  const expectedMinutes = Number(row.expectedMinutes || 0);
  return {
    ...row,
    grossMinutes,
    breakMinutes,
    netMinutes: workedMinutes,
    normalMinutes: Math.max(0, workedMinutes - holidayMinutes),
    holidayMinutes,
    nightMinutes,
    missingMinutes: Math.max(0, expectedMinutes - workedMinutes),
    overtimeMinutes: Math.max(0, workedMinutes - expectedMinutes),
  };
}

export function buildTimesheetRows(state, filters = {}) {
  const { attendance = [], holidays = [], leaves = [], leaveTypes = [], people = [] } = state;
  const personById = Object.fromEntries(people.map((person) => [person.id, person]));
  const typeById = Object.fromEntries(leaveTypes.map((type) => [type.id, type]));
  const rows = attendance.map((row) => ({
    ...calculateAttendance(row, holidays, state.settings),
    recordType: "attendance",
    leaveMinutes: 0,
    paidLeaveMinutes: 0,
    weeklyCreditMinutes: 0,
  }));

  leaves.forEach((leave) => {
    const type = typeById[leave.typeId] || {};
    const person = personById[leave.personId] || {};
    rows.push({
      id: leave.id,
      recordType: "leave",
      personId: leave.personId,
      name: person.name || leave.personName,
      warehouse: leave.warehouse || person.warehouse,
      date: toTrDate(leave.date),
      planned: "İzin",
      checkIn: "—",
      checkOut: "—",
      expectedMinutes: Number(leave.minutes || 0),
      netMinutes: 0,
      normalMinutes: 0,
      holidayMinutes: 0,
      nightMinutes: 0,
      missingMinutes: type.excusesMissing !== false ? 0 : Number(leave.minutes || 0),
      overtimeMinutes: 0,
      leaveMinutes: Number(leave.minutes || 0),
      paidLeaveMinutes: type.paid ? Number(leave.minutes || 0) : 0,
      weeklyCreditMinutes: type.countsWeekly ? Number(leave.minutes || 0) : 0,
      status: type.name || "İzin",
      approval: leave.approval || "Onaylandı",
      leaveType: type.name,
    });
  });

  return rows.filter((row) => {
    const isoDate = toIsoDate(row.date);
    if (filters.personId && row.personId !== filters.personId) return false;
    if (filters.warehouse && row.warehouse !== filters.warehouse) return false;
    if (filters.startDate && isoDate < filters.startDate) return false;
    if (filters.endDate && isoDate > filters.endDate) return false;
    return true;
  }).sort((a, b) => `${a.date}-${a.name}`.localeCompare(`${b.date}-${b.name}`, "tr"));
}

export function summarizeTimesheet(rows = []) {
  return rows.reduce((summary, row) => ({
    normalMinutes: summary.normalMinutes + Number(row.normalMinutes || 0),
    holidayMinutes: summary.holidayMinutes + Number(row.holidayMinutes || 0),
    nightMinutes: summary.nightMinutes + Number(row.nightMinutes || 0),
    overtimeMinutes: summary.overtimeMinutes + Number(row.overtimeMinutes || 0),
    missingMinutes: summary.missingMinutes + Number(row.missingMinutes || 0),
    leaveMinutes: summary.leaveMinutes + Number(row.leaveMinutes || 0),
    paidLeaveMinutes: summary.paidLeaveMinutes + Number(row.paidLeaveMinutes || 0),
    weeklyCreditMinutes: summary.weeklyCreditMinutes + Number(row.weeklyCreditMinutes || 0),
  }), { normalMinutes: 0, holidayMinutes: 0, nightMinutes: 0, overtimeMinutes: 0, missingMinutes: 0, leaveMinutes: 0, paidLeaveMinutes: 0, weeklyCreditMinutes: 0 });
}

function employmentAllows(person, isoDate) {
  if (!person) return true;
  if (person.hireDate && isoDate < person.hireDate) return false;
  if (person.terminationDate && isoDate > person.terminationDate) return false;
  return true;
}

export function buildCumulativePayroll(state, filters = {}) {
  const startDate = filters.startDate || "0000-01-01";
  const endDate = filters.endDate || "9999-12-31";
  const personById = Object.fromEntries((state.people || []).map((person) => [person.id, person]));
  const rows = buildTimesheetRows(state, { startDate, endDate }).filter((row) => employmentAllows(personById[row.personId], toIsoDate(row.date)));
  const expectedByPerson = {};
  (state.shifts || []).forEach((shift) => {
    const person = personById[shift.personId];
    if (shift.status === "İptal" || shift.date < startDate || shift.date > endDate || !employmentAllows(person, shift.date)) return;
    expectedByPerson[shift.personId] = (expectedByPerson[shift.personId] || 0) + Number(shift.expectedMinutes || 0);
  });
  const grouped = new Map();
  rows.forEach((row) => {
    const person = personById[row.personId] || { id: row.personId, name: row.name, warehouse: row.warehouse };
    if (!grouped.has(row.personId)) {
      grouped.set(row.personId, {
        personId: row.personId,
        name: person.name || row.name,
        nationalId: person.nationalId || "",
        warehouse: person.warehouse || row.warehouse,
        role: person.role || row.role || "Picker",
        hireDate: person.hireDate || "",
        terminationDate: person.terminationDate || "",
        expectedMinutes: expectedByPerson[row.personId] || 0,
        workedMinutes: 0,
        normalMinutes: 0,
        holidayMinutes: 0,
        nightMinutes: 0,
        overtimeMinutes: 0,
        missingMinutes: 0,
        leaveMinutes: 0,
        paidLeaveMinutes: 0,
        weeklyCreditMinutes: 0,
        shiftCount: 0,
        leaveDays: 0,
      });
    }
    const target = grouped.get(row.personId);
    target.workedMinutes += Number(row.netMinutes || 0);
    target.normalMinutes += Number(row.normalMinutes || 0);
    target.holidayMinutes += Number(row.holidayMinutes || 0);
    target.nightMinutes += Number(row.nightMinutes || 0);
    target.overtimeMinutes += Number(row.overtimeMinutes || 0);
    target.missingMinutes += Number(row.missingMinutes || 0);
    target.leaveMinutes += Number(row.leaveMinutes || 0);
    target.paidLeaveMinutes += Number(row.paidLeaveMinutes || 0);
    target.weeklyCreditMinutes += Number(row.weeklyCreditMinutes || 0);
    if (row.recordType === "attendance") target.shiftCount += 1;
    else target.leaveDays += 1;
  });
  (state.people || []).forEach((person) => {
    const activeInPeriod = (!person.hireDate || person.hireDate <= endDate) && (!person.terminationDate || person.terminationDate >= startDate);
    if (!activeInPeriod || grouped.has(person.id)) return;
    grouped.set(person.id, {
      personId: person.id, name: person.name, nationalId: person.nationalId || "", warehouse: person.warehouse, role: person.role,
      hireDate: person.hireDate || "", terminationDate: person.terminationDate || "", expectedMinutes: expectedByPerson[person.id] || 0,
      workedMinutes: 0, normalMinutes: 0, holidayMinutes: 0, nightMinutes: 0, overtimeMinutes: 0, missingMinutes: 0,
      leaveMinutes: 0, paidLeaveMinutes: 0, weeklyCreditMinutes: 0, shiftCount: 0, leaveDays: 0,
    });
  });
  return [...grouped.values()].filter((row) => {
    if (filters.personId && row.personId !== filters.personId) return false;
    if (filters.warehouse && row.warehouse !== filters.warehouse) return false;
    return true;
  }).sort((a, b) => a.name.localeCompare(b.name, "tr"));
}

export function summarizeCumulativePayroll(rows = []) {
  return rows.reduce((summary, row) => {
    Object.keys(summary).forEach((key) => { summary[key] += Number(row[key] || 0); });
    return summary;
  }, { expectedMinutes: 0, workedMinutes: 0, normalMinutes: 0, holidayMinutes: 0, nightMinutes: 0, overtimeMinutes: 0, missingMinutes: 0, leaveMinutes: 0 });
}
