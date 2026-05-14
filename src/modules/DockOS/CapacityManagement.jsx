import React, { useMemo, useState } from "react";

const WAREHOUSES = [
  "Ankara DC",
  "İstanbul Avrupa DC",
  "İstanbul Anadolu DC",
  "İzmir DC",
];

const HOURS = [
  "06:00 - 07:00", "07:00 - 08:00", "08:00 - 09:00",
  "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00",
  "12:00 - 13:00", "13:00 - 14:00", "14:00 - 15:00",
  "15:00 - 16:00", "16:00 - 17:00", "17:00 - 18:00",
  "18:00 - 19:00", "19:00 - 20:00", "20:00 - 21:00",
  "21:00 - 22:00", "22:00 - 23:00", "23:00 - 00:00",
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

function datesBetween(start, end) {
  const result = [];
  const current = new Date(start);
  const last = new Date(end);

  while (current <= last) {
    result.push(current.toISOString().slice(0, 10));
    current.setDate(current.getDate() + 1);
  }

  return result;
}

export default function CapacityManagement() {
  const [warehouse, setWarehouse] = useState("Ankara DC");
  const [startDate, setStartDate] = useState(today());
  const [endDate, setEndDate] = useState(today());
  const [selectedHours, setSelectedHours] = useState(["08:00 - 09:00"]);
  const [palletLimit, setPalletLimit] = useState(40);
  const [skuLimit, setSkuLimit] = useState(500);

  const [rows, setRows] = useState(() => {
    const saved = localStorage.getItem("dockos_capacity_rows");
    return saved ? JSON.parse(saved) : [];
  });

  const selectedDates = useMemo(
    () => datesBetween(startDate, endDate),
    [startDate, endDate]
  );

  function saveRows(nextRows) {
    localStorage.setItem("dockos_capacity_rows", JSON.stringify(nextRows));
    setRows(nextRows);
  }

  function toggleHour(hour) {
    setSelectedHours((prev) =>
      prev.includes(hour)
        ? prev.filter((h) => h !== hour)
        : [...prev, hour]
    );
  }

  function applyPreset(type) {
    if (type === "light") {
      setPalletLimit(20);
      setSkuLimit(250);
    }

    if (type === "standard") {
      setPalletLimit(40);
      setSkuLimit(500);
    }

    if (type === "heavy") {
      setPalletLimit(70);
      setSkuLimit(900);
    }
  }

  function applyLimits() {
    const newRows = [];

    selectedDates.forEach((date) => {
      selectedHours.forEach((hour) => {
        newRows.push({
          id: `${warehouse}-${date}-${hour}`,
          warehouse,
          date,
          hour,
          palletLimit: Number(palletLimit),
          skuLimit: Number(skuLimit),
          usedPallet: 0,
          usedSku: 0,
        });
      });
    });

    const filtered = rows.filter(
      (row) => !newRows.some((newRow) => newRow.id === row.id)
    );

    const updated = [...filtered, ...newRows].sort((a, b) =>
      `${a.date}-${a.hour}`.localeCompare(`${b.date}-${b.hour}`)
    );

    saveRows(updated);
  }

  function simulateReservation(id) {
    const updated = rows.map((row) =>
      row.id === id
        ? {
            ...row,
            usedPallet: Math.min(row.palletLimit, row.usedPallet + 5),
            usedSku: Math.min(row.skuLimit, row.usedSku + 60),
          }
        : row
    );

    saveRows(updated);
  }

  function clearWarehouseCapacity() {
    const updated = rows.filter((row) => row.warehouse !== warehouse);
    saveRows(updated);
  }

  const filteredRows = rows.filter((row) => row.warehouse === warehouse);

  const totals = useMemo(() => {
    const totalPallet = filteredRows.reduce((a, r) => a + r.palletLimit, 0);
    const usedPallet = filteredRows.reduce((a, r) => a + r.usedPallet, 0);
    const totalSku = filteredRows.reduce((a, r) => a + r.skuLimit, 0);
    const usedSku = filteredRows.reduce((a, r) => a + r.usedSku, 0);

    return {
      totalPallet,
      usedPallet,
      remainingPallet: totalPallet - usedPallet,
      totalSku,
      usedSku,
      remainingSku: totalSku - usedSku,
    };
  }, [filteredRows]);

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <p style={styles.kicker}>DockOS · Admin</p>
        <h1 style={styles.title}>Slot & Kapasite Yönetimi</h1>
        <p style={styles.subtitle}>
          Merkez depo, tarih aralığı ve saat bazlı palet/SKU limiti tanımlayın.
        </p>
      </section>

      <section style={styles.panel}>
        <div style={styles.grid3}>
          <Field label="Merkez Depo">
            <select
              value={warehouse}
              onChange={(e) => setWarehouse(e.target.value)}
              style={styles.input}
            >
              {WAREHOUSES.map((w) => (
                <option key={w}>{w}</option>
              ))}
            </select>
          </Field>

          <Field label="Başlangıç Tarihi">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.input}
            />
          </Field>

          <Field label="Bitiş Tarihi">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.input}
            />
          </Field>
        </div>

        <div style={styles.presetRow}>
          <button type="button" onClick={() => applyPreset("light")} style={styles.ghostButton}>
            Hafif Gün
          </button>
          <button type="button" onClick={() => applyPreset("standard")} style={styles.ghostButton}>
            Standart Gün
          </button>
          <button type="button" onClick={() => applyPreset("heavy")} style={styles.ghostButton}>
            Yoğun Gün
          </button>
        </div>

        <div style={styles.grid2}>
          <Field label="Palet Limiti">
            <input
              type="number"
              value={palletLimit}
              onChange={(e) => setPalletLimit(e.target.value)}
              style={styles.input}
            />
          </Field>

          <Field label="SKU Limiti">
            <input
              type="number"
              value={skuLimit}
              onChange={(e) => setSkuLimit(e.target.value)}
              style={styles.input}
            />
          </Field>
        </div>

        <label style={styles.label}>Saat Seçimi</label>
        <div style={styles.hourGrid}>
          {HOURS.map((hour) => (
            <button
              key={hour}
              type="button"
              onClick={() => toggleHour(hour)}
              style={{
                ...styles.hourButton,
                ...(selectedHours.includes(hour) ? styles.hourButtonActive : {}),
              }}
            >
              {hour}
            </button>
          ))}
        </div>

        <button type="button" onClick={applyLimits} style={styles.primaryButton}>
          Seçili Tarih ve Saatlere Limiti Uygula
        </button>

        <button type="button" onClick={clearWarehouseCapacity} style={styles.dangerButton}>
          Bu Merkez Deponun Kapasitesini Temizle
        </button>
      </section>

      <section style={styles.summaryGrid}>
        <Summary title="Toplam Palet" value={totals.totalPallet} />
        <Summary title="Kullanılan Palet" value={totals.usedPallet} />
        <Summary title="Kalan Palet" value={totals.remainingPallet} />
        <Summary title="Toplam SKU" value={totals.totalSku} />
        <Summary title="Kullanılan SKU" value={totals.usedSku} />
        <Summary title="Kalan SKU" value={totals.remainingSku} />
      </section>

      <section style={styles.tableCard}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Tarih</th>
              <th style={styles.th}>Saat</th>
              <th style={styles.th}>Palet Limit</th>
              <th style={styles.th}>SKU Limit</th>
              <th style={styles.th}>Kullanılan</th>
              <th style={styles.th}>Kalan</th>
              <th style={styles.th}>Durum</th>
              <th style={styles.th}>Test</th>
            </tr>
          </thead>

          <tbody>
            {filteredRows.map((row) => {
              const remainingPallet = row.palletLimit - row.usedPallet;
              const remainingSku = row.skuLimit - row.usedSku;
              const isFull = remainingPallet <= 0 || remainingSku <= 0;

              return (
                <tr key={row.id}>
                  <td style={styles.td}>{row.date}</td>
                  <td style={styles.td}>{row.hour}</td>
                  <td style={styles.td}>{row.palletLimit}</td>
                  <td style={styles.td}>{row.skuLimit}</td>
                  <td style={styles.td}>
                    {row.usedPallet} palet / {row.usedSku} SKU
                  </td>
                  <td style={styles.td}>
                    {remainingPallet} palet / {remainingSku} SKU
                  </td>
                  <td style={styles.td}>
                    <span style={{ ...styles.status, ...(isFull ? styles.full : styles.open) }}>
                      {isFull ? "Dolu" : "Açık"}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <button
                      type="button"
                      onClick={() => simulateReservation(row.id)}
                      style={styles.smallButton}
                    >
                      + Test
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label style={styles.label}>{label}</label>
      {children}
    </div>
  );
}

function Summary({ title, value }) {
  return (
    <div style={styles.summaryCard}>
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

const styles = {
  page: { padding: 24, background: "#f5f7fb", minHeight: "100vh", color: "#111827" },
  hero: { background: "#fff", borderRadius: 24, padding: 24, marginBottom: 18, border: "1px solid #e5e7eb" },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "8px 0", fontSize: 30 },
  subtitle: { margin: 0, color: "#6b7280" },
  panel: { background: "#fff", borderRadius: 24, padding: 22, border: "1px solid #e5e7eb", marginBottom: 18, display: "grid", gap: 16 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  grid3: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 },
  label: { display: "block", marginBottom: 8, fontWeight: 800, fontSize: 13 },
  input: { width: "100%", boxSizing: "border-box", padding: "12px 14px", borderRadius: 14, border: "1px solid #d1d5db" },
  presetRow: { display: "flex", gap: 10, flexWrap: "wrap" },
  ghostButton: { border: "1px solid #d1d5db", background: "#fff", color: "#111827", borderRadius: 999, padding: "10px 14px", fontWeight: 900, cursor: "pointer" },
  hourGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10 },
  hourButton: { border: "1px solid #d1d5db", background: "#fff", color: "#111827", borderRadius: 14, padding: "12px 10px", cursor: "pointer", fontWeight: 900 },
  hourButtonActive: { borderColor: "#DF1067", background: "#fff0f6", color: "#DF1067" },
  primaryButton: { border: "none", background: "#DF1067", color: "#fff", borderRadius: 16, padding: "14px 18px", fontWeight: 900, cursor: "pointer" },
  dangerButton: { border: "1px solid #fecaca", background: "#fff1f2", color: "#be123c", borderRadius: 16, padding: "12px 18px", fontWeight: 900, cursor: "pointer" },
  summaryGrid: { display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 18 },
  summaryCard: { background: "#fff", borderRadius: 18, padding: 16, border: "1px solid #e5e7eb", display: "grid", gap: 8 },
  tableCard: { background: "#fff", borderRadius: 24, padding: 20, border: "1px solid #e5e7eb", overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse", minWidth: 980 },
  th: { textAlign: "left", padding: 12, borderBottom: "1px solid #e5e7eb", color: "#6b7280", fontSize: 13 },
  td: { padding: 12, borderBottom: "1px solid #f3f4f6", fontWeight: 700 },
  status: { display: "inline-block", padding: "6px 10px", borderRadius: 999, fontSize: 12, fontWeight: 900 },
  open: { background: "#ecfdf5", color: "#047857" },
  full: { background: "#fff7ed", color: "#c2410c" },
  smallButton: { border: "none", background: "#111827", color: "#fff", borderRadius: 12, padding: "8px 10px", cursor: "pointer", fontWeight: 800 },
};