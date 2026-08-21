import React, { useEffect, useState } from "react";
import { getNotificationOutbox } from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const STATUSES = ["SENT", "PENDING", "WAITING_CONFIG", "FAILED", "CANCELLED"];

export default function NotificationCenter() {
  const { t, localeCode } = useDockOSUi();
  const [rows, setRows] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      setRows(await getNotificationOutbox(500));
      setMessage("");
    } catch (error) {
      setMessage(error.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load(true), 15000);
    return () => window.clearInterval(timer);
  }, []);

  const counts = rows.reduce((acc, row) => ({ ...acc, [row.status]: (acc[row.status] || 0) + 1 }), {});
  const statusLabel = (value) => value === "SENT" ? t("sent") : value === "PENDING" ? t("pending") : value === "WAITING_CONFIG" ? t("waitingConfig") : value === "FAILED" ? t("failed") : t("cancelled");

  return <div style={styles.page}>
    <section style={styles.hero}>
      <div><p style={styles.kicker}>{t("notificationKicker")}</p><h1 style={styles.title}>{t("notificationTitle")}</h1><p style={styles.subtitle}>{t("notificationSubtitle")}</p></div>
      <div style={styles.autoBadge}><span style={styles.liveDot} />{t("autoActive")}</div>
    </section>
    <div style={styles.autoInfo}>{loading ? "…" : t("autoInfo")}</div>
    {message && <div style={styles.message}>{message}</div>}
    <section style={styles.stats}>{STATUSES.map((status) => <div key={status} style={styles.card}><span>{statusLabel(status)}</span><strong>{counts[status] || 0}</strong></div>)}</section>
    <section style={styles.panel}>
      <div style={styles.tableWrap}><table style={styles.table}><thead><tr><th>{t("status")}</th><th>{t("event")}</th><th>{t("reservation")}</th><th>{t("scheduled")}</th><th>{t("recipients")}</th><th>{t("subject")}</th><th>{t("attempts")}</th></tr></thead><tbody>{rows.map((row) => <tr key={row.key}><td><Status value={row.status} label={statusLabel(row.status)} /></td><td>{row.event}</td><td><strong>{row.reservation_no}</strong></td><td>{new Date(row.due_at).toLocaleString(localeCode)}</td><td>{(row.recipients || []).join(", ") || t("waitingAddress")}</td><td>{row.subject}</td><td>{row.attempts || 0}</td></tr>)}</tbody></table></div>
      {!rows.length && <div style={styles.empty}>{t("noNotifications")}</div>}
    </section>
  </div>;
}

function Status({ value, label }) {
  const tone = value === "SENT" ? ["#027a48","#ecfdf3"] : value === "FAILED" ? ["#b42318","#fef3f2"] : value === "WAITING_CONFIG" ? ["#b54708","#fffaeb"] : ["#3538cd","#eef4ff"];
  return <span style={{ ...styles.badge, color:tone[0], background:tone[1] }}>{label}</span>;
}

const styles = {
  page:{display:"grid",gap:14,color:"var(--dockos-text)"}, hero:{display:"flex",justifyContent:"space-between",alignItems:"center",gap:16,padding:22,border:"1px solid var(--dockos-border)",borderRadius:20,background:"var(--dockos-surface)"}, kicker:{margin:0,color:"#e5005a",fontWeight:900}, title:{margin:"6px 0 0"}, subtitle:{margin:"6px 0 0",color:"var(--dockos-muted)"}, autoBadge:{display:"flex",alignItems:"center",gap:8,padding:"11px 14px",border:"1px solid #6ce9a6",borderRadius:999,color:"#027a48",background:"#ecfdf3",fontWeight:900,whiteSpace:"nowrap"}, liveDot:{width:9,height:9,borderRadius:"50%",background:"#12b76a",boxShadow:"0 0 0 5px rgba(18,183,106,.14)"}, autoInfo:{padding:12,borderRadius:12,background:"var(--dockos-surface-alt)",color:"var(--dockos-muted)",fontWeight:800}, message:{padding:12,borderRadius:12,background:"#fef3f2",color:"#b42318",fontWeight:800}, stats:{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:10}, card:{display:"grid",gap:5,padding:15,border:"1px solid var(--dockos-border)",borderRadius:15,background:"var(--dockos-surface)"}, panel:{padding:18,border:"1px solid var(--dockos-border)",borderRadius:18,background:"var(--dockos-surface)"}, tableWrap:{overflowX:"auto"}, table:{width:"100%",minWidth:1050,borderCollapse:"collapse"}, badge:{display:"inline-block",padding:"5px 8px",borderRadius:999,fontSize:11,fontWeight:900}, empty:{padding:24,textAlign:"center",color:"var(--dockos-muted)"}
};
