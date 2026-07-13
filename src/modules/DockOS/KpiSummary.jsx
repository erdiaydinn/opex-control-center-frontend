import React, { useEffect, useMemo, useState } from "react";
import { askAnalytics, executeAdminCommand, getKpis, getSuppliers, getWarehouses } from "./dockosApi";
import { useDockOSUi } from "./DockOSUiContext";

const COLORS = ["#e5005a", "#7c3aed", "#12b76a", "#f79009", "#2e90fa", "#667085"];
const isoToday = () => new Date().toISOString().slice(0, 10);
const daysAgo = (days) => new Date(Date.now() - days * 86400000).toISOString().slice(0, 10);
const SUGGESTIONS = {
  tr: ["En yakın rezervasyon hangi tedarikçiye ait?", "Son 7 gün geç gelen tedarikçileri göster", "Bu ay depo bazında iptal raporu ver", "Eti için Ankara DC'de bu ay maksimum 20 palet limiti uygula"],
  en: ["Which supplier owns the next reservation?", "Show suppliers that arrived late in the last 7 days", "Give a cancellation report by DC this month"],
  de: ["Zu welchem Lieferanten gehört die nächste Reservierung?", "Lieferanten mit Verspätung in den letzten 7 Tagen anzeigen", "Stornobericht nach Lager für diesen Monat"],
  ar: ["الحجز القادم تابع لأي مورد؟", "اعرض الموردين المتأخرين خلال آخر 7 يوم", "اعرض تقرير الإلغاء حسب المستودع هذا الشهر"],
};

export default function KpiSummary() {
  const { t, locale } = useDockOSUi();
  const [data, setData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [filters, setFilters] = useState({ supplier_name: "", warehouse_name: "", date_from: daysAgo(30), date_to: isoToday() });
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [report, setReport] = useState(null);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [chat, setChat] = useState([]);
  const [builder, setBuilder] = useState({ dimension: "tedarikçi", metric: "rezervasyon", period: "seçili dönem" });

  async function load(next = filters) {
    setLoading(true);
    try {
      setData(await getKpis(next));
      setMessage("");
    } catch (error) {
      setMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const [supplierRows, warehouseRows] = await Promise.all([getSuppliers(), getWarehouses()]);
        setSuppliers(supplierRows);
        setWarehouses(warehouseRows);
        await load(filters);
      } catch (error) {
        setMessage(error.message);
      }
    })();
  }, []);

  useEffect(() => {
    setChat([{ id: `welcome-${locale}`, role: "assistant", text: t("welcome") }]);
  }, [locale]);

  async function changeFilter(key, value) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    await load(next);
  }

  async function runQuestion(text = question) {
    const clean = text.trim();
    if (clean.length < 3) return;
    setQuestion("");
    setAssistantLoading(true);
    setChat((current) => [...current, { id: `user-${Date.now()}`, role: "user", text: clean }]);
    try {
      const result = await askAnalytics(clean, { ...filters, locale });
      setReport(result);
      setChat((current) => [...current, { id: `assistant-${Date.now()}`, role: "assistant", text: result.summary }]);
    } catch (error) {
      setChat((current) => [...current, { id: `error-${Date.now()}`, role: "assistant", text: error.message }]);
    } finally {
      setAssistantLoading(false);
    }
  }

  function runBuilder() {
    const periodPrefix = builder.period === "son 7 gün" ? "Son 7 gün " : builder.period === "bu ay" ? "Bu ay " : "";
    runQuestion(`${periodPrefix}${builder.dimension} bazında ${builder.metric} raporu ver`);
  }

  async function executePreview(action) {
    if (!action) return;
    setActionLoading(true);
    try {
      const result = await executeAdminCommand(action);
      setChat((current) => [...current, { id: `action-${Date.now()}`, role: "assistant", text: result.message }]);
      setReport((current) => ({ ...current, confirmation_required: false, action_completed: true, summary: result.message }));
    } catch (error) {
      setChat((current) => [...current, { id: `action-error-${Date.now()}`, role: "assistant", text: error.message }]);
    } finally {
      setActionLoading(false);
    }
  }

  const metricCards = useMemo(() => [
    { label: t("totalReservation"), value: data?.total_reservations ?? 0, helper: t("selectedPeriodHelp"), color: "#7c3aed" },
    { label: t("activeReservation"), value: data?.active_reservations ?? 0, helper: t("waitingOps"), color: "#2e90fa" },
    { label: t("onTime"), value: `%${safeNumber(data?.on_time_rate)}`, percent: safeNumber(data?.on_time_rate), helper: t("checkedVehicles"), color: "#12b76a" },
    { label: t("completion"), value: `%${safeNumber(data?.completion_rate)}`, percent: safeNumber(data?.completion_rate), helper: t("closedReservations"), color: "#7c3aed" },
    { label: t("cancelRate"), value: `%${safeNumber(data?.cancel_rate)}`, percent: safeNumber(data?.cancel_rate), helper: `${data?.cancelled ?? 0} ${t("record").toLocaleLowerCase()}`, color: "#e5005a" },
    { label: t("capacityUsage"), value: `%${safeNumber(data?.avg_capacity_usage)}`, percent: safeNumber(data?.avg_capacity_usage), helper: t("palletCapacity"), color: "#f79009" },
  ], [data, locale]);

  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <div><p style={styles.kicker}>DockOS · Dynamic Analytics</p><h1 style={styles.title}>{t("decisionCenter")}</h1><p style={styles.subtitle}>{t("decisionSubtitle")}</p></div>
        <button type="button" onClick={() => load()} disabled={loading} style={styles.darkButton}>{loading ? "…" : t("refresh")}</button>
      </section>

      <section style={styles.filters}>
        <FilterSelect value={filters.supplier_name} onChange={(event) => changeFilter("supplier_name", event.target.value)}><option value="">{t("allSuppliers")}</option>{suppliers.map((row) => <option key={row.supplier_name} value={row.supplier_name}>{row.supplier_name}</option>)}</FilterSelect>
        <FilterSelect value={filters.warehouse_name} onChange={(event) => changeFilter("warehouse_name", event.target.value)}><option value="">{t("allWarehouses")}</option>{warehouses.map((row) => <option key={row.warehouse_name} value={row.warehouse_name}>{row.warehouse_name}</option>)}</FilterSelect>
        <input type="date" value={filters.date_from} onChange={(event) => changeFilter("date_from", event.target.value)} style={styles.input} />
        <input type="date" value={filters.date_to} onChange={(event) => changeFilter("date_to", event.target.value)} style={styles.input} />
      </section>
      {message && <div style={styles.error}>{message}</div>}

      <section style={styles.assistantShell}>
        <div style={styles.assistantIntro}><span style={styles.aiBadge}>AI</span><div><h2 style={styles.assistantTitle}>{t("commandTitle")}</h2><p style={styles.assistantSub}>{t("commandSubtitle")}</p></div><span style={styles.securePill}>{t("private")}</span></div>
        <div style={styles.promptRow}><input value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") runQuestion(); }} placeholder={t("promptPlaceholder")} style={styles.promptInput} /><button type="button" onClick={() => runQuestion()} disabled={assistantLoading} style={styles.askButton}>{assistantLoading ? "…" : t("run")}</button></div>
        <div style={styles.suggestionWrap}>{SUGGESTIONS[locale].map((text) => <button key={text} type="button" onClick={() => runQuestion(text)} style={styles.suggestion}>{text}</button>)}</div>
        {chat.length > 1 && <div style={styles.chatWindow}>{chat.slice(-2).map((item) => <div key={item.id} style={item.role === "user" ? styles.userBubble : styles.assistantBubble}><strong>{item.role === "user" ? t("you") : "DockOS"}</strong><span>{item.text}</span></div>)}</div>}
      </section>

      {report && <DynamicReport report={report} onExecute={executePreview} actionLoading={actionLoading} />}

      <section style={styles.builderPanel}>
        <div><p style={styles.kicker}>{t("reportBuilder")}</p><h2 style={styles.builderTitle}>{t("builderTitle")}</h2></div>
        <FilterSelect value={builder.dimension} onChange={(event) => setBuilder({ ...builder, dimension: event.target.value })}><option value="tedarikçi">{t("supplierLabel")}</option><option value="depo">{t("warehouseLabel")}</option><option value="tarih trend">{t("dailyTrend")}</option><option value="durum">{t("status")}</option><option value="gönderim türü">{t("shipmentDistribution")}</option></FilterSelect>
        <FilterSelect value={builder.metric} onChange={(event) => setBuilder({ ...builder, metric: event.target.value })}><option value="rezervasyon">{t("reservation")}</option><option value="geç geliş">{t("late")}</option><option value="no-show">{t("noShow")}</option><option value="iptal">{t("cancel")}</option><option value="rampa uyumsuzluğu">{t("dockIncompatible")}</option><option value="tamamlanan">{t("completed")}</option></FilterSelect>
        <FilterSelect value={builder.period} onChange={(event) => setBuilder({ ...builder, period: event.target.value })}><option value="seçili dönem">{t("selectedPeriod")}</option><option value="son 7 gün">{t("last7")}</option><option value="bu ay">{t("thisMonth")}</option></FilterSelect>
        <button type="button" onClick={runBuilder} style={styles.buildButton}>{t("buildReport")}</button>
      </section>

      <section style={styles.kpiGrid}>{metricCards.map((card) => <MetricCard key={card.label} {...card} />)}</section>

      <section style={styles.chartGrid}>
        <Panel title={t("reservationStatus")} subtitle={t("operationStage")}><DonutChart rows={data?.status_breakdown || []} /></Panel>
        <Panel title={t("shipmentDistribution")} subtitle={t("shipmentRatio")}><DonutChart rows={data?.mode_breakdown || []} /></Panel>
        <Panel title={t("supplierVolume")} subtitle={t("busiestSuppliers")}><BarChart rows={data?.supplier_breakdown || []} valueKey="total" /></Panel>
        <Panel title={t("warehouseVolume")} subtitle={t("warehouseDistribution")}><BarChart rows={data?.warehouse_breakdown || []} valueKey="total" /></Panel>
      </section>

      <Panel title={t("dailyTrend")} subtitle={t("trendSubtitle")}><TrendChart rows={data?.daily_trend || []} /></Panel>

      <Panel title={t("supplierPerformance")} subtitle={t("compareIssues")}>
        <div style={styles.tableWrap}><table style={styles.table}><thead><tr><th>{t("supplierLabel")}</th><th>{t("total")}</th><th>{t("active")}</th><th>{t("completed")}</th><th>{t("late")}</th><th>{t("noShow")}</th><th>{t("cancel")}</th><th>{t("success")}</th></tr></thead><tbody>{(data?.supplier_breakdown || []).map((row) => <tr key={row.name}><td><strong>{row.name}</strong></td><td>{row.total}</td><td>{row.active}</td><td>{row.completed}</td><td>{row.late}</td><td>{row.no_show}</td><td>{row.cancelled}</td><td><ScoreBadge value={row.success_rate} /></td></tr>)}</tbody></table></div>
      </Panel>
    </div>
  );
}

function safeNumber(value) { const number = Number(value); return Number.isFinite(number) ? Math.round(number * 10) / 10 : 0; }
function FilterSelect({ children, ...props }) { return <select {...props} style={styles.input}>{children}</select>; }
function Panel({ title, subtitle, children }) { return <section style={styles.panel}><div style={styles.panelHead}><div><h2 style={styles.panelTitle}>{title}</h2>{subtitle && <p style={styles.panelSub}>{subtitle}</p>}</div></div>{children}</section>; }

function MetricCard({ label, value, percent, helper, color }) {
  return <div style={styles.metricCard}><div><span style={styles.metricLabel}>{label}</span><strong style={styles.metricValue}>{value}</strong><small style={styles.metricHelper}>{helper}</small></div>{percent !== undefined ? <Gauge value={percent} color={color} /> : <span style={{ ...styles.metricDot, background: color }} />}</div>;
}

function Gauge({ value, color }) {
  const normalized = Math.min(100, Math.max(0, safeNumber(value)));
  return <div style={{ ...styles.gauge, background: `conic-gradient(${color} ${normalized * 3.6}deg,#eaecf0 0deg)` }}><div style={styles.gaugeInner}>%{normalized}</div></div>;
}

function DonutChart({ rows }) {
  const { t } = useDockOSUi();
  const clean = rows.map((row) => ({ name: row.name || t("unspecified"), value: safeNumber(row.value ?? row.total) })).filter((row) => row.value >= 0);
  const total = clean.reduce((sum, row) => sum + row.value, 0);
  if (!total) return <Empty />;
  const radius = 54; const circumference = 2 * Math.PI * radius; let offset = 0;
  return <div style={styles.donutLayout}><div style={styles.donutWrap}><svg width="150" height="150" viewBox="0 0 150 150"><circle cx="75" cy="75" r={radius} fill="none" stroke="#f2f4f7" strokeWidth="18" />{clean.map((row, index) => { const dash = row.value / total * circumference; const currentOffset = offset; offset += dash; return <circle key={`${row.name}-${index}`} cx="75" cy="75" r={radius} fill="none" stroke={COLORS[index % COLORS.length]} strokeWidth="18" strokeDasharray={`${dash} ${circumference - dash}`} strokeDashoffset={-currentOffset} strokeLinecap="butt" transform="rotate(-90 75 75)" />; })}</svg><div style={styles.donutCenter}><strong>{total}</strong><span>{t("total")}</span></div></div><div style={styles.legend}>{clean.map((row, index) => <div key={`${row.name}-legend`} style={styles.legendRow}><span style={{ ...styles.legendDot, background: COLORS[index % COLORS.length] }} /><b>{row.name}</b><span>{row.value} · %{Math.round(row.value * 100 / total)}</span></div>)}</div></div>;
}

function BarChart({ rows, valueKey = "value" }) {
  const { t } = useDockOSUi();
  if (!rows.length) return <Empty />;
  const normalized = rows.slice(0, 10).map((row) => ({ name: row.name || t("unspecified"), value: safeNumber(row[valueKey]) }));
  const max = Math.max(1, ...normalized.map((row) => row.value));
  return <div style={styles.barList}>{normalized.map((row, index) => <div key={`${row.name}-${index}`} style={styles.barRow}><span title={row.name}>{row.name}</span><div style={styles.track}><div style={{ ...styles.bar, width: `${row.value / max * 100}%`, background: COLORS[index % COLORS.length] }} /></div><strong>{row.value}</strong></div>)}</div>;
}

function TrendChart({ rows }) {
  const { t } = useDockOSUi();
  if (!rows.length) return <Empty />;
  const max = Math.max(1, ...rows.map((row) => safeNumber(row.total)));
  return <div style={styles.trend}>{rows.map((row, index) => <div key={`${row.name}-${index}`} style={styles.trendItem}><span style={styles.trendValue}>{row.total}</span><div style={styles.trendStack}><div title={`${t("total")} ${row.total}`} style={{ ...styles.trendTotal, height: `${Math.max(8, safeNumber(row.total) / max * 150)}px` }} /><div title={`${t("late")} ${row.late || 0}`} style={{ ...styles.trendIssue, height: `${Math.max(0, safeNumber(row.late) / max * 150)}px` }} /></div><span>{String(row.name).slice(5)}</span></div>)}</div>;
}

function DynamicReport({ report, onExecute, actionLoading }) {
  const { t } = useDockOSUi();
  if (report.visualization === "answer") {
    return <section style={styles.dynamicReport}><div style={styles.reportHeader}><div><p style={styles.kicker}>{t("generatedReport")}</p><h2 style={styles.reportTitle}>{report.title}</h2><p style={styles.reportSummary}>{report.summary}</p></div><span style={styles.safeBadge}>{t("secureAnalytics")}</span></div><div style={styles.answerGrid}>{(report.answer_cards || []).map((item) => <div key={item.label} style={styles.answerCard}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div></section>;
  }
  if (report.visualization === "action") {
    return <section style={styles.actionPreview}><div><p style={styles.kicker}>{t("adminPreview")}</p><h2 style={styles.reportTitle}>{report.title}</h2><p style={styles.reportSummary}>{report.summary}</p></div>{report.action_preview && <div style={styles.actionFacts}><span><b>{t("supplierLabel")}</b>{report.action_preview.supplier_name}</span><span><b>{t("warehouseLabel")}</b>{report.action_preview.warehouse_name}</span><span><b>{t("dailyMax")}</b>{report.action_preview.max_pallet}</span></div>}{report.confirmation_required && <button type="button" onClick={() => onExecute(report.action_preview)} disabled={actionLoading} style={styles.confirmButton}>{actionLoading ? t("applying") : t("confirmApply")}</button>}{report.action_completed && <div style={styles.actionSuccess}>{t("actionSuccess")}</div>}</section>;
  }
  return <section style={styles.dynamicReport}><div style={styles.reportHeader}><div><p style={styles.kicker}>{t("generatedReport")}</p><h2 style={styles.reportTitle}>{report.title}</h2><p style={styles.reportSummary}>{report.summary}</p></div><span style={styles.safeBadge}>{t("secureAnalytics")}</span></div><div style={styles.reportBody}>{report.visualization === "donut" ? <DonutChart rows={report.rows} /> : report.visualization === "line" ? <TrendChart rows={report.rows.map((row) => ({ ...row, total: row.value }))} /> : <BarChart rows={report.rows} />}</div>{report.columns.length > 0 && <div style={styles.tableWrap}><table style={styles.table}><thead><tr>{report.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{report.rows.map((row, index) => <tr key={`${row.name}-${index}`}><td><strong>{row.name}</strong></td><td>{row.value}</td><td>{row.total}</td><td>%{row.rate}</td></tr>)}</tbody></table></div>}</section>;
}

function ScoreBadge({ value }) { const score = safeNumber(value); const style = score >= 90 ? styles.scoreGood : score >= 70 ? styles.scoreWarn : styles.scoreBad; return <span style={style}>%{score}</span>; }
function Empty() { const { t } = useDockOSUi(); return <div style={styles.empty}>{t("noData")}</div>; }

const styles = {
  page: { display: "grid", gap: 14, color: "var(--dockos-text)" }, hero: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 24, border: "1px solid var(--dockos-border)", borderRadius: 22, background: "linear-gradient(135deg,#fff 0%,#fff7fb 100%)" }, kicker: { margin: 0, color: "#e5005a", fontWeight: 900 }, title: { margin: "6px 0 0", fontSize: 30 }, subtitle: { margin: "7px 0 0", color: "#475467" }, darkButton: { border: 0, borderRadius: 12, padding: "12px 17px", color: "#fff", background: "#101828", fontWeight: 900, cursor: "pointer" },
  filters: { display: "grid", gridTemplateColumns: "1.3fr 1.3fr 1fr 1fr", gap: 10, padding: 14, border: "1px solid var(--dockos-border)", borderRadius: 16, background: "var(--dockos-surface)" }, input: { boxSizing: "border-box", width: "100%", minHeight: 43, padding: "9px 12px", border: "1px solid #d0d5dd", borderRadius: 11, color: "var(--dockos-text)", background: "var(--dockos-surface)" }, error: { padding: 12, borderRadius: 12, color: "#b42318", background: "#fef3f2" },
  assistantShell: { padding: 18, border: "1px solid #d6bbfb", borderRadius: 20, background: "linear-gradient(135deg,#ffffff 0%,#f4f3ff 100%)", color: "var(--dockos-text)", boxShadow: "0 10px 28px rgba(16,24,40,.07)" }, assistantIntro: { display: "flex", alignItems: "center", gap: 12 }, aiBadge: { display: "grid", placeItems: "center", width: 40, height: 40, borderRadius: 13, color: "#fff", background: "linear-gradient(135deg,#e5005a,#7c3aed)", fontWeight: 900 }, assistantTitle: { margin: 0, fontSize: 18 }, assistantSub: { margin: "3px 0 0", color: "#667085" }, securePill: { marginInlineStart: "auto", padding: "7px 10px", borderRadius: 999, color: "#5925dc", background: "#ebe9fe", fontSize: 11, fontWeight: 900 }, chatWindow: { display: "grid", gap: 7, marginTop: 12, maxHeight: 120, overflowY: "auto" }, assistantBubble: { display: "flex", gap: 8, justifySelf: "start", maxWidth: "90%", padding: "8px 11px", borderRadius: 10, color: "#344054", background: "var(--dockos-surface)" }, userBubble: { display: "flex", gap: 8, justifySelf: "end", maxWidth: "90%", padding: "8px 11px", borderRadius: 10, color: "#fff", background: "#7c3aed" }, promptRow: { display: "grid", gridTemplateColumns: "1fr auto", gap: 9, marginTop: 13 }, promptInput: { minHeight: 48, padding: "10px 14px", border: "2px solid #7c3aed", borderRadius: 13, color: "var(--dockos-text)", background: "var(--dockos-surface)" }, askButton: { minWidth: 120, border: 0, borderRadius: 13, color: "#fff", background: "#e5005a", fontWeight: 900, cursor: "pointer" }, suggestionWrap: { display: "flex", flexWrap: "wrap", gap: 7, marginTop: 9 }, suggestion: { padding: "7px 10px", border: "1px solid #d0d5dd", borderRadius: 999, color: "#475467", background: "var(--dockos-surface)", fontSize: 11, cursor: "pointer" },
  builderPanel: { display: "grid", gridTemplateColumns: "1.6fr repeat(3,1fr) auto", gap: 10, alignItems: "end", padding: 18, border: "1px solid var(--dockos-border)", borderRadius: 18, background: "var(--dockos-surface)" }, builderTitle: { margin: "4px 0 0", fontSize: 18 }, buildButton: { minHeight: 43, padding: "9px 15px", border: 0, borderRadius: 11, color: "#fff", background: "#7c3aed", fontWeight: 900, cursor: "pointer" },
  kpiGrid: { display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 11 }, metricCard: { display: "flex", justifyContent: "space-between", alignItems: "center", minHeight: 105, padding: 18, border: "1px solid var(--dockos-border)", borderRadius: 18, background: "var(--dockos-surface)", boxShadow: "0 6px 18px rgba(16,24,40,.04)" }, metricLabel: { display: "block", color: "#667085", fontSize: 12, fontWeight: 900 }, metricValue: { display: "block", marginTop: 5, fontSize: 29 }, metricHelper: { display: "block", marginTop: 4, color: "#98a2b3" }, metricDot: { width: 14, height: 50, borderRadius: 999 }, gauge: { width: 72, height: 72, display: "grid", placeItems: "center", borderRadius: "50%" }, gaugeInner: { width: 52, height: 52, display: "grid", placeItems: "center", borderRadius: "50%", background: "var(--dockos-surface)", fontWeight: 900, fontSize: 12 },
  chartGrid: { display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 12 }, panel: { padding: 18, border: "1px solid var(--dockos-border)", borderRadius: 18, background: "var(--dockos-surface)" }, panelHead: { display: "flex", justifyContent: "space-between", marginBottom: 16 }, panelTitle: { margin: 0, fontSize: 17 }, panelSub: { margin: "4px 0 0", color: "#667085", fontSize: 12 }, donutLayout: { display: "flex", alignItems: "center", justifyContent: "space-around", gap: 18, minHeight: 180 }, donutWrap: { position: "relative", width: 150, height: 150 }, donutCenter: { position: "absolute", inset: 0, display: "grid", placeContent: "center", textAlign: "center" }, legend: { display: "grid", gap: 10, minWidth: 190 }, legendRow: { display: "grid", gridTemplateColumns: "12px 1fr auto", gap: 8, alignItems: "center" }, legendDot: { width: 10, height: 10, borderRadius: "50%" },
  barList: { display: "grid", gap: 11 }, barRow: { display: "grid", gridTemplateColumns: "minmax(110px,180px) 1fr 38px", gap: 10, alignItems: "center" }, track: { height: 12, borderRadius: 999, background: "#f2f4f7", overflow: "hidden" }, bar: { height: "100%", borderRadius: 999 }, trend: { display: "flex", alignItems: "end", gap: 10, minHeight: 210, overflowX: "auto", paddingTop: 12 }, trendItem: { minWidth: 48, display: "grid", justifyItems: "center", gap: 5 }, trendStack: { position: "relative", width: 32, height: 150, display: "flex", alignItems: "end" }, trendTotal: { position: "absolute", bottom: 0, width: 32, borderRadius: "8px 8px 2px 2px", background: "#7c3aed" }, trendIssue: { position: "absolute", bottom: 0, width: 32, borderRadius: "8px 8px 2px 2px", background: "#e5005a" }, trendValue: { fontSize: 11, fontWeight: 900 },
  dynamicReport: { padding: 20, border: "2px solid #7c3aed", borderRadius: 22, background: "var(--dockos-surface)", boxShadow: "0 16px 36px rgba(124,58,237,.12)" }, reportHeader: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }, reportTitle: { margin: "5px 0 0" }, reportSummary: { margin: "7px 0 0", color: "var(--dockos-muted)" }, safeBadge: { padding: "8px 11px", borderRadius: 999, color: "#5925dc", background: "#f4f3ff", fontWeight: 900, fontSize: 12 }, reportBody: { marginTop: 16, padding: 16, borderRadius: 16, background: "var(--dockos-surface-alt)" }, answerGrid:{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:10,marginTop:16},answerCard:{display:"grid",gap:5,padding:14,border:"1px solid var(--dockos-border)",borderRadius:14,background:"var(--dockos-surface-alt)"},
  actionPreview: { display: "grid", gap: 14, padding: 20, border: "2px solid #f79009", borderRadius: 20, background: "var(--dockos-surface)" }, actionFacts: { display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 10 }, confirmButton: { minHeight: 46, border: 0, borderRadius: 12, color: "#fff", background: "#b54708", fontWeight: 900, cursor: "pointer" }, actionSuccess: { padding: 12, borderRadius: 12, color: "#027a48", background: "#ecfdf3", fontWeight: 900 },
  tableWrap: { overflowX: "auto" }, table: { width: "100%", minWidth: 760, borderCollapse: "collapse" }, scoreGood: { padding: "5px 9px", borderRadius: 999, color: "#027a48", background: "#ecfdf3", fontWeight: 900 }, scoreWarn: { padding: "5px 9px", borderRadius: 999, color: "#b54708", background: "#fffaeb", fontWeight: 900 }, scoreBad: { padding: "5px 9px", borderRadius: 999, color: "#b42318", background: "#fef3f2", fontWeight: 900 }, empty: { padding: 30, textAlign: "center", color: "#667085", background: "var(--dockos-surface-alt)", borderRadius: 12 },
};
