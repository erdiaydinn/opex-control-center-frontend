function cleanId(value = "") { return String(value).trim(); }
function cleanNationalId(value = "") {
  const digits = String(value).replace(/\D/g, "");
  return digits.length === 11 ? digits : "";
}
function cleanEmail(value = "") { return String(value).trim().toLocaleLowerCase("tr-TR"); }

function uniqueIndex(items, getter) {
  const buckets = new Map();
  items.forEach((item) => {
    const key = getter(item);
    if (!key) return;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(item);
  });
  return buckets;
}

export function resolveWorkforcePerson(identity, people = [], rosterIdentityMap = {}) {
  const peopleById = new Map(people.map((person) => [cleanId(person.id), person]));
  const peopleByNationalId = uniqueIndex(people, (person) => cleanNationalId(person.nationalId));
  const peopleByRosterId = uniqueIndex(people.flatMap((person) => (person.rosterIds || []).map((rosterId) => ({ rosterId: cleanId(rosterId), person }))), (item) => item.rosterId);
  const sourcePersonId = cleanId(identity?.sourcePersonId || identity?.personId || identity?.hrPersonId);
  const nationalId = cleanNationalId(identity?.nationalId);

  if (nationalId) {
    const matches = peopleByNationalId.get(nationalId) || [];
    if (matches.length === 1) return { person: matches[0], method: "TC", status: "Eşleşti", reason: "" };
    if (matches.length > 1) return { person: null, method: "TC", status: "Belirsiz", reason: "TC birden fazla personel kaydıyla eşleşiyor" };
  }

  if (sourcePersonId && peopleById.has(sourcePersonId)) {
    return { person: peopleById.get(sourcePersonId), method: "Employee ID", status: "Eşleşti", reason: "" };
  }

  const rosterMapping = sourcePersonId ? rosterIdentityMap[sourcePersonId] : null;
  if (rosterMapping?.status === "Eşleşti" && peopleById.has(cleanId(rosterMapping.hrPersonId))) {
    return { person: peopleById.get(cleanId(rosterMapping.hrPersonId)), method: "Roster ID eşleştirmesi", status: "Eşleşti", reason: "" };
  }

  const rosterMatches = sourcePersonId ? (peopleByRosterId.get(sourcePersonId) || []) : [];
  if (rosterMatches.length === 1) {
    return { person: rosterMatches[0].person, method: "Roster ID", status: "Eşleşti", reason: "" };
  }
  if (rosterMatches.length > 1) {
    return { person: null, method: "Roster ID", status: "Belirsiz", reason: "Roster ID birden fazla personel kaydıyla eşleşiyor" };
  }

  return {
    person: null,
    method: "",
    status: "Eşleşmedi",
    reason: nationalId ? "TC, personel ana verisinde bulunamadı" : "TC veya Employee ID personel ana verisiyle eşleşmedi",
  };
}

export function buildRosterIdentityMappings(rows, people, existing = {}) {
  const peopleById = new Map(people.map((person) => [cleanId(person.id), person]));
  const peopleByNationalId = uniqueIndex(people, (person) => cleanNationalId(person.nationalId));
  const peopleByEmail = uniqueIndex(people, (person) => cleanEmail(person.email));
  const next = { ...existing };
  let matched = 0;
  let unmatched = 0;
  let ambiguous = 0;

  rows.forEach((row) => {
    const rosterPersonId = cleanId(row.rosterPersonId);
    const nationalId = cleanNationalId(row.nationalId);
    const email = cleanEmail(row.email);
    let person = null;
    let method = "";
    let reason = "";

    if (nationalId && peopleByNationalId.get(nationalId)?.length === 1) {
      [person] = peopleByNationalId.get(nationalId); method = "TC";
    } else if (nationalId && peopleByNationalId.get(nationalId)?.length > 1) {
      reason = "TC birden fazla İK kaydıyla eşleşiyor"; ambiguous += 1;
    } else if (nationalId) {
      reason = "TC, İK personel ana verisinde bulunamadı";
    } else if (row.hrPersonId && peopleById.has(cleanId(row.hrPersonId))) {
      person = peopleById.get(cleanId(row.hrPersonId)); method = "HR Employee ID";
    } else if (email && peopleByEmail.get(email)?.length === 1) {
      [person] = peopleByEmail.get(email); method = "E-posta";
    } else if (email && peopleByEmail.get(email)?.length > 1) {
      reason = "E-posta birden fazla İK kaydıyla eşleşiyor"; ambiguous += 1;
    } else if (peopleById.has(rosterPersonId)) {
      person = peopleById.get(rosterPersonId); method = "Aynı Employee ID";
    } else reason = "TC gerekli; HR Employee ID yalnız eski dosyalar için yedek alan olarak desteklenir";

    const record = {
      rosterPersonId,
      rosterPersonName: row.rosterPersonName || "—",
      nationalId,
      email: row.email || "",
      phone: row.phone || "",
      contract: row.contract || "",
      active: row.active,
      hrPersonId: person ? cleanId(person.id) : "",
      hrPersonName: person?.name || "",
      warehouse: person?.warehouse || "",
      method,
      status: person ? "Eşleşti" : reason.includes("birden fazla") ? "Belirsiz" : "Eşleşmedi",
      reason,
      updatedAt: new Date().toISOString(),
    };
    next[rosterPersonId] = record;
    if (person) matched += 1; else unmatched += 1;
  });
  return { mappings: next, summary: { total: rows.length, matched, unmatched, ambiguous } };
}

export function reconcileRosterRows(rows, state) {
  const mappings = state.rosterIdentityMap || {};
  const peopleById = new Map((state.people || []).map((person) => [cleanId(person.id), person]));
  const peopleByNationalId = uniqueIndex(state.people || [], (person) => cleanNationalId(person.nationalId));
  const peopleByRosterId = uniqueIndex((state.people || []).flatMap((person) => (person.rosterIds || []).map((rosterId) => ({ rosterId: cleanId(rosterId), person }))), (item) => item.rosterId);
  return rows.map((row) => {
    const rosterPersonId = cleanId(row.rosterPersonId || row.personId);
    const mapping = mappings[rosterPersonId];
    const directPerson = peopleById.get(rosterPersonId);
    const inlineTcMatches = peopleByNationalId.get(cleanNationalId(row.nationalId)) || [];
    const inlineTcPerson = inlineTcMatches.length === 1 ? inlineTcMatches[0] : null;
    const rosterMatches = peopleByRosterId.get(rosterPersonId) || [];
    const rosterPerson = rosterMatches.length === 1 ? rosterMatches[0].person : null;
    const hrPersonId = mapping?.status === "Eşleşti" ? cleanId(mapping.hrPersonId) : directPerson ? rosterPersonId : inlineTcPerson ? cleanId(inlineTcPerson.id) : rosterPerson ? cleanId(rosterPerson.id) : "";
    const person = peopleById.get(hrPersonId);
    if (!person) return { ...row, rosterPersonId, rosterPersonName: row.rosterPersonName || row.personName, identityStatus: mapping?.status || (inlineTcMatches.length > 1 || rosterMatches.length > 1 ? "Belirsiz" : "Eşleşmedi"), identityMethod: mapping?.method || "" };
    return {
      ...row,
      rosterPersonId,
      rosterPersonName: row.rosterPersonName || row.personName,
      personId: hrPersonId,
      personName: person.name || row.personName,
      identityStatus: "Eşleşti",
      identityMethod: mapping?.method || (directPerson ? "Aynı Employee ID" : inlineTcPerson ? "Roster TC" : "Roster ID"),
      hrWarehouse: person.warehouse || "",
    };
  });
}
