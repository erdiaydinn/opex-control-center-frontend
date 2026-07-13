import React, { useEffect, useMemo, useState } from "react";
import {
  cancelReservation,
  editReservationAdmin,
  getSuppliers,
  getSlots,
  getReservations,
  updateReservationArrival,
  updateReservationStatus,
} from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

export default function AdminReservations() {
  const { t } = useDockOSUi();
  const [reservations, setReservations] = useState([]);
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("ALL");
  const [supplierFilter,setSupplierFilter]=useState("ALL");
  const [statusFilter,setStatusFilter]=useState("ALL");
  const [dateFilter,setDateFilter]=useState("");
  const [suppliers,setSuppliers]=useState([]);
  const [loading,setLoading]=useState(false);
  const [editTarget,setEditTarget]=useState(null);
  const [editForm,setEditForm]=useState(null);
  const [editSlots,setEditSlots]=useState([]);
  const [cancelTarget,setCancelTarget]=useState(null);
  const [cancelReason,setCancelReason]=useState("");

  async function loadData() {
    setLoading(true);
    try {
      const [data,sups] = await Promise.all([getReservations(),getSuppliers()]);
      setReservations(data || []); setSuppliers(sups||[]);
      setMessage(`${t("listRefreshed")} · ${data?.length || 0} ${t("record").toLocaleLowerCase()}.`);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
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
      const warehouseOk = warehouseFilter === "ALL" || r.warehouse_name === warehouseFilter;
      const supplierOk = supplierFilter === "ALL" || r.supplier_name === supplierFilter;
      const statusOk = statusFilter === "ALL" || r.status === statusFilter;
      const dateOk = !dateFilter || r.slot_date === dateFilter;

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

      return warehouseOk && supplierOk && statusOk && dateOk && text.includes(q);
    });
  }, [reservations, search, warehouseFilter, supplierFilter, statusFilter, dateFilter]);

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
    try {
      const result = await updateReservationArrival(
        reservation.reservation_no,
        reservation.arrival_check || {}
      );
      setMessage(result.message || "Kontrol kaydedildi.");
      await loadData();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function handleCancel() {
    if (!cancelTarget || cancelReason.trim().length < 5) return setMessage(t("cancelMin"));
    try {
      const result = await cancelReservation(cancelTarget.reservation_no, true, cancelReason.trim());
      setMessage(result.message || t("reservationCancelled"));
      setCancelTarget(null); setCancelReason("");
      await loadData();
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function openEdit(row) {
    try {
      const slots = await getSlots({ warehouse_name: row.warehouse_name });
      setEditSlots(slots);
      setEditTarget(row);
      setEditForm({ slot_date: row.slot_date, selected_slot: row.selected_slot, pallet_count: row.pallet_count, sku_count: row.sku_count, vehicle_plate: row.vehicle_plate || "", vehicle_type: row.vehicle_type || "", shipment_details: row.shipment_details || "", edit_reason: "" });
    } catch (error) { setMessage(error.message); }
  }

  async function saveEdit(event) {
    event.preventDefault();
    try {
      const result = await editReservationAdmin(editTarget.reservation_no, { ...editForm, pallet_count: Number(editForm.pallet_count), sku_count: Number(editForm.sku_count) });
      setMessage(result.message); setEditTarget(null); setEditForm(null);
      await loadData();
    } catch (error) { setMessage(error.message); }
  }

  async function handleStatus(reservationNo, status) {
    try {
      const result = await updateReservationStatus(reservationNo, { status, note: "" });
      setMessage(result.message);
      await loadData();
    } catch (error) {
      setMessage(error.message);
    }
  }

  function exportCsv() {
    const headers = ["reservation_no", "supplier_name", "warehouse_name", "shipment_mode", "slot_date", "selected_slot", "vehicle_plate", "cargo_tracking_no", "po_number", "status"];
    const escape = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const content = [headers.join(","), ...filteredReservations.map((row) => headers.map((key) => escape(row[key])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", content], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `dockos_rezervasyonlar_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <p style={styles.kicker}>{t("adminKicker")}</p>
        <h1 style={styles.title}>{t("adminTitle")}</h1>
        <p style={styles.subtitle}>{t("adminSubtitle")}</p>
      </section>

      <section style={styles.filterCard}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("searchReservation")}
          style={styles.searchInput}
        />

        <select
          value={warehouseFilter}
          onChange={(e) => setWarehouseFilter(e.target.value)}
          style={styles.select}
        >
          <option value="ALL">{t("allWarehouses")}</option>
          {warehouses.map((warehouse) => (
            <option key={warehouse} value={warehouse}>
              {warehouse}
            </option>
          ))}
        </select>

        <select value={supplierFilter} onChange={(e)=>setSupplierFilter(e.target.value)} style={styles.select}><option value="ALL">{t("allSuppliers")}</option>{suppliers.map(s=><option key={s.supplier_name}>{s.supplier_name}</option>)}</select>
        <select value={statusFilter} onChange={(e)=>setStatusFilter(e.target.value)} style={styles.select}><option value="ALL">{t("allStatuses")}</option><option value="APPROVED">{t("approved")}</option><option value="REVISION_REQUESTED">{t("revision")}</option><option value="COMPLETED">{t("completed")}</option><option value="CANCELLED">{t("cancelled")}</option></select>
        <input type="date" value={dateFilter} onChange={(e)=>setDateFilter(e.target.value)} style={styles.select} />
        <button type="button" onClick={loadData} disabled={loading} style={styles.refreshButton}>
          {loading ? t("refreshing") : t("refreshShort")}
        </button>
        <button type="button" onClick={exportCsv} style={styles.exportButton}>{t("downloadCsv")}</button>
      </section>

      {message && <div style={styles.message}>{message}</div>}

      <section style={styles.tableCard}>
        {filteredReservations.length === 0 ? (
          <div style={styles.empty}>{t("noMatching")}</div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>{t("reservation")}</th>
                <th style={styles.th}>{t("supplierLabel")}</th>
                <th style={styles.th}>{t("warehouseLabel")}</th>
                <th style={styles.th}>{t("dateTime")}</th>
                <th style={styles.th}>{t("palletSku")}</th>
                <th style={styles.th}>{t("vehiclePlate")}</th>
                <th style={styles.th}>{t("waybill")}</th>
                <th style={styles.th}>{t("arrived")}</th>
                <th style={styles.th}>{t("dockSuitable")}</th>
                <th style={styles.th}>{t("onTimeQuestion")}</th>
                <th style={styles.th}>{t("note")}</th>
                <th style={styles.th}>{t("action")}</th>
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
                      {r.pallet_count || 0} {t("palletUnit")}
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
                        placeholder={t("note")}
                        style={styles.textarea}
                      />
                    </td>

                    <td style={styles.td}>
                      <button
                        type="button"
                        onClick={() => saveArrivalCheck(r)}
                        style={styles.saveButton}
                      >
                        {t("save")}
                      </button>

                      {r.status !== "COMPLETED" && r.status !== "CANCELLED" && (
                        <button type="button" onClick={() => handleStatus(r.reservation_no, "COMPLETED")} style={styles.completeButton}>{t("complete")}</button>
                      )}
                      {r.status !== "REVISION_REQUESTED" && r.status !== "CANCELLED" && (
                        <button type="button" onClick={() => handleStatus(r.reservation_no, "REVISION_REQUESTED")} style={styles.revisionButton}>{t("revision")}</button>
                      )}

                      {r.shipment_mode === "SEVKIYAT" && r.status !== "CANCELLED" && <button type="button" onClick={() => openEdit(r)} style={styles.editButton}>{t("edit")}</button>}

                      {r.status !== "CANCELLED" && <button
                        type="button"
                        onClick={() => { setCancelTarget(r); setCancelReason(""); }}
                        style={styles.cancelButton}
                      >
                        {t("cancel")}
                      </button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      {editTarget && editForm && <div style={styles.overlay}><form onSubmit={saveEdit} style={styles.modal}><div style={styles.modalHead}><div><p style={styles.kicker}>{t("adminEdit")}</p><h2 style={styles.modalTitle}>{editTarget.reservation_no}</h2><span style={styles.muted}>{editTarget.supplier_name} · {editTarget.warehouse_name}</span></div><button type="button" onClick={() => setEditTarget(null)} style={styles.closeButton}>×</button></div><div style={styles.editGrid}><label>{t("date")}<input required type="date" value={editForm.slot_date} onChange={(e) => setEditForm({...editForm,slot_date:e.target.value,selected_slot:""})} /></label><label>{t("time")}<select required value={editForm.selected_slot} onChange={(e) => setEditForm({...editForm,selected_slot:e.target.value})}><option value="">{t("selectTime")}</option>{editSlots.filter((slot) => slot.date === editForm.slot_date).map((slot) => <option key={`${slot.date}-${slot.slot}`} value={slot.slot}>{slot.slot}</option>)}</select></label><label>{t("pallet")}<input required type="number" min="1" value={editForm.pallet_count} onChange={(e) => setEditForm({...editForm,pallet_count:e.target.value})} /></label><label>{t("sku")}<input required type="number" min="1" value={editForm.sku_count} onChange={(e) => setEditForm({...editForm,sku_count:e.target.value})} /></label><label>{t("vehicleType")}<select value={editForm.vehicle_type} onChange={(e) => setEditForm({...editForm,vehicle_type:e.target.value})}><option value="">{t("select")}</option><option value="KAMYON">{t("truck")}</option><option value="TIR">{t("semiTruck")}</option><option value="KAMYONET">{t("van")}</option></select></label><label>{t("plate")}<input required value={editForm.vehicle_plate} onChange={(e) => setEditForm({...editForm,vehicle_plate:e.target.value})} /></label></div><label style={styles.fullField}>{t("shipmentDetail")}<textarea required value={editForm.shipment_details} onChange={(e) => setEditForm({...editForm,shipment_details:e.target.value})} /></label><label style={styles.fullField}>{t("editReason")}<textarea required minLength="5" value={editForm.edit_reason} onChange={(e) => setEditForm({...editForm,edit_reason:e.target.value})} placeholder={t("emailReasonHelp")} /></label><button style={styles.modalSave}>{t("saveNotify")}</button></form></div>}
      {cancelTarget && <div style={styles.overlay}><section style={styles.cancelModal}><p style={styles.kicker}>{t("reservationCancel")}</p><h2 style={styles.modalTitle}>{cancelTarget.reservation_no}</h2><p>{cancelTarget.supplier_name} · {t("cancelEmailInfo")}</p><textarea value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder={t("cancelReasonPlaceholder")} style={styles.cancelReason} /><div style={styles.modalActions}><button type="button" onClick={() => setCancelTarget(null)} style={styles.closeAction}>{t("dismiss")}</button><button type="button" onClick={handleCancel} style={styles.cancelConfirm}>{t("cancelNotify")}</button></div></section></div>}
    </div>
  );
}

function BoolButtons({ value, onChange }) {
  const { t } = useDockOSUi();
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
        {t("yes")}
      </button>

      <button
        type="button"
        onClick={() => onChange(false)}
        style={{
          ...styles.boolButton,
          ...(value === false ? styles.boolNo : {}),
        }}
      >
        {t("no")}
      </button>
    </div>
  );
}

const styles = {
  page: { padding: 24, background: "var(--dockos-bg)", minHeight: "100vh", color: "var(--dockos-text)" },
  hero: { background: "var(--dockos-surface)", borderRadius: 24, padding: 24, border: "1px solid var(--dockos-border)", marginBottom: 18 },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "8px 0", fontSize: 30 },
  subtitle: { margin: 0, color: "var(--dockos-muted)" },

  filterCard: {
    background: "var(--dockos-surface)",
    borderRadius: 20,
    padding: 16,
    border: "1px solid var(--dockos-border)",
    marginBottom: 16,
    display: "grid",
    gridTemplateColumns: "minmax(240px,2fr) repeat(4,minmax(150px,1fr)) auto auto",
    gap: 12,
  },

  searchInput: {
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d1d5db",
    width: "100%",
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
  },

  select: {
    padding: "12px 14px",
    borderRadius: 14,
    border: "1px solid #d1d5db",
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
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
  exportButton: { border: "1px solid #d0d5dd", background: "var(--dockos-surface)", color: "var(--dockos-text)", borderRadius: 14, padding: "12px 16px", fontWeight: 900, cursor: "pointer" },

  message: {
    background: "var(--dockos-success-bg)",
    color: "var(--dockos-success-text)",
    padding: 14,
    borderRadius: 16,
    fontWeight: 900,
    marginBottom: 16,
  },

  tableCard: {
    background: "var(--dockos-surface)",
    borderRadius: 24,
    padding: 20,
    border: "1px solid var(--dockos-border)",
    overflowX: "auto",
  },

  table: { width: "100%", minWidth: 1450, borderCollapse: "collapse" },
  th: { textAlign: "left", padding: 12, borderBottom: "1px solid var(--dockos-border)", color: "var(--dockos-muted)", background: "var(--dockos-surface-alt)", fontSize: 13 },
  td: { padding: 12, borderBottom: "1px solid #f3f4f6", verticalAlign: "top", fontWeight: 700 },
  muted: { color: "var(--dockos-muted)", fontSize: 12 },

  boolWrap: { display: "flex", gap: 6 },
  boolButton: {
    minWidth: 58,
    border: "1px solid #d1d5db",
    background: "var(--dockos-surface)",
    color: "var(--dockos-text)",
    borderRadius: 999,
    padding: "7px 10px",
    fontWeight: 900,
    cursor: "pointer",
  },
  boolYes: { background: "var(--dockos-success-bg)", color: "var(--dockos-success-text)", border: "1px solid #34d399" },
  boolNo: { background: "var(--dockos-danger-bg)", color: "var(--dockos-danger-text)", border: "1px solid #fb7185" },

  textarea: {
    width: 230,
    minHeight: 70,
    borderRadius: 12,
    border: "1px solid #d1d5db",
    padding: 10,
    resize: "vertical",
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
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
    background: "var(--dockos-danger-bg)",
    color: "var(--dockos-danger-text)",
    borderRadius: 12,
    padding: "9px 10px",
    fontWeight: 900,
    cursor: "pointer",
  },

  completeButton: {
    display: "block", width: 90, border: "none", background: "var(--dockos-success-bg)", color: "var(--dockos-success-text)",
    borderRadius: 12, padding: "9px 10px", fontWeight: 900, cursor: "pointer", marginBottom: 8,
  },

  revisionButton: {
    display: "block", width: 90, border: "1px solid #fedf89", background: "var(--dockos-warning-bg)", color: "var(--dockos-warning-text)",
    borderRadius: 12, padding: "9px 10px", fontWeight: 900, cursor: "pointer", marginBottom: 8,
  },
  editButton: { display: "block", width: 90, border: "1px solid #84adff", background: "var(--dockos-info-bg)", color: "var(--dockos-info-text)", borderRadius: 12, padding: "9px 10px", fontWeight: 900, cursor: "pointer", marginBottom: 8 },
  overlay: { position: "fixed", inset: 0, zIndex: 1000, display: "grid", placeItems: "center", padding: 20, background: "rgba(16,24,40,.58)", backdropFilter: "blur(4px)" }, modal: { width: "min(780px,96vw)", maxHeight: "90vh", overflowY: "auto", padding: 22, borderRadius: 22, background: "var(--dockos-surface,#fff)", color: "var(--dockos-text,#101828)" }, modalHead: { display: "flex", justifyContent: "space-between", alignItems: "flex-start" }, modalTitle: { margin: "5px 0" }, closeButton: { width: 38, height: 38, border: "1px solid #d0d5dd", borderRadius: 10, background: "transparent", fontSize: 24, cursor: "pointer" }, editGrid: { display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 12, marginTop: 18 }, fullField: { display: "grid", gap: 6, marginTop: 12, fontWeight: 800 }, modalSave: { width: "100%", minHeight: 46, marginTop: 16, border: 0, borderRadius: 12, color: "#fff", background: "#e5005a", fontWeight: 900, cursor: "pointer" }, cancelModal: { width: "min(520px,94vw)", padding: 24, borderRadius: 22, background: "var(--dockos-surface,#fff)", color: "var(--dockos-text,#101828)" }, cancelReason: { boxSizing: "border-box", width: "100%", minHeight: 100, padding: 12, border: "1px solid #d0d5dd", borderRadius: 12 }, modalActions: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }, closeAction: { minHeight: 44, border: "1px solid #d0d5dd", borderRadius: 11, background: "transparent", fontWeight: 900 }, cancelConfirm: { minHeight: 44, border: 0, borderRadius: 11, color: "#fff", background: "#d92d20", fontWeight: 900 },

  empty: { padding: 20, color: "var(--dockos-muted)", fontWeight: 800 },
};
