function cleanId(value = "") { return String(value).trim(); }
function cleanNationalId(value = "") { return String(value).replace(/\D/g, ""); }
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
  return rows.map((row) => {
    const rosterPersonId = cleanId(row.rosterPersonId || row.personId);
    const mapping = mappings[rosterPersonId];
    const directPerson = peopleById.get(rosterPersonId);
    const inlineTcMatches = peopleByNationalId.get(cleanNationalId(row.nationalId)) || [];
    const inlineTcPerson = inlineTcMatches.length === 1 ? inlineTcMatches[0] : null;
    const hrPersonId = mapping?.status === "Eşleşti" ? cleanId(mapping.hrPersonId) : directPerson ? rosterPersonId : inlineTcPerson ? cleanId(inlineTcPerson.id) : "";
    const person = peopleById.get(hrPersonId);
    if (!person) return { ...row, rosterPersonId, rosterPersonName: row.rosterPersonName || row.personName, identityStatus: mapping?.status || (inlineTcMatches.length > 1 ? "Belirsiz" : "Eşleşmedi"), identityMethod: mapping?.method || "" };
    return {
      ...row,
      rosterPersonId,
      rosterPersonName: row.rosterPersonName || row.personName,
      personId: hrPersonId,
      personName: person.name || row.personName,
      identityStatus: "Eşleşti",
      identityMethod: mapping?.method || (directPerson ? "Aynı Employee ID" : "Roster TC"),
      hrWarehouse: person.warehouse || "",
    };
  });
}
