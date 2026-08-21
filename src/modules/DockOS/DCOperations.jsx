import React, { useEffect, useMemo, useState } from "react";
import {
  getOperationsBoard,
  getWarehouses,
  updateReservationArrival,
} from "./dockosApi";

const today = new Date().toISOString().slice(0, 10);

function Metric({ label, value }) {
  return <div style={styles.metric}><span>{label}</span><strong>{value}</strong></div>;
}

function BoolSelect({ value, onChange }) {
  return (
    <select value={value === null || value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "true")} style={styles.select}>
      <option value="">Seçiniz</option>
      <option value="true">Evet</option>
      <option value="false">Hayır</option>
    </select>
  );
}

export default function DCOperations() {
  const [warehouses, setWarehouses] = useState([]);
  const [warehouse, setWarehouse] = useState("Ankara DC");
  const [boardDate, setBoardDate] = useState(today);
  const [board, setBoard] = useState({ summary: {}, rows: [] });
  const [drafts, setDrafts] = useState({});
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const [warehouseRows, boardData] = await Promise.all([
        getWarehouses(),
        getOperationsBoard({ warehouse_name: warehouse, board_date: boardDate }),
      ]);
      setWarehouses(warehouseRows || []);
      setBoard(boardData || { summary: {}, rows: [] });
      const initial = {};
      (boardData?.rows || []).forEach((r) => {
        initial[r.reservation_no] = {
          arrived: r.arrival_check?.arrived ?? null,
          dock_compatible: r.arrival_check?.dock_compatible ?? null,
          on_time: r.arrival_check?.on_time ?? null,
          note: r.arrival_check?.note || "",
          dock_no: r.arrival_check?.dock_no || "",
        };
      });
      setDrafts(initial);
    } catch (error) {
      setMessage(error.message || "Operasyon panosu yüklenemedi.");
    }
  }

  useEffect(() => { load(); }, [warehouse, boardDate]);

  const rows = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("tr-TR");
    if (!q) return board.rows || [];
    return (board.rows || []).filter((r) => [r.reservation_no, r.supplier_name, r.vehicle_plate, r.po_number, r.selected_slot].join(" ").toLocaleLowerCase("tr-TR").includes(q));
  }, [board.rows, search]);

  function patch(no, key, value) {
    setDrafts((prev) => ({ ...prev, [no]: { ...(prev[no] || {}), [key]: value } }));
  }

  async function save(row) {
    const draft = drafts[row.reservation_no] || {};
    if (draft.arrived === null || draft.dock_compatible === null || draft.on_time === null) {
      setMessage("Geldi, rampaya uygun ve zamanında alanlarını doldur.");
      return;
    }
    const result = await updateReservationArrival(row.reservation_no, draft);
    setMessage(result.message || "Kontrol kaydedildi.");
    await load();
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div><p style={styles.kicker}>DockOS · DC Operations</p><h1 style={styles.title}>Merkez Depo Operasyon Kontrolü</h1><p style={styles.subtitle}>Plaka, tedarikçi, PO ve rezervasyon üzerinden araç gelişini yönetin.</p></div>
        <button style={styles.refresh} onClick={load}>Yenile</button>
      </section>

      <section style={styles.filters}>
        <select value={warehouse} onChange={(e) => setWarehouse(e.target.value)} style={styles.input}>
          {warehouses.map((x) => <option key={x.warehouse_name}>{x.warehouse_name}</option>)}
        </select>
        <input type="date" value={boardDate} onChange={(e) => setBoardDate(e.target.value)} style={styles.input} />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Plaka, tedarikçi, PO veya rezervasyon ara" style={{ ...styles.input, flex: 1 }} />
      </section>

      <section style={styles.metrics}>
        <Metric label="Toplam" value={board.summary?.total || 0} />
        <Metric label="Bekliyor" value={board.summary?.waiting || 0} />
        <Metric label="Geldi" value={board.summary?.arrived || 0} />
        <Metric label="Geç" value={board.summary?.late || 0} />
        <Metric label="No-show" value={board.summary?.no_show || 0} />
      </section>

      {message && <div style={styles.message}>{message}</div>}

      <section style={styles.tableWrap}>
        <table style={styles.table}>
          <thead><tr><th>Saat</th><th>Rezervasyon</th><th>Tedarikçi / PO</th><th>Plaka</th><th>Geldi mi?</th><th>Rampaya uygun?</th><th>Zamanında mı?</th><th>Rampa</th><th>Not</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan="10" style={styles.empty}>Seçili gün için rezervasyon yok.</td></tr> : rows.map((row) => {
              const d = drafts[row.reservation_no] || {};
              return <tr key={row.reservation_no}>
                <td><strong>{row.selected_slot}</strong><small style={styles.small}>{row.slot_date}</small></td>
                <td><strong>{row.reservation_no}</strong><small style={styles.small}>{row.status}</small></td>
                <td><strong>{row.supplier_name}</strong><small style={styles.small}>{row.po_number}</small></td>
                <td><strong>{row.vehicle_plate || "—"}</strong><small style={styles.small}>{row.vehicle_type || ""}</small></td>
                <td><BoolSelect value={d.arrived} onChange={(v) => patch(row.reservation_no, "arrived", v)} /></td>
                <td><BoolSelect value={d.dock_compatible} onChange={(v) => patch(row.reservation_no, "dock_compatible", v)} /></td>
                <td><BoolSelect value={d.on_time} onChange={(v) => patch(row.reservation_no, "on_time", v)} /></td>
                <td><input value={d.dock_no || ""} onChange={(e) => patch(row.reservation_no, "dock_no", e.target.value)} placeholder="Rampa 1" style={styles.compactInput} /></td>
                <td><input value={d.note || ""} onChange={(e) => patch(row.reservation_no, "note", e.target.value)} placeholder="Varsa not" style={styles.noteInput} /></td>
                <td><button onClick={() => save(row)} style={styles.save}>Kaydet</button></td>
              </tr>;
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}

const styles = {
  page: { display: "grid", gap: 16 }, hero: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 24, background: "white", borderRadius: 24 }, kicker: { margin: 0, color: "#DF1067", fontWeight: 900 }, title: { margin: "6px 0", fontSize: 28 }, subtitle: { margin: 0, color: "#667085" }, refresh: { border: 0, borderRadius: 14, padding: "12px 18px", background: "#111827", color: "white", fontWeight: 900, cursor: "pointer" }, filters: { display: "flex", gap: 10, padding: 14, background: "white", borderRadius: 18 }, input: { minHeight: 44, border: "1px solid #d0d5dd", borderRadius: 12, padding: "0 12px" }, metrics: { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }, metric: { padding: 16, background: "white", borderRadius: 18 }, message: { padding: 12, borderRadius: 12, background: "#fff1f5", color: "#9f1239", fontWeight: 800 }, tableWrap: { overflowX: "auto", background: "white", borderRadius: 20 }, table: { width: "100%", borderCollapse: "collapse", minWidth: 1250 }, select: { width: 105, minHeight: 38, border: "1px solid #d0d5dd", borderRadius: 10 }, compactInput: { width: 90, minHeight: 38, border: "1px solid #d0d5dd", borderRadius: 10, padding: "0 8px" }, noteInput: { width: 180, minHeight: 38, border: "1px solid #d0d5dd", borderRadius: 10, padding: "0 8px" }, save: { border: 0, borderRadius: 10, padding: "10px 13px", background: "#DF1067", color: "white", fontWeight: 900, cursor: "pointer" }, small: { display: "block", marginTop: 4, color: "#667085" }, empty: { textAlign: "center", padding: 36, color: "#667085" },
};
