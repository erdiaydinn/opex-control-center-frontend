import Holidays from "date-holidays";

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return isoDate(date);
}

function interval(id, name, startAt, endAt, year, projected = false) {
  return {
    id: `TR-${year}-${id}`,
    name,
    startAt: `${startAt}+03:00`,
    endAt: `${endAt}+03:00`,
    scope: "Tüm Türkiye",
    active: !projected,
    source: projected ? "Takvim projeksiyonu" : "T.C. Diyanet / 2429 sayılı Kanun",
    verification: projected ? "2036 sonrası resmî yayımla doğrulanmalı" : "Resmî takvim",
    projected,
  };
}

export function generateTurkeyHolidays(startYear = 2026, endYear = 2050) {
  const calendar = new Holidays("TR");
  const results = [];
  for (let year = startYear; year <= endYear; year += 1) {
    const projected = year > 2035;
    const publicDays = calendar.getHolidays(year).filter((item) => item.type === "public");
    publicDays.forEach((item) => {
      const date = item.date.slice(0, 10);
      if (item.name.includes("Ramazan")) {
        const eve = addDays(date, -1);
        results.push(interval("RAMAZAN-ARIFE", "Ramazan Bayramı Arifesi", `${eve}T13:00:00`, `${eve}T23:59:59`, year, projected));
        for (let day = 0; day < 3; day += 1) {
          const current = addDays(date, day);
          results.push(interval(`RAMAZAN-${day + 1}`, `Ramazan Bayramı ${day + 1}. Gün`, `${current}T00:00:00`, `${current}T23:59:59`, year, projected));
        }
        return;
      }
      if (item.name.includes("Kurban")) {
        const eve = addDays(date, -1);
        results.push(interval("KURBAN-ARIFE", "Kurban Bayramı Arifesi", `${eve}T13:00:00`, `${eve}T23:59:59`, year, projected));
        for (let day = 0; day < 4; day += 1) {
          const current = addDays(date, day);
          results.push(interval(`KURBAN-${day + 1}`, `Kurban Bayramı ${day + 1}. Gün`, `${current}T00:00:00`, `${current}T23:59:59`, year, projected));
        }
        return;
      }
      if (item.name.includes("Cumhuriyet")) {
        const eve = `${year}-10-28`;
        results.push(interval("CUMHURIYET", "Cumhuriyet Bayramı", `${eve}T13:00:00`, `${date}T23:59:59`, year, projected));
        return;
      }
      results.push(interval(item.name.toLocaleUpperCase("tr-TR").replaceAll(/[^A-ZÇĞİÖŞÜ0-9]+/g, "-"), item.name, `${date}T00:00:00`, `${date}T23:59:59`, year, projected));
    });
  }
  return results.filter((item, index, rows) => rows.findIndex((candidate) => candidate.id === item.id) === index);
}
