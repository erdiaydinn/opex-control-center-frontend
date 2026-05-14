import React, { useEffect, useMemo, useState } from "react";
import {
  cancelReservation,
  getReservations,
  updateReservationArrival,
} from "./dockosApi";

export default function AdminReservations() {
  const [reservations, setReservations] = useState([]);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("ALL");

  async function loadData() {
    const data = await getReservations();
    setReservations(data || []);
    setMessage("Liste yenilendi.");
  }

  useEffect(() => {
    loadData();
  }, []);

  const warehouses = useMemo(
    () => [...new Set(reservations.map((r) => r.warehouse_name).filter(Boolean))],
    [reservations]
  );

  const filteredReservations = useMemo(() => {
    const q = search.trim().toLowerCase();

    return reservations.filter((r) => {
      const warehouseOk =
        warehouseFilter === "ALL" || r.warehouse_name === warehouseFilter;

      const text = [
        r.reservation_no,
        r.supplier_name,
        r.warehouse_name,
        r.slot_date,
        r.selected_slot,
        r.vehicle_type,
        r.vehicle_plate,
        r.waybill_info,
        r.po_number,
        ...(r.po_numbers || []),
      ]
        .join(" ")
        .toLowerCase();

      return warehouseOk && text.includes(q);
    });
  }, [reservations, search, warehouseFilter]);

  function updateLocal(reservationNo, field, value) {
    setReservations((prev) =>
      prev.map((r) =>
        r.reservation_no === reservationNo
          ? {
              ...r,
              arrival_check: {
                ...(r.arrival_check || {}),
                [field]: value,
              },
            }
          : r
      )
    );
  }

  async function saveArrivalCheck(reservation) {
    const result = await updateReservationArrival(
      reservation.reservation_no,
      reservation.arrival_check || {}
    );

    setMessage(result.message || "Kontrol kaydedildi.");
    await loadData();
  }

  async function handleCancel(reservationNo) {
    const result = await cancelReservation(reservationNo);
    setMessage(result.message || "Rezervasyon iptal edildi.");
    await loadData();
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <p style={styles.kicker}>DockOS · Merkez Depo</p>
        <h1 style={styles.title}>Rezervasyon Kontrol Ekranı</h1>
        <p style={styles.subtitle}>
          Gelen sevkiyatları plaka, tedarikçi, irsaliye veya PO ile arayın.
        </p>
      </section>

      <section style={styles.filterCard}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rezervasyon no, tedarikçi, plaka, irsaliye veya PO ara..."
          style={styles.searchInput}
        />

        <select
          value={warehouseFilter}
          onChange={(e) => setWarehouseFilter(e.target.value)}
          style={styles.select}
        >
          <option value="ALL">Tüm Merkez Depolar</option>
          {warehouses.map((warehouse) => (
            <option key={warehouse} value={warehouse}>
              {warehouse}
            </option>
          ))}
        </select>

        <button type="button" onClick={loadData} style={styles.refreshButton}>
          Yenile
        </button>
      </section>

      {message && <div style={styles.message}>{message}</div>}

      <section style={styles.tableCard}>
        {filteredReservations.length === 0 ? (
          <div style={styles.empty}>Kriterlere uygun rezervasyon yok.</div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Rezervasyon</th>
                <th style={styles.th}>Tedarikçi</th>
                <th style={styles.th}>Depo</th>
                <th style={styles.th}>Tarih / Saat</th>
                <th style={styles.th}>Palet / SKU</th>
                <th style={styles.th}>Araç / Plaka</th>
                <th style={styles.th}>İrsaliye</th>
                <th style={styles.th}>Geldi mi?</th>
                <th style={styles.th}>Rampa uygun mu?</th>
                <th style={styles.th}>Saatinde mi?</th>
                <th style={styles.th}>Not</th>
                <th style={styles.th}>Aksiyon</th>
              </tr>
            </thead>

            <tbody>
              {filteredReservations.map((r) => {
                const check = r.arrival_check || {};

                return (
                  <tr key={r.reservation_no}>
                    <td style={styles.td}>
                      <strong>{r.reservation_no}</strong>
                      <br />
                      <span style={styles.muted}>{r.status}</span>
                    </td>

                    <td style={styles.td}>{r.supplier_name || "-"}</td>
                    <td style={styles.td}>{r.warehouse_name || "-"}</td>

                    <td style={styles.td}>
                      {r.slot_date || "-"}
                      <br />
                      <strong>{r.selected_slot || "-"}</strong>
                    </td>

                    <td style={styles.td}>
                      {r.pallet_count || 0} palet
                      <br />
                      {r.sku_count || 0} SKU
                    </td>

                    <td style={styles.td}>
                      <strong>{r.vehicle_type || "-"}</strong>
                      <br />
                      {r.vehicle_plate || "-"}
                    </td>

                    <td style={styles.td}>{r.waybill_info || "-"}</td>

                    <td style={styles.td}>
                      <BoolButtons
                        value={check.arrived}
                        onChange={(v) => updateLocal(r.reservation_no, "arrived", v)}
                      />
                    </td>

                    <td style={styles.td}>
                      <BoolButtons
                        value={check.dock_compatible}
                        onChange={(v) =>
                          updateLocal(r.reservation_no, "dock_compatible", v)
                        }
                      />
                    </td>

                    <td style={styles.td}>
                      <BoolButtons
                        value={check.on_time}
                        onChange={(v) => updateLocal(r.reservation_no, "on_time", v)}
                      />
                    </td>

                    <td style={styles.td}>
                      <textarea
                        value={check.note || ""}
                        onChange={(e) =>
                          updateLocal(r.reservation_no, "note", e.target.value)
                        }
                        placeholder="Örn: Araç rampaya uygun değildi, 20 dk geç geldi."
                        style={styles.textarea}
                      />
                    </td>

                    <td style={styles.td}>
                      <button
                        type="button"
                        onClick={() => saveArrivalCheck(r)}
                        style={styles.saveButton}
                      >
                        Kaydet
                      </button>

                      <button
                        type="button"
                        onClick={() => handleCancel(r.reservation_no)}
                        style={styles.cancelButton}
                      >
                        İptal
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function BoolButtons({ value, onChange }) {
  return (
    <div style={styles.boolWrap}>
      <button
        type="button"
        onClick={() => onChange(true)}
        style={{
          ...styles.boolButton,
          ...(value === true ? styles.boolYes : {}),
        }}
      >
        Evet
      </button>

      <button
        type="button"
        onClick={() => onChange(false)}
        style={{
          ...styles.boolButton,
          ...(value === false ? styles.boolNo : {}),
        }}
      >
        Hayır
      </button>
    </div>
  );
}

const styles = {
  page: { padding: 24, background: "#f7f8fb", minHeight: "100vh", color: "#111827" },
  hero: { background: "#fff", borderRadius: 24, padding: 24, border: "1px solid #e5e7eb", marginBottom: 18 },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "8px 0", fontSize: 30 },
  subtitle: { margin: 0, color: "#6b7280" },

  filterCard: {
    background: "#fff",
    borderRadius: 20,
    padding: 16,
    border: "1px solid #e5e7eb",
    marginBottom: 16,
    display: "grid",
    gridTemplateColumns: "2fr 1fr auto",
    gap: 12,
  },

  searchInput: {
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d1d5db",
    width: "100%",
    color: "#111827",
    background: "#fff",
  },

  select: {
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d1d5db",
    color: "#111827",
    background: "#fff",
  },

  refreshButton: {
    border: "none",
    background: "#111827",
    color: "#fff",
    borderRadius: 14,
    padding: "12px 16px",
    fontWeight: 900,
    cursor: "pointer",
  },

  message: {
    background: "#ecfdf5",
    color: "#065f46",
    padding: 14,
    borderRadius: 16,
    fontWeight: 900,
    marginBottom: 16,
  },

  tableCard: {
    background: "#fff",
    borderRadius: 24,
    padding: 20,
    border: "1px solid #e5e7eb",
    overflowX: "auto",
  },

  table: { width: "100%", minWidth: 1450, borderCollapse: "collapse" },
  th: { textAlign: "left", padding: 12, borderBottom: "1px solid #e5e7eb", color: "#6b7280", fontSize: 13 },
  td: { padding: 12, borderBottom: "1px solid #f3f4f6", verticalAlign: "top", fontWeight: 700 },
  muted: { color: "#6b7280", fontSize: 12 },

  boolWrap: { display: "flex", gap: 6 },
  boolButton: {
    border: "1px solid #d1d5db",
    background: "#fff",
    color: "#111827",
    borderRadius: 999,
    padding: "7px 10px",
    fontWeight: 900,
    cursor: "pointer",
  },
  boolYes: { background: "#ecfdf5", color: "#047857", borderColor: "#34d399" },
  boolNo: { background: "#fff1f2", color: "#be123c", borderColor: "#fb7185" },

  textarea: {
    width: 230,
    minHeight: 70,
    borderRadius: 12,
    border: "1px solid #d1d5db",
    padding: 10,
    resize: "vertical",
    color: "#111827",
    background: "#fff",
  },

  saveButton: {
    display: "block",
    width: 90,
    border: "none",
    background: "#DF1067",
    color: "#fff",
    borderRadius: 12,
    padding: "9px 10px",
    fontWeight: 900,
    cursor: "pointer",
    marginBottom: 8,
  },

  cancelButton: {
    display: "block",
    width: 90,
    border: "1px solid #fecaca",
    background: "#fff1f2",
    color: "#be123c",
    borderRadius: 12,
    padding: "9px 10px",
    fontWeight: 900,
    cursor: "pointer",
  },

  empty: { padding: 20, color: "#6b7280", fontWeight: 800 },
};