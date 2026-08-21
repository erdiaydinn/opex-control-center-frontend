import React, { useEffect, useState } from "react";
import { getAuditLog } from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";


export default function AuditLog() {
  const { t, localeCode } = useDockOSUi();
  const [rows, setRows] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setMessage("");
    try {
      setRows(await getAuditLog(500));
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div style={styles.page}>
      <section style={styles.header}>
        <div><p style={styles.kicker}>{t("auditKicker")}</p><h1 style={styles.title}>{t("auditTitle")}</h1><p style={styles.subtitle}>{t("auditSubtitle")}</p></div>
        <button type="button" onClick={load} disabled={loading} style={styles.button}>{loading ? t("refreshing") : t("refreshShort")}</button>
      </section>
      {message && <div style={styles.message}>{message}</div>}
      <section style={styles.card}>
        <table style={styles.table}><thead><tr><th style={styles.th}>{t("time")}</th><th style={styles.th}>{t("user")}</th><th style={styles.th}>{t("operation")}</th><th style={styles.th}>{t("entity")}</th><th style={styles.th}>{t("record")}</th><th style={styles.th}>{t("detail")}</th></tr></thead>
          <tbody>{rows.map((row, index) => <tr key={`${row.timestamp}-${index}`}><td style={styles.td}>{new Date(row.timestamp).toLocaleString(localeCode)}</td><td style={styles.td}>{row.user_email}</td><td style={styles.td}>{row.action}</td><td style={styles.td}>{row.entity_type}</td><td style={styles.td}>{row.entity_id}</td><td style={styles.td}><code>{JSON.stringify(row.details || {})}</code></td></tr>)}</tbody>
        </table>
        {!rows.length && !loading && <div style={styles.empty}>{t("noAudit")}</div>}
      </section>
    </div>
  );
}

const styles = {
  page: { display: "grid", gap: 16 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 22, border: "1px solid var(--dockos-border)", borderRadius: 20, background: "var(--dockos-surface)" },
  kicker: { margin: 0, color: "#e5005a", fontWeight: 900 }, title: { margin: "6px 0 0" }, subtitle: { margin: "6px 0 0", color: "#667085" },
  button: { border: 0, borderRadius: 12, padding: "11px 15px", background: "#101828", color: "#fff", fontWeight: 900, cursor: "pointer" },
  card: { padding: 18, overflowX: "auto", border: "1px solid var(--dockos-border)", borderRadius: 20, background: "var(--dockos-surface)" },
  table: { width: "100%", minWidth: 1050, borderCollapse: "collapse" }, th: { padding: 10, textAlign: "left", color: "#667085", borderBottom: "1px solid #e5e7eb" }, td: { padding: 10, verticalAlign: "top", borderBottom: "1px solid #f2f4f7" },
  message: { padding: 12, borderRadius: 12, background: "#fef3f2", color: "#b42318", fontWeight: 800 }, empty: { padding: 18, color: "#667085" },
};
