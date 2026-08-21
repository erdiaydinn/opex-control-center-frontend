import React, { useEffect, useMemo, useState } from "react";
import {
  cancelReservation,
  createReservation,
  getPurchaseOrders,
  getReservations,
  getSlots,
  getMySuppliers,
  getWarehouses,
} from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const USER_NAME = "Erdi Aydın";

export default function SupplierReservation() {
  const { t } = useDockOSUi();
  const [shipmentMode, setShipmentMode] = useState("SEVKIYAT");
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [supplierName, setSupplierName] = useState("");
  const [warehouseName, setWarehouseName] = useState("Ankara DC");

  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [slots, setSlots] = useState([]);
  const [selectedPoNumbers, setSelectedPoNumbers] = useState([]);

  const [palletCount, setPalletCount] = useState("");
  const [skuCount, setSkuCount] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedSlot, setSelectedSlot] = useState("");

  const [shipmentDetails, setShipmentDetails] = useState("");
  const [waybillInfo, setWaybillInfo] = useState("");
  const [vehicleType, setVehicleType] = useState("");
  const [vehicleCount, setVehicleCount] = useState("");
  const [vehiclePlate, setVehiclePlate] = useState("");
  const [shipmentForm, setShipmentForm] = useState("");
  const [boxCount, setBoxCount] = useState("");

  const [cargoDate, setCargoDate] = useState("");
  const [cargoTrackingNo, setCargoTrackingNo] = useState("");

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadLookups() {
    const supplierRows = await getMySuppliers();
    const nextSupplier = supplierName || supplierRows[0]?.supplier_name || "";
    const warehouseRows = await getWarehouses(nextSupplier);
    const nextWarehouse = warehouseRows.some((row) => row.warehouse_name === warehouseName)
      ? warehouseName
      : warehouseRows[0]?.warehouse_name || "";
    setSuppliers(supplierRows);
    setWarehouses(warehouseRows);
    setSupplierName(nextSupplier);
    setWarehouseName(nextWarehouse);
    return { supplier: nextSupplier, warehouse: nextWarehouse };
  }

  async function loadOperationalData(currentSupplier = supplierName, currentWarehouse = warehouseName) {
    const [poRows, reservationRows, slotRows] = await Promise.all([
      getPurchaseOrders(currentSupplier, currentWarehouse),
      getReservations({ supplier_name: currentSupplier }),
      getSlots({ warehouse_name: currentWarehouse, supplier_name: currentSupplier }),
    ]);
    setPurchaseOrders(poRows);
    setReservations(reservationRows);
    setSlots(slotRows);
  }

  useEffect(() => {
    (async () => {
      try {
        const lookup = await loadLookups();
        await loadOperationalData(lookup.supplier, lookup.warehouse);
      } catch (error) {
        setMessage(error.message);
      }
    })();
  }, []);

  const availableDates = useMemo(
    () => [...new Set(slots.map((row) => row.date))].sort(),
    [slots],
  );

  const suitableSlots = useMemo(() => {
    const pallet = Number(palletCount);
    const sku = Number(skuCount);
    if (!selectedDate || !pallet || !sku) return [];
    return slots.filter(
      (row) =>
        row.date === selectedDate &&
        row.remaining_pallet >= pallet &&
        row.remaining_sku >= sku,
    );
  }, [slots, selectedDate, palletCount, skuCount]);

  function togglePo(poNumber) {
    setSelectedPoNumbers((current) =>
      current.includes(poNumber)
        ? current.filter((item) => item !== poNumber)
        : [...current, poNumber],
    );
  }

  async function changeSupplier(event) {
    const value = event.target.value;
    setSupplierName(value);
    setSelectedPoNumbers([]);
    setMessage("");
    try {
      const warehouseRows = await getWarehouses(value);
      const nextWarehouse = warehouseRows[0]?.warehouse_name || "";
      setWarehouses(warehouseRows);
      setWarehouseName(nextWarehouse);
      await loadOperationalData(value, nextWarehouse);
    } catch (error) {
      setMessage(error.message);
    }
  }

  async function changeWarehouse(event) {
    const value = event.target.value;
    setWarehouseName(value);
    setSelectedPoNumbers([]);
    setSelectedDate("");
    setSelectedSlot("");
    setMessage("");
    try {
      await loadOperationalData(supplierName, value);
    } catch (error) {
      setMessage(error.message);
    }
  }

  function validate() {
    if (shipmentMode === "SEVKIYAT") {
      if (!selectedPoNumbers.length) return t("selectPo");
      if (Number(skuCount) <= 0) return t("skuRequired");
      if (Number(palletCount) <= 0) return t("palletRequired");
      if (!selectedDate || !selectedSlot) return t("reservationDateRequired");
      if (!vehiclePlate.trim()) return t("plateRequired");
      if (shipmentDetails.trim().length < 5) return t("shipmentMin");
    }

    if (shipmentMode === "KARGO") {
      if (!cargoDate) return t("cargoDateRequired");
      if (!cargoTrackingNo.trim()) return t("trackingRequired");
    }

    return "";
  }

  async function submit(event) {
    event.preventDefault();
    const errorMessage = validate();
    if (errorMessage) {
      setMessage(errorMessage);
      return;
    }

    setLoading(true);
    setMessage("");
    try {
      const result = await createReservation({
        po_number: shipmentMode === "SEVKIYAT" ? selectedPoNumbers[0] : null,
        po_numbers: shipmentMode === "SEVKIYAT" ? selectedPoNumbers : [],
        supplier_name: supplierName,
        warehouse_name: warehouseName,
        shipment_mode: shipmentMode,
        pallet_count: shipmentMode === "SEVKIYAT" ? Number(palletCount) : 0,
        sku_count: shipmentMode === "SEVKIYAT" ? Number(skuCount) : 0,
        slot_date: shipmentMode === "SEVKIYAT" ? selectedDate : null,
        selected_slot: shipmentMode === "SEVKIYAT" ? selectedSlot : null,
        shipment_details: shipmentMode === "SEVKIYAT" ? shipmentDetails.trim() : null,
        waybill_info: shipmentMode === "SEVKIYAT" ? waybillInfo.trim() || null : null,
        shipment_form: shipmentMode === "SEVKIYAT" ? shipmentForm || null : null,
        box_count: shipmentMode === "SEVKIYAT" && boxCount ? Number(boxCount) : null,
        vehicle_type: shipmentMode === "SEVKIYAT" ? vehicleType : null,
        vehicle_count: shipmentMode === "SEVKIYAT" && vehicleCount ? Number(vehicleCount) : null,
        vehicle_plate: shipmentMode === "SEVKIYAT" ? vehiclePlate.trim() : null,
        cargo_date: shipmentMode === "KARGO" ? cargoDate : null,
        cargo_tracking_no: shipmentMode === "KARGO" ? cargoTrackingNo.trim() : null,
        reservation_user: USER_NAME,
      });

      setMessage(`${result.message} ${t("recordNo")}: ${result.reservation_no}`);
      setSelectedPoNumbers([]);
      setPalletCount("");
      setSkuCount("");
      setSelectedDate("");
      setSelectedSlot("");
      setShipmentDetails("");
      setWaybillInfo("");
      setVehicleType("");
      setVehicleCount("");
      setVehiclePlate("");
      setShipmentForm("");
      setBoxCount("");
      setCargoDate("");
      setCargoTrackingNo("");
      await loadOperationalData(supplierName, warehouseName);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel(reservationNo) {
    try {
      const result = await cancelReservation(reservationNo, false);
      setMessage(result.message);
      await loadOperationalData(supplierName, warehouseName);
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.kicker}>{t("supplierKicker")}</p>
          <h1 style={styles.title}>{t("supplierTitle")}</h1>
          <p style={styles.subtitle}>{t("supplierSubtitle")}</p>
        </div>
        <span style={styles.badge}>{t("supplierView")}</span>
      </section>

      <form onSubmit={submit} style={styles.flow}>
        <section style={styles.card}>
          <h2 style={styles.cardTitle}>{t("shipmentMethod")}</h2>
          <div style={styles.modeGrid}>
            <ModeCard
              active={shipmentMode === "SEVKIYAT"}
              title={t("dcShipment")}
              description={t("dcShipmentDesc")}
              onClick={() => setShipmentMode("SEVKIYAT")}
            />
            <ModeCard
              active={shipmentMode === "KARGO"}
              title={t("cargoShipment")}
              description={t("cargoShipmentDesc")}
              onClick={() => setShipmentMode("KARGO")}
            />
          </div>
        </section>

        <section style={styles.card}>
          <h2 style={styles.cardTitle}>{shipmentMode === "SEVKIYAT" ? t("companyWarehousePo") : t("companyWarehouse")}</h2>
          <div style={styles.formGrid}>
            <FieldSelect label={t("supplierLabel")} value={supplierName} onChange={changeSupplier} disabled={suppliers.length <= 1}>
              {suppliers.map((row) => (
                <option key={row.supplier_name} value={row.supplier_name}>{row.supplier_name}</option>
              ))}
            </FieldSelect>

            <FieldSelect label={t("warehouseLabel")} value={warehouseName} onChange={changeWarehouse} disabled={shipmentMode === "SEVKIYAT" && selectedPoNumbers.length > 0}>
              {warehouses.map((row) => (
                <option key={row.warehouse_name} value={row.warehouse_name}>{row.warehouse_name}</option>
              ))}
            </FieldSelect>
          </div>

          {shipmentMode === "SEVKIYAT" && <div style={styles.poList}>
            {purchaseOrders.length === 0 ? (
              <div style={styles.warning}>
                {t("noOpenPo")}
              </div>
            ) : (
              purchaseOrders.map((po) => (
                <button
                  key={po.po_number}
                  type="button"
                  onClick={() => togglePo(po.po_number)}
                  style={{
                    ...styles.poButton,
                    ...(selectedPoNumbers.includes(po.po_number) ? styles.poButtonActive : {}),
                  }}
                >
                  <strong>{po.po_number}</strong>
                  <span>{po.sku_count || 0} SKU</span>
                  <span>{t("due")}: {po.delivery_date || "-"}</span>
                </button>
              ))
            )}
          </div>}
        </section>

        {shipmentMode === "SEVKIYAT" && <section style={styles.card}>
          <h2 style={styles.cardTitle}>{t("quantityInfo")}</h2>
          <div style={styles.formGrid}>
            <FieldInput label={t("palletCount")} type="number" min="1" value={palletCount} onChange={(e) => setPalletCount(e.target.value)} />
            <FieldInput label={t("skuCount")} type="number" min="1" value={skuCount} onChange={(e) => setSkuCount(e.target.value)} />
            <FieldInput label={t("boxCount")} type="number" min="0" value={boxCount} onChange={(e) => setBoxCount(e.target.value)} />
          </div>
        </section>}

        {shipmentMode === "SEVKIYAT" ? (
          <section style={styles.card}>
            <h2 style={styles.cardTitle}>{t("reservationDateTime")}</h2>
            <div style={styles.formGrid}>
              <FieldSelect label={t("suitableDate")} value={selectedDate} onChange={(e) => { setSelectedDate(e.target.value); setSelectedSlot(""); }}>
                <option value="">{t("selectDate")}</option>
                {availableDates.map((dateValue) => <option key={dateValue} value={dateValue}>{dateValue}</option>)}
              </FieldSelect>

              <FieldSelect label={t("suitableTime")} value={selectedSlot} onChange={(e) => setSelectedSlot(e.target.value)}>
                <option value="">{t("selectTime")}</option>
                {suitableSlots.map((row) => (
                  <option key={`${row.date}-${row.slot}`} value={row.slot}>
                    {row.slot} · {t("available")}
                  </option>
                ))}
              </FieldSelect>
            </div>
          </section>
        ) : (
          <section style={styles.card}>
            <h2 style={styles.cardTitle}>{t("cargoInfo")}</h2>
            <div style={styles.formGrid}>
              <FieldInput label={t("cargoDate")} type="date" value={cargoDate} onChange={(e) => setCargoDate(e.target.value)} />
              <FieldInput label={t("trackingNo")} value={cargoTrackingNo} onChange={(e) => setCargoTrackingNo(e.target.value)} />
            </div>
          </section>
        )}

        {shipmentMode === "SEVKIYAT" && <section style={styles.card}>
          <h2 style={styles.cardTitle}>{t("shipmentDetailsTitle")} <span title={t("shipmentHelp")} style={styles.infoIcon}>i</span></h2>
          <p style={styles.helpText}>
            {t("shipmentHelp")}
          </p>

          <div style={styles.formGrid}>
            <FieldInput label={t("shipmentDetails")} value={shipmentDetails} onChange={(e) => setShipmentDetails(e.target.value)} />
            <FieldInput label={t("waybill")} value={waybillInfo} onChange={(e) => setWaybillInfo(e.target.value)} />
            <FieldSelect label={t("shipmentForm")} value={shipmentForm} onChange={(e) => setShipmentForm(e.target.value)}>
              <option value="">{t("select")}</option>
              <option value="DOKME">{t("bulk")}</option>
              <option value="PALETLI">{t("palletized")}</option>
              <option value="KARMA">{t("mixed")}</option>
            </FieldSelect>

              <>
                <FieldSelect label={t("vehicleType")} value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}>
                  <option value="">{t("select")}</option>
                  <option value="KAMYON">{t("truck")}</option>
                  <option value="TIR">{t("semiTruck")}</option>
                  <option value="KAMYONET">{t("van")}</option>
                </FieldSelect>
                <FieldInput label={t("vehicleCount")} type="number" min="1" value={vehicleCount} onChange={(e) => setVehicleCount(e.target.value)} />
                <FieldInput label={t("plates")} value={vehiclePlate} onChange={(e) => setVehiclePlate(e.target.value)} placeholder="34 ABC 123, 34 XYZ 987" />
              </>
          </div>
        </section>}

        {message && <div style={styles.message}>{message}</div>}
        <button type="submit" disabled={loading} style={styles.primaryButton}>
          {loading ? t("saving") : shipmentMode === "SEVKIYAT" ? t("createReservation") : t("createCargo")}
        </button>
      </form>

      <section style={styles.card}>
        <h2 style={styles.cardTitle}>{t("upcomingRecords")}</h2>
        {reservations.length === 0 ? (
          <div style={styles.warning}>{t("noRecords")}</div>
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>{t("record")}</th>
                  <th style={styles.th}>{t("type")}</th>
                  <th style={styles.th}>{t("warehouseLabel")}</th>
                  <th style={styles.th}>{t("dateTime")}</th>
                  <th style={styles.th}>{t("plateTracking")}</th>
                  <th style={styles.th}>{t("status")}</th>
                  <th style={styles.th}>{t("action")}</th>
                </tr>
              </thead>
              <tbody>
                {reservations.map((row) => (
                  <tr key={row.reservation_no}>
                    <td style={styles.td}><strong>{row.reservation_no}</strong><br />{row.po_number}</td>
                    <td style={styles.td}>{row.shipment_mode}</td>
                    <td style={styles.td}>{row.warehouse_name}</td>
                    <td style={styles.td}>{row.slot_date}<br /><strong>{row.selected_slot}</strong></td>
                    <td style={styles.td}>{row.shipment_mode === "KARGO" ? row.cargo_tracking_no : row.vehicle_plate}</td>
                    <td style={styles.td}>{row.status}</td>
                    <td style={styles.td}>
                      {row.status !== "CANCELLED" && (
                        <button type="button" onClick={() => handleCancel(row.reservation_no)} style={styles.cancelButton}>
                          {t("cancelAction")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function ModeCard({ active, title, description, onClick }) {
  return (
    <button type="button" onClick={onClick} style={{ ...styles.modeCard, ...(active ? styles.modeCardActive : {}) }}>
      <strong>{title}</strong>
      <span>{description}</span>
    </button>
  );
}

function FieldInput({ label, ...props }) {
  return (
    <label style={styles.field}>
      <span style={styles.label}>{label}</span>
      <input {...props} style={styles.input} />
    </label>
  );
}

function FieldSelect({ label, children, ...props }) {
  return (
    <label style={styles.field}>
      <span style={styles.label}>{label}</span>
      <select {...props} style={styles.input}>{children}</select>
    </label>
  );
}

const styles = {
  page: { display: "grid", gap: 16 },
  hero: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 24, border: "1px solid #f5bfd3", borderRadius: 22, background: "#fff7fa" },
  kicker: { margin: 0, color: "#e5005a", fontWeight: 900 },
  title: { margin: "7px 0 0", fontSize: 28 },
  subtitle: { margin: "7px 0 0", color: "#667085" },
  badge: { padding: "10px 14px", borderRadius: 999, color: "#fff", background: "#e5005a", fontWeight: 900 },
  flow: { display: "grid", gap: 16 },
  card: { padding: 22, border: "1px solid var(--dockos-border)", borderRadius: 20, background: "var(--dockos-surface)" },
  cardTitle: { margin: "0 0 18px", fontSize: 18 },
  modeGrid: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 12 },
  modeCard: { display: "grid", gap: 8, padding: 18, textAlign: "left", color: "var(--dockos-text)", border: "2px solid #e5e7eb", borderRadius: 16, background: "var(--dockos-surface)", cursor: "pointer" },
  modeCardActive: { border: "2px solid #e5005a", background: "#fff1f6" },
  formGrid: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14 },
  field: { display: "grid", gap: 7 },
  label: { fontSize: 12, fontWeight: 900 },
  input: { minHeight: 42, padding: "9px 12px", border: "1px solid #d0d5dd", borderRadius: 11, background: "var(--dockos-surface)" },
  poList: { display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 10, marginTop: 16 },
  poButton: { display: "grid", gap: 4, padding: 14, color: "var(--dockos-text)", border: "1px solid #f1a8c1", borderRadius: 14, background: "#fff8fb", cursor: "pointer" },
  poButtonActive: { border: "2px solid #e5005a", background: "#ffe6ef" },
  warning: { padding: 14, borderRadius: 12, color: "#92400e", background: "#fff7ed", fontWeight: 800 },
  helpText: { margin: "-8px 0 16px", color: "#667085" },
  infoIcon: { display: "inline-grid", placeItems: "center", width: 20, height: 20, marginLeft: 6, borderRadius: "50%", color: "#fff", background: "#667085", fontSize: 12, cursor: "help" },
  message: { padding: 14, borderRadius: 12, background: "#eef2ff", fontWeight: 800 },
  primaryButton: { minHeight: 48, border: 0, borderRadius: 14, color: "#fff", background: "#e5005a", fontWeight: 900, cursor: "pointer" },
  cancelButton: { border: "1px solid #fda4af", borderRadius: 10, padding: "8px 10px", color: "#be123c", background: "#fff1f2", fontWeight: 800, cursor: "pointer" },
  tableWrap: { overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { padding: 10, textAlign: "left", borderBottom: "1px solid #e5e7eb", fontSize: 12, color: "#667085" },
  td: { padding: 10, borderBottom: "1px solid #f0f2f5", verticalAlign: "top" },
};
