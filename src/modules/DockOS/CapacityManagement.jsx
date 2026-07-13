import React, { useEffect, useMemo, useState } from "react";
import {
  blockSlotDates,
  bulkUpdateCapacity,
  bulkUpdateSupplierCapacityMatrix,
  deleteSlotCapacity,
  editSlotCapacity,
  getSlots,
  getSupplierCapacity,
  getSupplierDailyLimits,
  getSuppliers,
  getWarehouses,
} from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const today = () => new Date().toISOString().slice(0, 10);

function timeToMinutes(value) {
  const [hour, minute] = String(value || "").split(":").map(Number);
  return Number.isInteger(hour) && Number.isInteger(minute) ? hour * 60 + minute : null;
}

function minutesToTime(value) {
  const normalized = ((value % 1440) + 1440) % 1440;
  return `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${String(normalized % 60).padStart(2, "0")}`;
}

function slotStartMinutes(slot) {
  return timeToMinutes(String(slot).split("-")[0].trim()) ?? 1440;
}

function sortSlots(values) {
  return [...new Set(values)].sort((a, b) => slotStartMinutes(a) - slotStartMinutes(b) || a.localeCompare(b));
}

function datesBetween(start, end) {
  if (!start || !end || start > end) return [];
  const result = [];
  const cursor = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  while (cursor <= last) {
    result.push(cursor.toISOString().slice(0, 10));
    cursor.setDate(cursor.getDate() + 1);
  }
  return result;
}

function displayDate(value, localeCode) {
  return new Date(`${value}T12:00:00`).toLocaleDateString(localeCode, { day: "2-digit", month: "short", weekday: "short" });
}

export default function CapacityManagement() {
  const { t, localeCode } = useDockOSUi();
  const [warehouses, setWarehouses] = useState([]);
  const [warehouse, setWarehouse] = useState("Ankara DC");
  const [rangeStart, setRangeStart] = useState(today());
  const [rangeEnd, setRangeEnd] = useState(today());
  const [singleDate, setSingleDate] = useState(today());
  const [selectedDates, setSelectedDates] = useState([today()]);
  const [selectedHours, setSelectedHours] = useState([]);
  const [capacityMode, setCapacityMode] = useState("");
  const [newSlotStart, setNewSlotStart] = useState("18:00");
  const [newSlotDuration, setNewSlotDuration] = useState(60);
  const [newSlotCount, setNewSlotCount] = useState(1);
  const [palletLimit, setPalletLimit] = useState(40);
  const [skuLimit, setSkuLimit] = useState(500);
  const [rows, setRows] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [allocationRows, setAllocationRows] = useState([]);
  const [allocations, setAllocations] = useState([]);
  const [dailyLimits, setDailyLimits] = useState([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [showClosedSlots, setShowClosedSlots] = useState(false);
  const [editingSlot, setEditingSlot] = useState(null);

  const sortedDates = useMemo(() => [...new Set(selectedDates)].sort(), [selectedDates]);
  const dateSet = useMemo(() => new Set(sortedDates), [sortedDates]);

  async function loadRows(currentWarehouse = warehouse) {
    const [slotRows, allocationData, dailyLimitRows] = await Promise.all([
      getSlots({ warehouse_name: currentWarehouse }),
      getSupplierCapacity({ warehouse_name: currentWarehouse }),
      getSupplierDailyLimits({ warehouse_name: currentWarehouse }),
    ]);
    setRows(slotRows);
    setAllocations(allocationData);
    setDailyLimits(dailyLimitRows);
  }

  useEffect(() => {
    (async () => {
      try {
        const [warehouseRows, supplierRows] = await Promise.all([getWarehouses(), getSuppliers()]);
        const firstWarehouse = warehouseRows[0]?.warehouse_name || "";
        setWarehouses(warehouseRows);
        setWarehouse(firstWarehouse);
        setSuppliers(supplierRows);
        if (supplierRows.length) {
          setAllocationRows([{ id: "allocation-1", supplier_name: supplierRows[0].supplier_name, reserved_pallet: 0, reserved_sku: 0, max_daily_pallet: "" }]);
        }
        await loadRows(firstWarehouse);
      } catch (error) {
        setMessage(error.message);
      }
    })();
  }, []);

  function addDates(values) {
    setSelectedDates((current) => [...new Set([...current, ...values])].sort());
  }

  function addNextSevenDays() {
    const values = Array.from({ length: 7 }, (_, index) => new Date(Date.now() + index * 86400000).toISOString().slice(0, 10));
    addDates(values);
  }

  function addGeneratedSlots() {
    const start = timeToMinutes(newSlotStart);
    const duration = Number(newSlotDuration);
    const count = Number(newSlotCount);
    if (start === null || duration < 15 || duration > 240 || count < 1 || count > 24 || duration * count > 1440) {
      return setMessage(t("customSlotInvalid"));
    }
    const generated = Array.from({ length: count }, (_, index) => {
      const blockStart = start + index * duration;
      return `${minutesToTime(blockStart)} - ${minutesToTime(blockStart + duration)}`;
    });
    setSelectedHours((current) => sortSlots([...current, ...generated]));
    setMessage(`${generated.length} ${t("customSlotsAdded")}`);
  }

  async function applyLimits() {
    if (!sortedDates.length || !selectedHours.length) return setMessage(t("selectDateHour"));
    setSaving(true);
    setMessage("");
    try {
      const result = await bulkUpdateCapacity({ warehouse_name: warehouse, dates: sortedDates, slots: selectedHours, max_pallet: Number(palletLimit), max_sku: Number(skuLimit) });
      setMessage(result.message);
      await loadRows(warehouse);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  async function blockDates() {
    if (!sortedDates.length) return setMessage(t("selectDateFirst"));
    if (!window.confirm(t("blockDatesConfirm"))) return;
    setSaving(true);
    setMessage("");
    try {
      const result = await blockSlotDates({ warehouse_name: warehouse, dates: sortedDates });
      setMessage(result.message);
      setSelectedHours([]);
      await loadRows(warehouse);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  function beginSlotEdit(row) {
    const [start, end] = row.slot.split("-").map((value) => value.trim());
    setEditingSlot({ key: `${row.warehouse_name}|${row.date}|${row.slot}`, warehouse_name: row.warehouse_name, date: row.date, current_slot: row.slot, start, end, max_pallet: row.max_pallet, max_sku: row.max_sku });
  }

  async function saveSlotEdit() {
    if (!editingSlot) return;
    setSaving(true);
    setMessage("");
    try {
      const result = await editSlotCapacity({
        warehouse_name: editingSlot.warehouse_name,
        date: editingSlot.date,
        current_slot: editingSlot.current_slot,
        new_slot: `${editingSlot.start} - ${editingSlot.end}`,
        max_pallet: Number(editingSlot.max_pallet),
        max_sku: Number(editingSlot.max_sku),
      });
      setMessage(result.message);
      setEditingSlot(null);
      await loadRows(warehouse);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeSlot(row) {
    if (!window.confirm(t("deleteSlotConfirm"))) return;
    setSaving(true);
    setMessage("");
    try {
      const result = await deleteSlotCapacity({ warehouse_name: row.warehouse_name, date: row.date, slot: row.slot });
      setMessage(result.message);
      await loadRows(warehouse);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  function updateAllocation(id, key, value) {
    setAllocationRows((current) => current.map((row) => row.id === id ? { ...row, [key]: value } : row));
  }

  function addSupplierRow() {
    const used = new Set(allocationRows.map((row) => row.supplier_name));
    const next = suppliers.find((row) => !used.has(row.supplier_name));
    if (!next) return setMessage(t("noMoreSupplier"));
    setAllocationRows((current) => [...current, { id: `allocation-${Date.now()}`, supplier_name: next.supplier_name, reserved_pallet: 0, reserved_sku: 0, max_daily_pallet: "" }]);
  }

  async function applySupplierMatrix() {
    if (!sortedDates.length || !selectedHours.length) return setMessage(t("selectDateHour"));
    if (!allocationRows.length) return setMessage(t("addOneSupplier"));
    setSaving(true);
    setMessage("");
    try {
      const result = await bulkUpdateSupplierCapacityMatrix({
        warehouse_name: warehouse,
        dates: sortedDates,
        slots: selectedHours,
        allocations: allocationRows.map((row) => ({ supplier_name: row.supplier_name, reserved_pallet: Number(row.reserved_pallet), reserved_sku: Number(row.reserved_sku), max_daily_pallet: row.max_daily_pallet === "" ? null : Number(row.max_daily_pallet) })),
      });
      setMessage(result.message);
      await loadRows(warehouse);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }

  const filteredRows = useMemo(() => rows.filter((row) => dateSet.has(row.date)).sort((a, b) => `${a.date}-${a.slot}`.localeCompare(`${b.date}-${b.slot}`)), [rows, dateSet]);
  const managedRows = useMemo(() => showClosedSlots ? filteredRows : filteredRows.filter((row) => Number(row.max_pallet) > 0 || Number(row.max_sku) > 0), [filteredRows, showClosedSlots]);
  const visibleAllocations = useMemo(() => allocations.filter((row) => dateSet.has(row.date)).sort((a, b) => `${a.date}-${a.slot}-${a.supplier_name}`.localeCompare(`${b.date}-${b.slot}-${b.supplier_name}`)), [allocations, dateSet]);
  const visibleDailyLimits = useMemo(() => dailyLimits.filter((row) => dateSet.has(row.date)).sort((a, b) => `${a.date}-${a.supplier_name}`.localeCompare(`${b.date}-${b.supplier_name}`)), [dailyLimits, dateSet]);
  const totals = useMemo(() => filteredRows.reduce((acc, row) => ({
    totalPallet: acc.totalPallet + Number(row.max_pallet || 0),
    remainingPallet: acc.remainingPallet + Number(row.remaining_pallet || 0),
    totalSku: acc.totalSku + Number(row.max_sku || 0),
    remainingSku: acc.remainingSku + Number(row.remaining_sku || 0),
  }), { totalPallet: 0, remainingPallet: 0, totalSku: 0, remainingSku: 0 }), [filteredRows]);

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div><p style={styles.kicker}>{t("capacityKicker")}</p><h1 style={styles.title}>{t("capacityTitle")}</h1><p style={styles.subtitle}>{t("capacitySubtitle")}</p></div>
        <div style={styles.scopeBadge}>{sortedDates.length} {t("scopeDate")} · {selectedHours.length} {t("scopeHour")} · {allocationRows.length} {t("scopeSupplier")}</div>
      </section>

      <section style={styles.panel}>
        <h2 style={styles.sectionTitle}>{t("dateBasket")}</h2>
        <div style={styles.dateControls}>
          <FieldSelect label={t("warehouseLabel")} value={warehouse} onChange={async (event) => { setWarehouse(event.target.value); await loadRows(event.target.value); }}>
            {warehouses.map((row) => <option key={row.warehouse_name} value={row.warehouse_name}>{row.warehouse_name}</option>)}
          </FieldSelect>
          <FieldInput label={t("singleDate")} type="date" value={singleDate} onChange={(event) => setSingleDate(event.target.value)} />
          <button type="button" style={styles.outlineButton} onClick={() => addDates([singleDate])}>{t("addDate")}</button>
          <FieldInput label={t("rangeStart")} type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} />
          <FieldInput label={t("rangeEnd")} type="date" value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} />
          <button type="button" style={styles.outlineButton} onClick={() => addDates(datesBetween(rangeStart, rangeEnd))}>{t("addRange")}</button>
        </div>
        <div style={styles.quickWrap}>
          <button type="button" style={styles.quickButton} onClick={addNextSevenDays}>{t("next7")}</button>
          <button type="button" style={styles.quickButton} onClick={() => setSelectedDates([today()])}>{t("onlyToday")}</button>
          <button type="button" style={styles.quickDanger} onClick={() => setSelectedDates([])}>{t("clearDates")}</button>
        </div>
        <div style={styles.chipWrap}>{sortedDates.map((value) => <button type="button" key={value} style={styles.dateChip} onClick={() => setSelectedDates((current) => current.filter((dateValue) => dateValue !== value))}>{displayDate(value, localeCode)} ×</button>)}</div>
      </section>

      <section style={styles.panel}>
        <h2 style={styles.sectionTitle}>{t("managementChoiceTitle")}</h2>
        <p style={styles.subtitle}>{t("managementChoiceHelp")}</p>
        <div style={styles.modeGrid}>
          <button type="button" onClick={() => setCapacityMode("BLOCK")} style={capacityMode === "BLOCK" ? styles.modeCardActive : styles.modeCard}>
            <span style={styles.modeIcon}>⊘</span><strong>{t("blockWholeDay")}</strong><small>{t("blockWholeDayHelp")}</small>
          </button>
          <button type="button" onClick={() => setCapacityMode("PARTIAL")} style={capacityMode === "PARTIAL" ? styles.modeCardActive : styles.modeCard}>
            <span style={styles.modeIcon}>＋</span><strong>{t("managePartial")}</strong><small>{t("managePartialHelp")}</small>
          </button>
        </div>

        {capacityMode === "BLOCK" && <div style={styles.blockAction}>
          <div><strong>{sortedDates.length} {t("scopeDate")}</strong><span>{t("blockActionHelp")}</span></div>
          <button type="button" disabled={saving || !sortedDates.length} onClick={blockDates} style={styles.dangerButton}>{saving ? t("saving") : t("blockSelectedDates")}</button>
        </div>}

        {capacityMode && <div style={styles.slotBuilder}>
          <div style={styles.slotBuilderHead}><strong>{capacityMode === "BLOCK" ? t("reopenHoursTitle") : t("customSlotTitle")}</strong><span>{capacityMode === "BLOCK" ? t("reopenHoursHelp") : t("customSlotHelp")}</span></div>
          <div style={styles.ruleNote}>{t("singleAppointmentRule")}</div>
          <div style={styles.customSlotGrid}>
            <FieldInput label={t("slotStart")} type="time" step="900" value={newSlotStart} onChange={(event) => setNewSlotStart(event.target.value)} />
            <FieldInput label={t("slotDuration")} type="number" min="15" max="240" step="15" value={newSlotDuration} onChange={(event) => setNewSlotDuration(event.target.value)} />
            <FieldInput label={t("slotCount")} type="number" min="1" max="24" value={newSlotCount} onChange={(event) => setNewSlotCount(event.target.value)} />
            <button type="button" style={styles.outlineButton} onClick={addGeneratedSlots}>+ {t("addSlotBlocks")}</button>
          </div>
          {selectedHours.length > 0 && <div style={styles.selectedSlotWrap}>{selectedHours.map((hour) => <button key={hour} type="button" style={styles.selectedSlotChip} onClick={() => setSelectedHours((current) => current.filter((item) => item !== hour))}>{hour} ×</button>)}</div>}
          <div style={styles.limitGrid}>
            <FieldInput label={t("palletLimit")} type="number" min="0" value={palletLimit} onChange={(event) => setPalletLimit(event.target.value)} />
            <FieldInput label={t("skuLimit")} type="number" min="0" value={skuLimit} onChange={(event) => setSkuLimit(event.target.value)} />
            <button type="button" disabled={saving || !selectedHours.length} onClick={applyLimits} style={styles.primaryButton}>{saving ? t("saving") : t("openSelectedSlots")}</button>
          </div>
        </div>}
        {!capacityMode && <div style={styles.choiceEmpty}>{t("chooseManagementMode")}</div>}
      </section>

      <section style={styles.panel}>
        <div style={styles.sectionHead}>
          <div><h2 style={styles.sectionTitle}>{t("slotManagerTitle")}</h2><p style={styles.subtitle}>{t("slotManagerHelp")}</p></div>
          <label style={styles.switchLabel}><input type="checkbox" checked={showClosedSlots} onChange={(event) => setShowClosedSlots(event.target.checked)} /> {t("showClosedSlots")}</label>
        </div>
        {!managedRows.length ? <Empty text={t("noManagedSlots")} /> : <div style={styles.tableWrap}><table style={styles.table}><thead><tr><th>{t("date")}</th><th>{t("time")}</th><th>{t("palletLimit")}</th><th>{t("skuLimit")}</th><th>{t("used")}</th><th>{t("status")}</th><th>{t("action")}</th></tr></thead><tbody>{managedRows.map((row) => {
          const key = `${row.warehouse_name}|${row.date}|${row.slot}`;
          const editing = editingSlot?.key === key;
          return <tr key={key}>
            <td>{displayDate(row.date, localeCode)}</td>
            <td>{editing ? <div style={styles.timeEdit}><input type="time" value={editingSlot.start} onChange={(event) => setEditingSlot({...editingSlot,start:event.target.value})} style={styles.compactInput} /><span>–</span><input type="time" value={editingSlot.end} onChange={(event) => setEditingSlot({...editingSlot,end:event.target.value})} style={styles.compactInput} /></div> : <strong>{row.slot}</strong>}</td>
            <td>{editing ? <input type="number" min="0" value={editingSlot.max_pallet} onChange={(event) => setEditingSlot({...editingSlot,max_pallet:event.target.value})} style={styles.compactInput} /> : row.max_pallet}</td>
            <td>{editing ? <input type="number" min="0" value={editingSlot.max_sku} onChange={(event) => setEditingSlot({...editingSlot,max_sku:event.target.value})} style={styles.compactInput} /> : row.max_sku}</td>
            <td>{row.max_pallet - row.remaining_pallet} {t("palletUnit")} · {row.max_sku - row.remaining_sku} SKU</td>
            <td><span style={Number(row.max_pallet) > 0 || Number(row.max_sku) > 0 ? styles.openBadge : styles.fullBadge}>{Number(row.max_pallet) > 0 || Number(row.max_sku) > 0 ? t("open") : t("blocked")}</span></td>
            <td><div style={styles.rowActions}>{editing ? <><button type="button" disabled={saving} onClick={saveSlotEdit} style={styles.saveSmall}>{t("save")}</button><button type="button" onClick={() => setEditingSlot(null)} style={styles.cancelSmall}>{t("cancel")}</button></> : <><button type="button" onClick={() => beginSlotEdit(row)} style={styles.editSmall}>{t("edit")}</button><button type="button" disabled={saving} onClick={() => removeSlot(row)} style={styles.deleteSmall}>{t("deleteSlot")}</button></>}</div></td>
          </tr>;
        })}</tbody></table></div>}
      </section>

      <section style={styles.panel}>
        <div style={styles.sectionHead}><div><h2 style={styles.sectionTitle}>{t("multiSupplierCapacity")}</h2><p style={styles.subtitle}>{t("multiSupplierDesc")}</p></div><button type="button" onClick={addSupplierRow} style={styles.addButton}>+ {t("addSupplier")}</button></div>
        <div style={styles.matrixHeader}><span>{t("supplierLabel")}</span><span>{t("reservedPallet")}</span><span>{t("reservedSku")}</span><span>{t("dailyMax")}</span><span /></div>
        <div style={styles.matrixRows}>{allocationRows.map((row) => {
          const otherSelected = new Set(allocationRows.filter((item) => item.id !== row.id).map((item) => item.supplier_name));
          return <div key={row.id} style={styles.matrixRow}>
            <select value={row.supplier_name} onChange={(event) => updateAllocation(row.id, "supplier_name", event.target.value)} style={styles.input}>{suppliers.map((supplier) => <option key={supplier.supplier_name} value={supplier.supplier_name} disabled={otherSelected.has(supplier.supplier_name)}>{supplier.supplier_name}</option>)}</select>
            <input type="number" min="0" value={row.reserved_pallet} onChange={(event) => updateAllocation(row.id, "reserved_pallet", event.target.value)} style={styles.input} />
            <input type="number" min="0" value={row.reserved_sku} onChange={(event) => updateAllocation(row.id, "reserved_sku", event.target.value)} style={styles.input} />
            <input type="number" min="0" value={row.max_daily_pallet} placeholder={t("noLimit")} onChange={(event) => updateAllocation(row.id, "max_daily_pallet", event.target.value)} style={styles.input} />
            <button type="button" style={styles.removeButton} onClick={() => setAllocationRows((current) => current.filter((item) => item.id !== row.id))}>{t("remove")}</button>
          </div>;
        })}</div>
        <button type="button" disabled={saving} onClick={applySupplierMatrix} style={styles.secondaryButton}>{saving ? t("applying") : `${allocationRows.length} ${t("applyCapacity")}`}</button>
        {message && <div style={styles.message}>{message}</div>}
      </section>

      <section style={styles.statsGrid}>
        <Stat label={t("totalPallet")} value={totals.totalPallet} tone="#7c3aed" />
        <Stat label={t("usedPallet")} value={totals.totalPallet - totals.remainingPallet} tone="#e5005a" />
        <Stat label={t("remainingPallet")} value={totals.remainingPallet} tone="#12b76a" />
        <Stat label={t("totalSku")} value={totals.totalSku} tone="#7c3aed" />
        <Stat label={t("usedSku")} value={totals.totalSku - totals.remainingSku} tone="#e5005a" />
        <Stat label={t("remainingSku")} value={totals.remainingSku} tone="#12b76a" />
      </section>

      <section style={styles.panel}>
        <h2 style={styles.sectionTitle}>{t("activeAllocations")}</h2>
        {visibleDailyLimits.length > 0 && <div style={styles.dailyLimitGrid}>{visibleDailyLimits.map((row) => <div key={`${row.supplier_name}-${row.date}`} style={styles.dailyLimitCard}><span>{t("dailyUpperLimit")}</span><strong>{row.supplier_name}</strong><b>{displayDate(row.date, localeCode)} · {t("maxAbbr")} {row.max_pallet} {t("palletUnit")}</b></div>)}</div>}
        {!visibleAllocations.length ? <Empty text={t("noFixedCapacity")} /> : <div style={styles.allocationGrid}>{visibleAllocations.map((row) => <div key={`${row.supplier_name}-${row.date}-${row.slot}`} style={styles.allocationCard}><strong>{row.supplier_name}</strong><span>{displayDate(row.date, localeCode)} · {row.slot}</span><b>{row.reserved_pallet} {t("palletUnit")} · {row.reserved_sku} SKU</b></div>)}</div>}
      </section>

    </div>
  );
}

function FieldInput({ label, ...props }) { return <label style={styles.field}><span style={styles.label}>{label}</span><input {...props} style={styles.input} /></label>; }
function FieldSelect({ label, children, ...props }) { return <label style={styles.field}><span style={styles.label}>{label}</span><select {...props} style={styles.input}>{children}</select></label>; }
function Stat({ label, value, tone }) { return <div style={{ ...styles.statCard, border: `1px solid ${tone}30` }}><span style={styles.statLabel}>{label}</span><strong style={{ ...styles.statValue, color: tone }}>{value}</strong></div>; }
function Empty({ text }) { return <div style={styles.empty}>{text}</div>; }

const styles = {
  page: { display: "grid", gap: 16, color: "var(--dockos-text)" }, hero: { display: "flex", alignItems: "center", justifyContent: "space-between", padding: 24, border: "1px solid var(--dockos-border)", borderRadius: 22, background: "var(--dockos-surface)" }, kicker: { margin: 0, color: "#e5005a", fontWeight: 900 }, title: { margin: "6px 0 0", fontSize: 28 }, subtitle: { margin: "6px 0 0", color: "var(--dockos-muted)" }, scopeBadge: { padding: "11px 15px", borderRadius: 999, color: "#fff", background: "#101828", fontWeight: 900 },
  panel: { padding: 20, border: "1px solid var(--dockos-border)", borderRadius: 20, background: "var(--dockos-surface)" }, sectionTitle: { margin: "0 0 8px", fontSize: 19 }, sectionHead: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }, dateControls: { display: "grid", gridTemplateColumns: "1.2fr 1fr auto 1fr 1fr auto", gap: 10, alignItems: "end" }, field: { display: "grid", gap: 7 }, label: { fontSize: 12, fontWeight: 900 }, input: { boxSizing: "border-box", width: "100%", minHeight: 42, padding: "9px 12px", border: "1px solid #d0d5dd", borderRadius: 11, color: "var(--dockos-text)", background: "var(--dockos-surface)" },
  outlineButton: { minHeight: 42, padding: "9px 14px", border: "1px solid var(--dockos-border)", borderRadius: 11, color: "var(--dockos-text)", background: "var(--dockos-surface)", fontWeight: 900, cursor: "pointer" }, quickWrap: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }, quickButton: { padding: "8px 12px", border: "1px solid var(--dockos-border)", borderRadius: 999, color: "var(--dockos-text)", background: "var(--dockos-surface)", fontWeight: 800, cursor: "pointer" }, quickDanger: { padding: "8px 12px", border: "1px solid #fda29b", borderRadius: 999, color: "var(--dockos-danger-text)", background: "var(--dockos-danger-bg)", fontWeight: 800, cursor: "pointer" }, chipWrap: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }, dateChip: { padding: "9px 12px", border: "1px solid #84adff", borderRadius: 10, color: "var(--dockos-info-text)", background: "var(--dockos-info-bg)", fontWeight: 900, cursor: "pointer" },
  modeGrid: { display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 12, marginTop: 16 }, modeCard: { display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", alignItems: "center", padding: 18, textAlign: "left", border: "1px solid var(--dockos-border)", borderRadius: 16, color: "var(--dockos-text)", background: "var(--dockos-surface-alt)", cursor: "pointer" }, modeCardActive: { display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", alignItems: "center", padding: 18, textAlign: "left", border: "2px solid #e5005a", borderRadius: 16, color: "var(--dockos-text)", background: "var(--dockos-accent-soft-bg)", cursor: "pointer" }, modeIcon: { gridRow: "1 / span 2", display: "grid", placeItems: "center", width: 42, height: 42, borderRadius: 12, color: "#fff", background: "#e5005a", fontSize: 24, fontWeight: 900 }, blockAction: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginTop: 14, padding: 14, border: "1px solid #fda29b", borderRadius: 14, background: "var(--dockos-danger-bg)" }, dangerButton: { minHeight: 42, padding: "9px 16px", border: 0, borderRadius: 11, color: "#fff", background: "#be123c", fontWeight: 900, cursor: "pointer" }, choiceEmpty: { marginTop: 14, padding: 18, textAlign: "center", borderRadius: 14, color: "var(--dockos-muted)", background: "var(--dockos-surface-alt)" },
  slotBuilder: { display: "grid", gap: 12, marginTop: 16, padding: 14, border: "1px dashed var(--dockos-border)", borderRadius: 14, background: "var(--dockos-surface-alt)" }, slotBuilderHead: { display: "grid", gap: 4, color: "var(--dockos-text)" }, ruleNote: { padding: 10, borderRadius: 10, color: "var(--dockos-info-text)", background: "var(--dockos-info-bg)", fontWeight: 800 }, customSlotGrid: { display: "grid", gridTemplateColumns: "repeat(3,minmax(150px,1fr)) auto", gap: 10, alignItems: "end" }, selectedSlotWrap: { display: "flex", flexWrap: "wrap", gap: 8 }, selectedSlotChip: { padding: "8px 11px", border: "1px solid #84adff", borderRadius: 10, color: "var(--dockos-info-text)", background: "var(--dockos-info-bg)", fontWeight: 900, cursor: "pointer" }, limitGrid: { display: "grid", gridTemplateColumns: "1fr 1fr 1.3fr", gap: 10, alignItems: "end" }, primaryButton: { minHeight: 42, border: 0, borderRadius: 11, color: "#fff", background: "#e5005a", fontWeight: 900, cursor: "pointer" },
  addButton: { padding: "10px 14px", border: "1px solid #101828", borderRadius: 11, color: "#fff", background: "#101828", fontWeight: 900, cursor: "pointer" }, matrixHeader: { display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 10, marginTop: 16, padding: "0 6px", color: "#667085", fontSize: 12, fontWeight: 900 }, matrixRows: { display: "grid", gap: 9, marginTop: 8 }, matrixRow: { display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr auto", gap: 10 }, removeButton: { minWidth: 86, border: "1px solid #fda29b", borderRadius: 11, color: "#b42318", background: "var(--dockos-surface)", fontWeight: 900, cursor: "pointer" }, secondaryButton: { width: "100%", minHeight: 46, marginTop: 16, border: 0, borderRadius: 12, color: "#fff", background: "#101828", fontWeight: 900, cursor: "pointer" }, message: { marginTop: 12, padding: 12, borderRadius: 12, color: "#344054", background: "#eef2ff", fontWeight: 800 },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(6,minmax(0,1fr))", gap: 10 }, statCard: { display: "grid", gap: 6, padding: 16, borderRadius: 16, background: "var(--dockos-surface)" }, statLabel: { color: "#667085", fontSize: 12, fontWeight: 800 }, statValue: { fontSize: 26 }, allocationGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 10 }, allocationCard: { display: "grid", gap: 5, padding: 14, border: "1px solid var(--dockos-border)", borderRadius: 14, background: "var(--dockos-surface-alt)" },
  dailyLimitGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))", gap: 10, marginBottom: 12 }, dailyLimitCard: { display: "grid", gap: 4, padding: 14, border: "1px solid #fedf89", borderRadius: 14, color: "var(--dockos-text)", background: "var(--dockos-surface-alt)" }, tableWrap: { overflowX: "auto", marginTop: 14 }, table: { width: "100%", minWidth: 980, borderCollapse: "collapse" }, openBadge: { padding: "5px 9px", borderRadius: 999, color: "var(--dockos-success-text)", background: "var(--dockos-success-bg)", fontWeight: 900 }, fullBadge: { padding: "5px 9px", borderRadius: 999, color: "var(--dockos-danger-text)", background: "var(--dockos-danger-bg)", fontWeight: 900 }, switchLabel: { display: "flex", alignItems: "center", gap: 7, color: "var(--dockos-muted)", fontWeight: 800 }, timeEdit: { display: "flex", alignItems: "center", gap: 5 }, compactInput: { minWidth: 82, maxWidth: 125, padding: "7px 8px", border: "1px solid var(--dockos-border)", borderRadius: 8, color: "var(--dockos-text)", background: "var(--dockos-surface)" }, rowActions: { display: "flex", flexWrap: "wrap", gap: 6 }, editSmall: { padding: "7px 10px", border: "1px solid #84adff", borderRadius: 8, color: "var(--dockos-info-text)", background: "var(--dockos-info-bg)", fontWeight: 900 }, deleteSmall: { padding: "7px 10px", border: "1px solid #fda29b", borderRadius: 8, color: "var(--dockos-danger-text)", background: "var(--dockos-danger-bg)", fontWeight: 900 }, saveSmall: { padding: "7px 10px", border: 0, borderRadius: 8, color: "#fff", background: "#e5005a", fontWeight: 900 }, cancelSmall: { padding: "7px 10px", border: "1px solid var(--dockos-border)", borderRadius: 8, color: "var(--dockos-text)", background: "var(--dockos-surface)", fontWeight: 900 }, empty: { padding: 26, textAlign: "center", borderRadius: 14, color: "var(--dockos-muted)", background: "var(--dockos-surface-alt)" },
};
