import React, { useEffect, useMemo, useState } from "react";
import {
  deleteSupplierAccessMapping,
  getSupplierAccessMappings,
  getSuppliers,
  getWarehouses,
  saveSupplierAccessMapping,
} from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const emptyForm = {
  email: "",
  supplier_names: [],
  warehouse_names: [],
  all_warehouses: true,
  active: true,
  locale: "tr",
};

export default function SupplierAccessManagement() {
  const { t } = useDockOSUi();
  const [rows, setRows] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  async function load() {
    const [accessRows, supplierRows, warehouseRows] = await Promise.all([
      getSupplierAccessMappings(),
      getSuppliers(),
      getWarehouses(),
    ]);
    setRows(accessRows);
    setSuppliers(supplierRows);
    setWarehouses(warehouseRows);
  }
  useEffect(() => {
    load().catch((error) => setMessage(error.message));
  }, []);
  const visible = useMemo(
    () =>
      rows.filter((row) =>
        `${row.email} ${(row.supplier_names || []).join(" ")} ${(row.warehouse_names || []).join(" ")}`
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase()),
      ),
    [rows, search],
  );
  function toggle(key, value) {
    setForm((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value],
    }));
  }
  function edit(row) {
    setForm({
      email: row.email,
      supplier_names: row.supplier_names || [],
      warehouse_names: row.warehouse_names || [],
      all_warehouses: row.all_warehouses !== false,
      active: row.active !== false,
      locale: row.locale || "tr",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const result = await saveSupplierAccessMapping(form);
      setMessage(result.message);
      setForm(emptyForm);
      await load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  }
  async function remove(email) {
    if (!window.confirm(t("accessDeleteConfirm"))) return;
    try {
      const result = await deleteSupplierAccessMapping(email);
      setMessage(result.message);
      if (form.email === email) setForm(emptyForm);
      await load();
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.kicker}>DockOS · {t("accessManagement")}</p>
          <h1 style={styles.title}>{t("supplierEmailAccess")}</h1>
          <p style={styles.subtitle}>{t("supplierEmailAccessSubtitle")}</p>
        </div>
        <span style={styles.secure}>{t("adminOnly")}</span>
      </section>
      <form onSubmit={save} style={styles.form}>
        <section style={styles.identityCard}>
          <div style={styles.identityHead}>
            <span style={styles.identityIcon}>@</span>
            <div>
              <h2 style={styles.identityTitle}>{t("accessIdentityTitle")}</h2>
              <p style={styles.identityHelp}>{t("accessIdentityHelp")}</p>
            </div>
          </div>
          <div className="dockos-access-identity-grid" style={styles.topGrid}>
            <label style={styles.field}>
              <span>{t("emailAddress")}</span>
              <input
                style={styles.control}
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="supplier@company.com"
              />
            </label>
            <label style={styles.field}>
              <span>{t("preferredLanguage")}</span>
              <select
                style={styles.control}
                value={form.locale}
                onChange={(e) => setForm({ ...form, locale: e.target.value })}
              >
                <option value="tr">Türkçe</option>
                <option value="en">English</option>
                <option value="de">Deutsch</option>
                <option value="ar">العربية</option>
              </select>
            </label>
          </div>
          <label
            style={form.active ? styles.activeCardOn : styles.activeCardOff}
          >
            <span style={styles.statusDot} />
            <span style={styles.activeCopy}>
              <strong>{t("accessActive")}</strong>
              <small>{t("activeAccessHelp")}</small>
            </span>
            <input
              style={styles.statusCheck}
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
            />
          </label>
        </section>
        <AccessChoices
          title={t("visibleSuppliers")}
          help={t("visibleSuppliersHelp")}
          values={suppliers.map((row) => row.supplier_name)}
          selected={form.supplier_names}
          onToggle={(value) => toggle("supplier_names", value)}
        />
        <div style={styles.allWarehouse}>
          <label style={styles.toggle}>
            <input
              type="checkbox"
              checked={form.all_warehouses}
              onChange={(e) =>
                setForm({
                  ...form,
                  all_warehouses: e.target.checked,
                  warehouse_names: e.target.checked ? [] : form.warehouse_names,
                })
              }
            />
            <span>{t("allWarehousesAccess")}</span>
          </label>
        </div>
        {!form.all_warehouses && (
          <AccessChoices
            title={t("visibleWarehouses")}
            help={t("visibleWarehousesHelp")}
            values={warehouses.map((row) => row.warehouse_name)}
            selected={form.warehouse_names}
            onToggle={(value) => toggle("warehouse_names", value)}
          />
        )}
        <div className="dockos-access-actions" style={styles.actions}>
          <button
            type="button"
            onClick={() => setForm(emptyForm)}
            style={styles.clear}
          >
            {t("clearForm")}
          </button>
          <button
            disabled={saving || !form.supplier_names.length}
            style={styles.save}
          >
            {saving ? t("saving") : t("saveAccess")}
          </button>
        </div>
        {message && <div style={styles.message}>{message}</div>}
      </form>
      <section style={styles.list}>
        <div className="dockos-access-list-head" style={styles.listHead}>
          <div>
            <h2 style={styles.listTitle}>{t("existingAccessMappings")}</h2>
            <p style={styles.listHelp}>{t("accessRuleHint")}</p>
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("searchEmailSupplier")}
            style={styles.search}
          />
        </div>
        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th>{t("emailAddress")}</th>
                <th>{t("visibleSuppliers")}</th>
                <th>{t("visibleWarehouses")}</th>
                <th>{t("preferredLanguage")}</th>
                <th>{t("status")}</th>
                <th>{t("action")}</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.email}>
                  <td>
                    <strong>{row.email}</strong>
                  </td>
                  <td>{(row.supplier_names || []).join(", ")}</td>
                  <td>
                    {row.all_warehouses !== false
                      ? t("allWarehouses")
                      : (row.warehouse_names || []).join(", ") || "-"}
                  </td>
                  <td>{String(row.locale || "tr").toUpperCase()}</td>
                  <td>
                    <span
                      style={
                        row.active !== false ? styles.active : styles.passive
                      }
                    >
                      {row.active !== false ? t("active") : t("passive")}
                    </span>
                  </td>
                  <td>
                    <div style={styles.rowActions}>
                      <button
                        type="button"
                        onClick={() => edit(row)}
                        style={styles.edit}
                      >
                        {t("edit")}
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(row.email)}
                        style={styles.delete}
                      >
                        {t("remove")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!visible.length && (
          <div style={styles.empty}>{t("noAccessMapping")}</div>
        )}
      </section>
    </div>
  );
}

function AccessChoices({ title, help, values, selected, onToggle }) {
  return (
    <section style={styles.choices}>
      <div>
        <h3 style={styles.choiceTitle}>{title}</h3>
        <p style={styles.choiceHelp}>{help}</p>
      </div>
      <div style={styles.choiceGrid}>
        {values.map((value) => (
          <label
            key={value}
            style={
              selected.includes(value) ? styles.choiceActive : styles.choice
            }
          >
            <input
              style={styles.choiceCheck}
              type="checkbox"
              checked={selected.includes(value)}
              onChange={() => onToggle(value)}
            />
            <span>{value}</span>
          </label>
        ))}
      </div>
    </section>
  );
}

const styles = {
  page: { display: "grid", gap: 18, color: "var(--dockos-text)" },
  hero: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    padding: 24,
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    background: "var(--dockos-surface)",
  },
  kicker: { margin: 0, color: "#e5005a", fontWeight: 900 },
  title: { margin: "6px 0 0", fontSize: 28 },
  subtitle: { margin: "6px 0 0", color: "var(--dockos-muted)" },
  secure: {
    padding: "9px 12px",
    borderRadius: 999,
    color: "var(--dockos-info-text)",
    background: "var(--dockos-info-bg)",
    fontWeight: 900,
  },
  form: {
    display: "grid",
    gap: 18,
    padding: 24,
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    background: "var(--dockos-surface)",
  },
  identityCard: {
    display: "grid",
    gap: 18,
    padding: 20,
    border: "1px solid var(--dockos-border)",
    borderRadius: 17,
    background: "var(--dockos-surface-alt)",
  },
  identityHead: { display: "flex", alignItems: "center", gap: 12 },
  identityIcon: {
    display: "grid",
    placeItems: "center",
    width: 44,
    height: 44,
    borderRadius: 14,
    color: "#fff",
    background: "linear-gradient(135deg,#e5005a,#7c3aed)",
    fontSize: 20,
    fontWeight: 900,
  },
  identityTitle: { margin: 0, fontSize: 18 },
  identityHelp: { margin: "4px 0 0", color: "var(--dockos-muted)" },
  topGrid: {
    display: "grid",
    gridTemplateColumns: "minmax(280px,2fr) minmax(220px,1fr)",
    gap: 14,
    alignItems: "end",
  },
  field: { display: "grid", gap: 8, fontWeight: 900, fontSize: 12 },
  control: {
    boxSizing: "border-box",
    width: "100%",
    minHeight: 48,
    padding: "11px 13px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 12,
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
    fontSize: 14,
  },
  activeCardOn: {
    display: "grid",
    gridTemplateColumns: "auto 1fr auto",
    alignItems: "center",
    gap: 12,
    minHeight: 62,
    padding: "12px 15px",
    border: "1px solid #6ce9a6",
    borderRadius: 14,
    color: "var(--dockos-success-text)",
    background: "var(--dockos-success-bg)",
    cursor: "pointer",
  },
  activeCardOff: {
    display: "grid",
    gridTemplateColumns: "auto 1fr auto",
    alignItems: "center",
    gap: 12,
    minHeight: 62,
    padding: "12px 15px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 14,
    color: "var(--dockos-muted)",
    background: "var(--dockos-surface)",
    cursor: "pointer",
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: "50%",
    background: "currentColor",
    boxShadow: "0 0 0 5px rgba(18,183,106,.12)",
  },
  activeCopy: { display: "grid", gap: 4 },
  statusCheck: { width: 20, height: 20, accentColor: "#e5005a" },
  toggle: {
    display: "flex",
    alignItems: "center",
    gap: 9,
    minHeight: 44,
    fontWeight: 900,
  },
  choices: {
    display: "grid",
    gap: 14,
    padding: 20,
    border: "1px solid var(--dockos-border)",
    borderRadius: 17,
    background: "var(--dockos-surface-alt)",
  },
  choiceTitle: { margin: 0, fontSize: 17 },
  choiceHelp: { margin: "5px 0 0", color: "var(--dockos-muted)" },
  choiceGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))",
    gap: 10,
  },
  choice: {
    display: "flex",
    alignItems: "center",
    gap: 9,
    minHeight: 46,
    padding: "10px 12px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 12,
    background: "var(--dockos-surface)",
    cursor: "pointer",
  },
  choiceActive: {
    display: "flex",
    alignItems: "center",
    gap: 9,
    minHeight: 46,
    padding: "10px 12px",
    border: "1px solid #7c3aed",
    borderRadius: 12,
    color: "var(--dockos-info-text)",
    background: "var(--dockos-info-bg)",
    fontWeight: 900,
    cursor: "pointer",
  },
  choiceCheck: { width: 17, height: 17, accentColor: "#7c3aed" },
  allWarehouse: { padding: "4px 6px" },
  actions: {
    display: "grid",
    gridTemplateColumns: "auto minmax(220px,1fr)",
    gap: 12,
    paddingTop: 4,
  },
  clear: {
    minHeight: 48,
    padding: "0 18px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 12,
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
    fontWeight: 900,
    cursor: "pointer",
  },
  save: {
    minHeight: 48,
    border: 0,
    borderRadius: 12,
    color: "#fff",
    background: "#e5005a",
    fontWeight: 900,
    cursor: "pointer",
  },
  message: {
    padding: 13,
    borderRadius: 12,
    color: "var(--dockos-success-text)",
    background: "var(--dockos-success-bg)",
    fontWeight: 900,
  },
  list: {
    padding: 24,
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    background: "var(--dockos-surface)",
  },
  listHead: {
    display: "flex",
    justifyContent: "space-between",
    gap: 18,
    alignItems: "center",
  },
  listTitle: { margin: 0 },
  listHelp: { margin: "5px 0 0", color: "var(--dockos-muted)" },
  search: {
    boxSizing: "border-box",
    minWidth: 340,
    minHeight: 46,
    padding: "10px 13px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 12,
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
  },
  tableWrap: { overflowX: "auto", marginTop: 18 },
  table: { width: "100%", minWidth: 900, borderCollapse: "collapse" },
  rowActions: { display: "flex", gap: 7 },
  edit: {
    padding: "8px 11px",
    border: "1px solid #84adff",
    borderRadius: 9,
    color: "var(--dockos-info-text)",
    background: "var(--dockos-info-bg)",
    fontWeight: 900,
    cursor: "pointer",
  },
  delete: {
    padding: "8px 11px",
    border: "1px solid #fda29b",
    borderRadius: 9,
    color: "var(--dockos-danger-text)",
    background: "var(--dockos-danger-bg)",
    fontWeight: 900,
    cursor: "pointer",
  },
  active: {
    padding: "5px 8px",
    borderRadius: 999,
    color: "var(--dockos-success-text)",
    background: "var(--dockos-success-bg)",
    fontWeight: 900,
  },
  passive: {
    padding: "5px 8px",
    borderRadius: 999,
    color: "var(--dockos-muted)",
    background: "var(--dockos-surface-alt)",
    fontWeight: 900,
  },
  empty: { padding: 22, textAlign: "center", color: "var(--dockos-muted)" },
};
