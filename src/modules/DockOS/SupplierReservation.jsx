import React, { useEffect, useMemo, useState } from "react";
import { createReservation, getPurchaseOrders, getSlots } from "./dockosApi";

const RESERVATION_USER = "Erdi Aydın";

const STATIC_WAREHOUSES = [
  { warehouse_name: "Ankara DC" },
  { warehouse_name: "İstanbul Avrupa DC" },
  { warehouse_name: "İstanbul Anadolu DC" },
  { warehouse_name: "İzmir DC" },
];

export default function SupplierReservation() {
  const [supplierName, setSupplierName] = useState("Eti");
  const [selectedWarehouse, setSelectedWarehouse] = useState("Ankara DC");

  const [purchaseOrders, setPurchaseOrders] = useState([]);
  const [slots, setSlots] = useState([]);

  const [selectedPoNumbers, setSelectedPoNumbers] = useState([]);
  const [palletCount, setPalletCount] = useState("");
  const [skuCount, setSkuCount] = useState("");

  const [selectedDate, setSelectedDate] = useState("");
  const [selectedSlot, setSelectedSlot] = useState("");

  const [waybillInfo, setWaybillInfo] = useState("");
  const [vehicleType, setVehicleType] = useState("");
  const [vehicleCount, setVehicleCount] = useState("");
  const [vehiclePlates, setVehiclePlates] = useState("");
  const [shipmentForm, setShipmentForm] = useState("");
  const [boxCount, setBoxCount] = useState("");

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadData(supplier = supplierName, warehouse = selectedWarehouse) {
    try {
      const [poData, slotData] = await Promise.all([
        getPurchaseOrders(supplier, warehouse),
        getSlots(warehouse),
      ]);

      setPurchaseOrders(poData || []);
      setSlots(slotData || []);
      setSelectedPoNumbers([]);
      setSelectedDate("");
      setSelectedSlot("");
    } catch {
      setMessage("Veri alınamadı.");
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const selectedPos = useMemo(() => {
    return purchaseOrders.filter((po) =>
      selectedPoNumbers.includes(po.po_number)
    );
  }, [purchaseOrders, selectedPoNumbers]);

  const availableDates = useMemo(() => {
    return [...new Set(slots.map((slot) => slot.date))].sort();
  }, [slots]);

  const suitableSlots = useMemo(() => {
    const pallet = Number(palletCount);
    const sku = Number(skuCount);

    if (!selectedDate || !pallet || !sku) return [];

    return slots.filter(
      (slot) =>
        slot.date === selectedDate &&
        slot.remaining_pallet >= pallet &&
        slot.remaining_sku >= sku
    );
  }, [slots, selectedDate, palletCount, skuCount]);

  const reservationNo = useMemo(() => {
    return `RN_${Date.now().toString().slice(-10)}`;
  }, []);

  const reservationDate = new Date().toLocaleDateString("tr-TR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const canShowDates =
    selectedPoNumbers.length > 0 &&
    Number(palletCount) > 0 &&
    Number(skuCount) > 0;

async function addManualPO() {
  const slotData = await getSlots(selectedWarehouse);
  setSlots(slotData || []);

  const manualPo = {
    po_number: `MANUAL-${Date.now().toString().slice(-6)}`,
    supplier_name: supplierName,
    warehouse_name: selectedWarehouse,
    delivery_date: new Date().toISOString().slice(0, 10),
    status: "OPEN",
  };

  setPurchaseOrders((prev) => [manualPo, ...prev]);
  setMessage("Test manuel PO eklendi.");
}

  function togglePo(poNumber) {
    setSelectedPoNumbers((prev) =>
      prev.includes(poNumber)
        ? prev.filter((x) => x !== poNumber)
        : [...prev, poNumber]
    );

    setSelectedDate("");
    setSelectedSlot("");
  }

  async function handleSupplierChange(e) {
    const supplier = e.target.value;
    setSupplierName(supplier);
    setMessage("");
    await loadData(supplier, selectedWarehouse);
  }

async function handleWarehouseChange(e) {
  const warehouse = e.target.value;
  setSelectedWarehouse(warehouse);
  setMessage("");
  setSelectedDate("");
  setSelectedSlot("");
  await loadData(supplierName, warehouse);
}
  async function handleSubmit(e) {
    e.preventDefault();
    setMessage("");

    if (!selectedPoNumbers.length) {
      setMessage("En az bir PO seçmelisin.");
      return;
    }

    if (!palletCount || !skuCount) {
      setMessage("Palet ve SKU sayısı girmelisin.");
      return;
    }

    if (!selectedDate) {
      setMessage("Rezervasyon tarihi seçmelisin.");
      return;
    }

    if (!selectedSlot) {
      setMessage("Uygun bir saat seçmelisin.");
      return;
    }

    setLoading(true);

    try {
      const result = await createReservation({
        po_number: selectedPoNumbers[0],
        po_numbers: selectedPoNumbers,
        supplier_name: supplierName,
        warehouse_name: selectedWarehouse,
        pallet_count: Number(palletCount),
        sku_count: Number(skuCount),
        slot_date: selectedDate,
        selected_slot: selectedSlot,
        waybill_info: waybillInfo,
        vehicle_type: vehicleType,
        vehicle_count: vehicleCount ? Number(vehicleCount) : null,
        vehicle_plate: vehiclePlates,
        shipment_form: shipmentForm,
        box_count: boxCount ? Number(boxCount) : null,
        reservation_user: RESERVATION_USER,
      });

      setMessage(`${result.message} Rezervasyon No: ${result.reservation_no}`);

      setPalletCount("");
      setSkuCount("");
      setSelectedPoNumbers([]);
      setSelectedDate("");
      setSelectedSlot("");
      setWaybillInfo("");
      setVehicleType("");
      setVehicleCount("");
      setVehiclePlates("");
      setShipmentForm("");
      setBoxCount("");

      await loadData(supplierName, selectedWarehouse);
    } catch {
      setMessage("Rezervasyon oluşturulamadı.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.hero}>
        <div>
          <p style={styles.kicker}>DockOS · Merkez Depo</p>
          <h1 style={styles.title}>Tedarikçi Rezervasyon Portalı</h1>
          <p style={styles.subtitle}>
            PO seç, palet/SKU gir, uygun tarih ve saatle merkez depo randevusu oluştur.
          </p>
        </div>
        <div style={styles.badge}>Supplier View</div>
      </div>

      <form onSubmit={handleSubmit} style={styles.flow}>
        <section style={styles.card}>
          <h2 style={styles.cardTitle}>1. Firma, Merkez Depo & PO Seçimi</h2>

          <div style={styles.formGrid}>
            <InputSelect label="Tedarikçi Ünvanı" value={supplierName} onChange={handleSupplierChange}>
              <option value="Eti">Eti</option>
              <option value="Ülker">Ülker</option>
              <option value="Coca Cola">Coca Cola</option>
              <option value="Pınar">Pınar</option>
            </InputSelect>

            <InputSelect label="Rezervasyon Yapılacak Merkez Depo" value={selectedWarehouse} onChange={handleWarehouseChange}>
              {STATIC_WAREHOUSES.map((warehouse) => (
                <option key={warehouse.warehouse_name} value={warehouse.warehouse_name}>
                  {warehouse.warehouse_name}
                </option>
              ))}
            </InputSelect>
          </div>

          <button type="button" onClick={addManualPO} style={styles.secondaryButton}>
            Test Manuel PO Ekle
          </button>

          <div style={styles.poList}>
            {purchaseOrders.length === 0 ? (
              <div style={styles.warning}>Açık PO bulunamadı.</div>
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
                  <span>{po.warehouse_name}</span>
                  <span>Termin: {po.delivery_date}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <section style={styles.card}>
          <h2 style={styles.cardTitle}>2. Rezervasyon Kimliği</h2>

          <div style={styles.readonlyGrid}>
            <Info label="Rezervasyon No" value={reservationNo} />
            <Info label="Kayıt Tarihi" value={reservationDate} />
            <Info label="Rezervasyonu Yapan" value={RESERVATION_USER} />
            <Info label="Merkez Depo" value={selectedWarehouse} />
          </div>
        </section>

        <section style={styles.card}>
          <h2 style={styles.cardTitle}>3. Palet & SKU Bilgisi</h2>

          <div style={styles.formGrid}>
            <Input label="Palet Sayısı" value={palletCount} setValue={setPalletCount} type="number" />
            <Input label="SKU Sayısı" value={skuCount} setValue={setSkuCount} type="number" />
          </div>
        </section>

        {canShowDates && (
          <section style={styles.card}>
            <h2 style={styles.cardTitle}>4. Rezervasyon Tarihi & Saat Seçimi</h2>

            <label style={styles.label}>Uygun Tarihler</label>
            <div style={styles.hourGrid}>
              {availableDates.length === 0 ? (
                <div style={styles.warning}>
                  Bu merkez depo için kapasite tanımı yok. Önce Kapasite Yönetimi ekranından limit gir.
                </div>
              ) : (
                availableDates.map((date) => (
                  <button
                    key={date}
                    type="button"
                    onClick={() => {
                      setSelectedDate(date);
                      setSelectedSlot("");
                    }}
                    style={{
                      ...styles.hourButton,
                      ...(selectedDate === date ? styles.hourButtonActive : {}),
                    }}
                  >
                    {date}
                  </button>
                ))
              )}
            </div>

            {selectedDate && (
              <>
                <label style={styles.label}>Uygun Saatler</label>
                <div style={styles.hourGrid}>
                  {suitableSlots.length === 0 ? (
                    <div style={styles.warning}>
                      Girilen palet/SKU için uygun saat bulunamadı.
                    </div>
                  ) : (
                    suitableSlots.map((slot) => (
                      <button
                        key={slot.slot}
                        type="button"
                        onClick={() => setSelectedSlot(slot.slot)}
                        style={{
                          ...styles.hourButton,
                          ...(selectedSlot === slot.slot ? styles.hourButtonActive : {}),
                        }}
                      >
                        {slot.slot}
                      </button>
                    ))
                  )}
                </div>
              </>
            )}
          </section>
        )}

        <section style={styles.card}>
          <h2 style={styles.cardTitle}>5. Sevkiyat Detayları</h2>

          <div style={styles.formGrid}>
            <Input label="İrsaliye Bilgisi" value={waybillInfo} setValue={setWaybillInfo} />
            <Input label="Araç Tipi" value={vehicleType} setValue={setVehicleType} />
            <Input label="Araç Sayısı" value={vehicleCount} setValue={setVehicleCount} type="number" />
            <Input label="Araç Plakası / Plakaları" value={vehiclePlates} setValue={setVehiclePlates} />
            <Input label="Sevk Şekli" value={shipmentForm} setValue={setShipmentForm} />
            <Input label="Koli Sayısı" value={boxCount} setValue={setBoxCount} type="number" />
          </div>
        </section>

        <button disabled={loading} style={styles.button}>
          {loading ? "Oluşturuluyor..." : "Rezervasyon Oluştur"}
        </button>

        {message && <div style={styles.message}>{message}</div>}
      </form>
    </div>
  );
}

function InputSelect({ label, value, onChange, children }) {
  return (
    <div>
      <label style={styles.label}>{label}</label>
      <select value={value} onChange={onChange} style={styles.input}>
        {children}
      </select>
    </div>
  );
}

function Input({ label, value, setValue, type = "text" }) {
  return (
    <div>
      <label style={styles.label}>{label}</label>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={styles.input}
        type={type}
      />
    </div>
  );
}

function Info({ label, value }) {
  return (
    <div style={styles.infoItem}>
      <span>{label}</span>
      <strong>{value || "-"}</strong>
    </div>
  );
}

const styles = {
  page: { padding: 24, background: "#f7f8fb", minHeight: "100vh", color: "#111827", fontFamily: "Inter, Arial, sans-serif" },
  hero: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, background: "linear-gradient(135deg, #ffffff 0%, #fff0f6 100%)", border: "1px solid #f3d1df", padding: 24, borderRadius: 24, marginBottom: 24 },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "8px 0", fontSize: 30, lineHeight: 1.1 },
  subtitle: { margin: 0, color: "#6b7280" },
  badge: { background: "#DF1067", color: "#fff", padding: "10px 14px", borderRadius: 999, fontWeight: 900 },
  flow: { display: "grid", gap: 18 },
  card: { background: "#fff", borderRadius: 24, padding: 22, border: "1px solid #e5e7eb", boxShadow: "0 12px 30px rgba(15, 23, 42, 0.04)" },
  cardTitle: { marginTop: 0, fontSize: 20 },
  label: { display: "block", marginTop: 14, marginBottom: 8, fontWeight: 800, fontSize: 13, color: "#374151" },
  input: { width: "100%", boxSizing: "border-box", padding: "12px 14px", borderRadius: 14, border: "1px solid #d1d5db", outline: "none", background: "#fff", color: "#111827" },
  formGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 },
  poList: { marginTop: 18, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 },
  poButton: { border: "2px solid #e5e7eb", borderRadius: 16, padding: 14, background: "#fff", display: "grid", gap: 6, textAlign: "left", cursor: "pointer", color: "#111827" },
  poButtonActive: { borderColor: "#DF1067", background: "#fff0f6" },
  readonlyGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 },
  infoItem: { background: "#f9fafb", padding: 14, borderRadius: 16, display: "grid", gap: 6 },
  warning: { marginTop: 16, background: "#fff7ed", padding: 14, borderRadius: 16, color: "#9a3412", fontWeight: 800 },
  hourGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginTop: 10 },
  hourButton: { border: "1px solid #d1d5db", background: "#fff", color: "#111827", borderRadius: 14, padding: "12px 10px", cursor: "pointer", fontWeight: 900 },
  hourButtonActive: { borderColor: "#DF1067", background: "#fff0f6", color: "#DF1067" },
  button: { border: "none", background: "#DF1067", color: "#fff", padding: "16px 18px", borderRadius: 16, fontWeight: 900, cursor: "pointer" },
  secondaryButton: { marginTop: 16, border: "1px solid #DF1067", borderRadius: 14, padding: "12px 14px", background: "#fff0f6", color: "#DF1067", fontWeight: 900, cursor: "pointer" },
  message: { background: "#ecfdf5", padding: 14, borderRadius: 16, color: "#065f46", fontWeight: 900 },
};