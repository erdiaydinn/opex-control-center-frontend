import React, { useState } from "react";
import { importPurchaseOrders } from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const REQUIRED = [
  "warehouse_name",
  "po_order_id",
  "supplier_id",
  "supplier_name",
  "created_date",
  "promised_date",
  "order_status",
  "total_sku",
];

function parseCsv(text) {
  const lines = text
    .replace(/\r/g, "")
    .split("\n")
    .filter((line) => line.trim());
  if (!lines.length) return [];

  const delimiter = lines[0].includes(";") ? ";" : ",";
  const split = (line) => {
    const result = [];
    let value = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"') {
        if (quoted && line[i + 1] === '"') {
          value += '"';
          i += 1;
        } else quoted = !quoted;
      } else if (char === delimiter && !quoted) {
        result.push(value.trim());
        value = "";
      } else value += char;
    }
    result.push(value.trim());
    return result;
  };

  const headers = split(lines[0]).map((x) => x.trim());
  return lines.slice(1).map((line) => {
    const values = split(line);
    return Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? ""]),
    );
  });
}

export default function PlanningPoUpload() {
  const { t } = useDockOSUi();
  const [rows, setRows] = useState([]);
  const [filename, setFilename] = useState("");
  const [message, setMessage] = useState("");
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [loading, setLoading] = useState(false);

  function handleFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = parseCsv(String(reader.result || ""));
        const missingHeaders = REQUIRED.filter(
          (key) => !Object.prototype.hasOwnProperty.call(parsed[0] || {}, key),
        );
        if (missingHeaders.length) {
          setRows([]);
          setMessage(`${t("missingColumns")}: ${missingHeaders.join(", ")}`);
          return;
        }
        setRows(parsed);
        setMessage(`${parsed.length} ${t("rowsRead")}`);
      } catch (error) {
        setMessage(error.message);
      }
    };
    reader.readAsText(file, "UTF-8");
  }

  async function upload() {
    if (!rows.length) return;
    setLoading(true);
    try {
      const result = await importPurchaseOrders({
        replace_existing: replaceExisting,
        rows: rows.map((row) => ({
          ...row,
          total_sku: Number(row.total_sku || 0),
        })),
      });
      setMessage(result.message);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div>
          <p style={styles.kicker}>{t("planningKicker")}</p>
          <h1 style={styles.title}>{t("bulkPoUpload")}</h1>
          <p style={styles.subtitle}>{t("planningSubtitle")}</p>
        </div>
      </section>

      <section style={styles.card}>
        <div style={styles.steps}>
          <Step
            number="1"
            title={t("chooseCsvStep")}
            description={t("chooseCsvStepHelp")}
            active
          />
          <Step
            number="2"
            title={t("validateStep")}
            description={t("validateStepHelp")}
            active={Boolean(rows.length)}
          />
          <Step
            number="3"
            title={t("uploadStep")}
            description={t("uploadStepHelp")}
            active={Boolean(rows.length)}
          />
        </div>

        <label style={styles.dropzone}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={handleFile}
            style={{ display: "none" }}
          />
          <span style={styles.uploadIcon}>⇧</span>
          <strong style={styles.dropTitle}>{t("chooseCsv")}</strong>
          <span style={styles.dropHelp}>{t("csvDropHelp")}</span>
          <span style={filename ? styles.fileBadgeActive : styles.fileBadge}>
            {filename || t("noFile")}
          </span>
        </label>

        <div style={styles.optionsBar}>
          <label style={styles.checkbox}>
            <input
              type="checkbox"
              checked={replaceExisting}
              onChange={(e) => setReplaceExisting(e.target.checked)}
              style={styles.checkInput}
            />
            <span style={styles.optionText}>
              <strong>{t("clearPrevious")}</strong>
              <small>{t("clearPreviousHelp")}</small>
            </span>
          </label>
        </div>

        <div className="dockos-upload-action-bar" style={styles.actionBar}>
          <div style={message ? styles.message : styles.actionHint}>
            {message || t("uploadActionHint")}
          </div>
          <button
            type="button"
            disabled={!rows.length || loading}
            onClick={upload}
            style={styles.button}
          >
            {loading ? t("saving") : `${rows.length} ${t("uploadPoRows")}`}
          </button>
        </div>
      </section>

      <section style={styles.card}>
        <h2 style={styles.sectionTitle}>{t("expectedColumns")}</h2>
        <div style={styles.columns}>
          {REQUIRED.map((key) => (
            <code key={key}>{key}</code>
          ))}
        </div>

        <div style={styles.tableWrap}>
          <table style={styles.table}>
            <thead>
              <tr>
                {REQUIRED.map((key) => (
                  <th key={key}>{key}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((row, index) => (
                <tr key={index}>
                  {REQUIRED.map((key) => (
                    <td key={key}>{row[key]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Step({ number, title, description, active }) {
  return (
    <div style={active ? styles.stepActive : styles.step}>
      <span style={active ? styles.stepNumberActive : styles.stepNumber}>
        {number}
      </span>
      <div>
        <strong style={styles.stepTitle}>{title}</strong>
        <small style={styles.stepDescription}>{description}</small>
      </div>
    </div>
  );
}

const styles = {
  page: { display: "grid", gap: 16, color: "var(--dockos-text)" },
  hero: {
    padding: 22,
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    background: "var(--dockos-surface)",
  },
  kicker: { margin: 0, color: "#e5005a", fontWeight: 900 },
  title: { margin: "7px 0 0", fontSize: 28 },
  subtitle: { margin: "7px 0 0", color: "var(--dockos-muted)" },
  card: {
    padding: 24,
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    background: "var(--dockos-surface)",
  },
  steps: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))",
    gap: 12,
    marginBottom: 22,
  },
  step: {
    display: "grid",
    gridTemplateColumns: "44px 1fr",
    alignItems: "center",
    gap: 12,
    minHeight: 76,
    padding: 14,
    border: "1px solid var(--dockos-border)",
    borderRadius: 15,
    color: "var(--dockos-muted)",
    background: "var(--dockos-surface-alt)",
  },
  stepActive: {
    display: "grid",
    gridTemplateColumns: "44px 1fr",
    alignItems: "center",
    gap: 12,
    minHeight: 76,
    padding: 14,
    border: "1px solid #f19aba",
    borderRadius: 15,
    color: "var(--dockos-text)",
    background: "var(--dockos-accent-soft-bg)",
  },
  stepNumber: {
    display: "grid",
    placeItems: "center",
    width: 42,
    height: 42,
    borderRadius: 13,
    color: "var(--dockos-muted)",
    background: "var(--dockos-surface)",
    fontSize: 17,
    fontWeight: 900,
  },
  stepNumberActive: {
    display: "grid",
    placeItems: "center",
    width: 42,
    height: 42,
    borderRadius: 13,
    color: "#fff",
    background: "linear-gradient(135deg,#e5005a,#7c3aed)",
    fontSize: 17,
    fontWeight: 900,
  },
  stepTitle: { display: "block", color: "var(--dockos-text)", fontSize: 14 },
  stepDescription: {
    display: "block",
    marginTop: 5,
    color: "var(--dockos-muted)",
    lineHeight: 1.35,
  },
  dropzone: {
    display: "grid",
    placeItems: "center",
    gap: 8,
    minHeight: 210,
    padding: 24,
    border: "2px dashed #f19aba",
    borderRadius: 20,
    background: "var(--dockos-accent-soft-bg)",
    cursor: "pointer",
    color: "var(--dockos-text)",
    textAlign: "center",
  },
  uploadIcon: {
    display: "grid",
    placeItems: "center",
    width: 52,
    height: 52,
    borderRadius: 16,
    color: "#fff",
    background: "linear-gradient(135deg,#e5005a,#7c3aed)",
    fontSize: 27,
    fontWeight: 900,
  },
  dropTitle: { fontSize: 17 },
  dropHelp: { color: "var(--dockos-muted)" },
  fileBadge: {
    marginTop: 5,
    padding: "8px 12px",
    border: "1px solid var(--dockos-border)",
    borderRadius: 999,
    color: "var(--dockos-muted)",
    background: "var(--dockos-surface)",
  },
  fileBadgeActive: {
    marginTop: 5,
    padding: "8px 12px",
    border: "1px solid #6ce9a6",
    borderRadius: 999,
    color: "var(--dockos-success-text)",
    background: "var(--dockos-success-bg)",
    fontWeight: 900,
  },
  optionsBar: {
    marginTop: 14,
    padding: 14,
    border: "1px solid var(--dockos-border)",
    borderRadius: 14,
    background: "var(--dockos-surface-alt)",
  },
  checkbox: {
    display: "flex",
    alignItems: "flex-start",
    gap: 10,
    color: "var(--dockos-text)",
    cursor: "pointer",
  },
  checkInput: { width: 18, height: 18, marginTop: 2, accentColor: "#e5005a" },
  optionText: { display: "grid", gap: 4 },
  actionBar: {
    display: "grid",
    gridTemplateColumns: "minmax(0,1fr) auto",
    alignItems: "center",
    gap: 14,
    marginTop: 16,
    paddingTop: 16,
    borderTop: "1px solid var(--dockos-border)",
  },
  message: {
    padding: 12,
    borderRadius: 12,
    background: "var(--dockos-info-bg)",
    color: "var(--dockos-info-text)",
    fontWeight: 800,
  },
  actionHint: { color: "var(--dockos-muted)" },
  button: {
    minWidth: 260,
    minHeight: 48,
    padding: "0 22px",
    border: 0,
    borderRadius: 12,
    background: "#e5005a",
    color: "#fff",
    fontWeight: 900,
    cursor: "pointer",
  },
  sectionTitle: { marginTop: 0 },
  columns: { display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 },
  tableWrap: { overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 12 },
};
