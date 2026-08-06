import React, { useMemo } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Building2,
  CalendarRange,
  Clock3,
  Gauge,
  ScanLine,
  TrendingUp,
  UsersRound,
} from "lucide-react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatMinutes } from "./workforceData.js";
import { buildWorkforceAnalytics } from "./workforceAnalytics.js";

const COPY = {
  tr: {
    eyebrow: "WORKFORCE ANALYTICS", title: "Verimlilik ve iş gücü karar merkezi", description: "Salt okunur analiz ekranı; depo, BY ve Regional Manager performansını aynı dönem içinde karşılaştırır.",
    start: "Başlangıç", end: "Kesim tarihi", rm: "Regional Manager", re: "BY / Regional Executive", warehouse: "Depo", all: "Tümü", allWarehouses: "Tüm depolar", sourceRoster: "Geçici roster + izin + norm", sourceLive: "Ana kaynak: check-in/out + norm", rows: "kayıt",
    effective: "Efektif çalışma", overtime: "Fazla mesai", overtimeRate: "Mesai oranı", checkin: "Check-in başarısı", normGap: "Norm altında depo", critical: "Kritik depo", periodTotal: "Dönem toplamı", laborDays: "planlı kişi-gün", topOvertime: "En çok fazla mesai yapan depolar", overtimeHours: "Fazla mesai (saat)", trend: "Günlük mesai ve check-in kırılımı", overtimeShort: "Mesai saati", noCheckin: "Kayıtsız kişi-gün", executive: "BY / bölge yöneticisi karşılaştırması", pressure: "İş gücü baskısı en yüksek depolar", signals: "Karar sinyalleri", avoidable: "Norm yeterli olduğu halde mesai oluşan depolar", manager: "Regional Manager", exec: "BY / Regional Executive", depots: "Depo", norm: "Norm", active: "Aktif", capacity: "Doluluk", score: "Baskı", status: "Durum", total: "Toplam", headcount: "Kadro", gap: "Açık", anomalies: "11s", interpretation: "Analist yorumu", healthy: "Dengeli", warning: "İzle", criticalRisk: "Kritik", criticalText: "Norm açığı, kayıt kaybı veya mesai yoğunluğu birlikte yükseliyor.", warningText: "Birden fazla gösterge eşik değerine yaklaşıyor.", healthyText: "Dönem verisi norm ve çalışma yüküyle dengeli.", empty: "Seçilen dönem ve filtreler için analiz edilebilir kayıt yok.", leakage: "Bu depolarda kadro normu karşılıyor; mesainin vardiya dağılımı, izin çakışması veya saat planından gelme ihtimali yüksek.", readOnly: "Bu ekranda veri değiştirilmez; sonuçlar puantaj, personel ana veri, izin ve norm kayıtlarından hesaplanır.",
  },
  en: {
    eyebrow: "WORKFORCE ANALYTICS", title: "Productivity and workforce decision center", description: "Read-only analytics comparing warehouse, Regional Executive and Regional Manager performance for one period.",
    start: "Start", end: "Cut-off date", rm: "Regional Manager", re: "Regional Executive", warehouse: "Warehouse", all: "All", allWarehouses: "All warehouses", sourceRoster: "Temporary roster + leave + norm", sourceLive: "Primary source: check-in/out + norm", rows: "records",
    effective: "Effective work", overtime: "Overtime", overtimeRate: "Overtime rate", checkin: "Check-in success", normGap: "Below-norm sites", critical: "Critical sites", periodTotal: "Period total", laborDays: "planned person-days", topOvertime: "Warehouses with the most overtime", overtimeHours: "Overtime (hours)", trend: "Daily overtime and check-in breakdown", overtimeShort: "Overtime hours", noCheckin: "Missing person-days", executive: "Regional Executive / manager comparison", pressure: "Warehouses under highest labor pressure", signals: "Decision signals", avoidable: "Overtime despite sufficient staffing norm", manager: "Regional Manager", exec: "Regional Executive", depots: "Sites", norm: "Norm", active: "Active", capacity: "Coverage", score: "Pressure", status: "Status", total: "Total", headcount: "Staff", gap: "Gap", anomalies: "11h", interpretation: "Analyst view", healthy: "Balanced", warning: "Watch", criticalRisk: "Critical", criticalText: "Staffing gap, missing records or overtime intensity are rising together.", warningText: "Multiple indicators are approaching their thresholds.", healthyText: "Period data is balanced against staffing and workload.", empty: "No analyzable records for the selected period and filters.", leakage: "Staffing meets the norm; overtime is likely driven by shift allocation, leave overlap or schedule design.", readOnly: "This screen cannot change data; results are calculated from attendance, employee master, leave and norm records.",
  },
  de: {
    eyebrow: "WORKFORCE ANALYTICS", title: "Produktivitäts- und Personalentscheidungszentrum", description: "Schreibgeschützte Analyse für Lager, Regional Executive und Regional Manager im selben Zeitraum.",
    start: "Beginn", end: "Stichtag", rm: "Regional Manager", re: "Regional Executive", warehouse: "Lager", all: "Alle", allWarehouses: "Alle Lager", sourceRoster: "Temporärer Roster + Abwesenheit + Norm", sourceLive: "Hauptquelle: Check-in/out + Norm", rows: "Datensätze",
    effective: "Effektive Arbeit", overtime: "Überstunden", overtimeRate: "Überstundenquote", checkin: "Check-in-Erfolg", normGap: "Lager unter Norm", critical: "Kritische Lager", periodTotal: "Zeitraum gesamt", laborDays: "geplante Personentage", topOvertime: "Lager mit den meisten Überstunden", overtimeHours: "Überstunden (Stunden)", trend: "Tägliche Überstunden und Check-in", overtimeShort: "Überstunden", noCheckin: "Fehlende Personentage", executive: "Vergleich Regional Executive / Manager", pressure: "Lager mit höchstem Personaldruck", signals: "Entscheidungssignale", avoidable: "Überstunden trotz ausreichender Norm", manager: "Regional Manager", exec: "Regional Executive", depots: "Lager", norm: "Norm", active: "Aktiv", capacity: "Deckung", score: "Druck", status: "Status", total: "Gesamt", headcount: "Personal", gap: "Lücke", anomalies: "11 Std.", interpretation: "Analyse", healthy: "Ausgeglichen", warning: "Beobachten", criticalRisk: "Kritisch", criticalText: "Personallücke, fehlende Buchungen oder Überstunden steigen gemeinsam.", warningText: "Mehrere Kennzahlen nähern sich ihren Schwellenwerten.", healthyText: "Zeitraumdaten sind mit Norm und Arbeitslast ausgeglichen.", empty: "Keine auswertbaren Daten für Zeitraum und Filter.", leakage: "Die Norm ist erfüllt; Überstunden entstehen wahrscheinlich durch Schichtverteilung, Abwesenheiten oder Planung.", readOnly: "Diese Ansicht ändert keine Daten; sie nutzt Zeit-, Personal-, Abwesenheits- und Normdaten.",
  },
  ar: {
    eyebrow: "تحليلات القوى العاملة", title: "مركز قرارات الإنتاجية والقوى العاملة", description: "تحليل للقراءة فقط يقارن أداء المستودعات والمديرين ضمن الفترة نفسها.",
    start: "البداية", end: "تاريخ القطع", rm: "المدير الإقليمي", re: "التنفيذي الإقليمي", warehouse: "المستودع", all: "الكل", allWarehouses: "كل المستودعات", sourceRoster: "الجدول المؤقت + الإجازات + المعيار", sourceLive: "المصدر الرئيسي: تسجيل الدخول والخروج + المعيار", rows: "سجل",
    effective: "العمل الفعلي", overtime: "العمل الإضافي", overtimeRate: "نسبة الإضافي", checkin: "نجاح تسجيل الدخول", normGap: "مستودعات دون المعيار", critical: "مستودعات حرجة", periodTotal: "إجمالي الفترة", laborDays: "يوم عمل مخطط", topOvertime: "المستودعات الأعلى في العمل الإضافي", overtimeHours: "العمل الإضافي (ساعة)", trend: "الإضافي اليومي وتسجيل الدخول", overtimeShort: "ساعات إضافية", noCheckin: "أيام بلا تسجيل", executive: "مقارنة المديرين الإقليميين", pressure: "المستودعات الأعلى ضغطاً", signals: "إشارات القرار", avoidable: "عمل إضافي رغم كفاية المعيار", manager: "المدير الإقليمي", exec: "التنفيذي الإقليمي", depots: "المستودعات", norm: "المعيار", active: "النشطون", capacity: "التغطية", score: "الضغط", status: "الحالة", total: "الإجمالي", headcount: "القوة", gap: "العجز", anomalies: "11 ساعة", interpretation: "رأي المحلل", healthy: "متوازن", warning: "للمتابعة", criticalRisk: "حرج", criticalText: "يرتفع عجز القوى أو فقدان السجلات أو كثافة الإضافي معاً.", warningText: "عدة مؤشرات تقترب من حدودها.", healthyText: "بيانات الفترة متوازنة مع المعيار وحجم العمل.", empty: "لا توجد بيانات قابلة للتحليل للفترة المحددة.", leakage: "القوة تفي بالمعيار؛ قد ينتج الإضافي عن توزيع الورديات أو تداخل الإجازات أو التخطيط.", readOnly: "لا يمكن تغيير البيانات هنا؛ النتائج محسوبة من الحضور وبيانات الموظفين والإجازات والمعايير.",
  },
};

function hours(minutes) { return Math.round((Number(minutes || 0) / 60) * 10) / 10; }

function Kpi({ icon: Icon, label, value, note, tone = "blue" }) {
  return <article className={`wfx-analytics-kpi ${tone}`}><div><Icon size={19} /></div><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function Risk({ value, t }) {
  const label = value === "critical" ? t.criticalRisk : value === "warning" ? t.warning : t.healthy;
  return <span className={`wfx-analytics-risk ${value}`}>{label}</span>;
}

export default function WorkforceAnalyticsDashboard({ state, attendance, rosterRows, period, setPeriod, locale = "tr", theme = "light" }) {
  const t = COPY[locale] || COPY.tr;
  const analytics = useMemo(() => buildWorkforceAnalytics({ state, attendance, rosterRows, period }), [state, attendance, rosterRows, period]);
  const managers = [...new Set((state.staffingNorms || []).map((row) => row.regionalManager))].filter(Boolean).sort();
  const executives = [...new Set((state.staffingNorms || []).filter((row) => !period.regionalManager || row.regionalManager === period.regionalManager).map((row) => row.regionalExecutive))].filter(Boolean).sort();
  const warehouses = [...new Set((state.staffingNorms || []).filter((row) => (!period.regionalManager || row.regionalManager === period.regionalManager) && (!period.regionalExecutive || row.regionalExecutive === period.regionalExecutive)).map((row) => row.warehouse))].filter(Boolean).sort();
  const topOvertime = [...analytics.warehouses].sort((a, b) => b.overtimeMinutes - a.overtimeMinutes).slice(0, 8).map((row) => ({ name: row.warehouse.replace(/ \(.+\)$/, ""), hours: hours(row.overtimeMinutes) }));
  const trend = analytics.trend.slice(-31).map((row) => ({ ...row, label: row.date.slice(5), hours: hours(row.overtimeMinutes) }));
  const tooltipStyle = { background: theme === "dark" ? "#111827" : "#fff", border: `1px solid ${theme === "dark" ? "#334155" : "#e8eaf0"}`, borderRadius: 12, color: theme === "dark" ? "#f3f6fc" : "#172033", fontSize: 12 };
  const riskText = (risk) => risk === "critical" ? t.criticalText : risk === "warning" ? t.warningText : t.healthyText;

  return <div className="wfx-analytics-dashboard">
    <section className="wfx-panel wfx-analytics-hero">
      <div><span>{t.eyebrow}</span><h2>{t.title}</h2><p>{t.description}</p></div>
      <div className="wfx-analytics-source"><BadgeCheck size={17} /><strong>{analytics.source === "roster" ? t.sourceRoster : t.sourceLive}</strong><small>{analytics.sourceRows.toLocaleString(locale)} {t.rows}</small></div>
    </section>

    <section className="wfx-panel wfx-analytics-filters" aria-label="Analytics filters">
      <label><CalendarRange size={15} />{t.start}<input type="date" value={period.startDate} onChange={(event) => setPeriod({ ...period, startDate: event.target.value })} /></label>
      <label><CalendarRange size={15} />{t.end}<input type="date" value={period.endDate} onChange={(event) => setPeriod({ ...period, endDate: event.target.value })} /></label>
      <label>{t.rm}<select value={period.regionalManager} onChange={(event) => setPeriod({ ...period, regionalManager: event.target.value, regionalExecutive: "", warehouse: "" })}><option value="">{t.all}</option>{managers.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>{t.re}<select value={period.regionalExecutive} onChange={(event) => setPeriod({ ...period, regionalExecutive: event.target.value, warehouse: "" })}><option value="">{t.all}</option>{executives.map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>{t.warehouse}<select value={period.warehouse} onChange={(event) => setPeriod({ ...period, warehouse: event.target.value })}><option value="">{t.allWarehouses}</option>{warehouses.map((value) => <option key={value}>{value}</option>)}</select></label>
    </section>

    <section className="wfx-analytics-kpis">
      <Kpi icon={Clock3} label={t.effective} value={formatMinutes(analytics.totals.totalMinutes)} note={t.periodTotal} tone="blue" />
      <Kpi icon={TrendingUp} label={t.overtime} value={formatMinutes(analytics.totals.overtimeMinutes)} note={`${analytics.totals.overtimeRate}% ${t.overtimeRate.toLocaleLowerCase(locale)}`} tone="purple" />
      <Kpi icon={ScanLine} label={t.checkin} value={`${analytics.totals.checkInRate}%`} note={`${analytics.totals.shiftDays.toLocaleString(locale)} ${t.laborDays}`} tone={analytics.totals.checkInRate < 95 ? "red" : "green"} />
      <Kpi icon={UsersRound} label={t.normGap} value={analytics.totals.normBelow} note={`${analytics.totals.headcount}/${analytics.totals.norm} · ${analytics.totals.capacityRate}%`} tone={analytics.totals.normBelow ? "amber" : "green"} />
      <Kpi icon={AlertTriangle} label={t.critical} value={analytics.totals.critical} note={`${analytics.warehouses.length} ${t.depots.toLocaleLowerCase(locale)}`} tone={analytics.totals.critical ? "red" : "green"} />
    </section>

    {!analytics.warehouses.length ? <section className="wfx-panel wfx-analytics-empty"><Gauge size={34} /><h3>{t.empty}</h3><p>{t.readOnly}</p></section> : <>
      <section className="wfx-analytics-chart-grid">
        <article className="wfx-panel wfx-analytics-chart"><header><div><span>{t.overtime}</span><h3>{t.topOvertime}</h3></div><TrendingUp size={20} /></header><div style={{ height: Math.max(280, topOvertime.length * 42) }}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={topOvertime} layout="vertical" margin={{ top: 8, right: 18, bottom: 8, left: 12 }}><CartesianGrid horizontal={false} stroke="var(--wfx-line)" /><XAxis type="number" tick={{ fill: "var(--wfx-muted)", fontSize: 11 }} axisLine={false} tickLine={false} unit=" sa" /><YAxis type="category" dataKey="name" width={125} tick={{ fill: "var(--wfx-ink)", fontSize: 11, fontWeight: 750 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${value} sa`, t.overtimeHours]} /><Bar dataKey="hours" name={t.overtimeHours} fill="var(--wfx-brand)" radius={[0, 8, 8, 0]} barSize={20} /></ComposedChart></ResponsiveContainer></div></article>
        <article className="wfx-panel wfx-analytics-chart"><header><div><span>{t.checkin}</span><h3>{t.trend}</h3></div><ScanLine size={20} /></header><div className="wfx-analytics-line"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={trend} margin={{ top: 12, right: 10, bottom: 0, left: -12 }}><defs><linearGradient id="wfxOvertimeArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--wfx-purple)" stopOpacity={0.42} /><stop offset="100%" stopColor="var(--wfx-purple)" stopOpacity={0.02} /></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--wfx-line)" /><XAxis dataKey="label" tick={{ fill: "var(--wfx-muted)", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis yAxisId="hours" tick={{ fill: "var(--wfx-muted)", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis yAxisId="missing" orientation="right" tick={{ fill: "var(--wfx-muted)", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} /><Area yAxisId="hours" type="monotone" dataKey="hours" name={t.overtimeShort} stroke="var(--wfx-purple)" fill="url(#wfxOvertimeArea)" strokeWidth={2.5} /><Bar yAxisId="missing" dataKey="noCheckIn" name={t.noCheckin} fill="var(--wfx-amber)" radius={[5, 5, 0, 0]} barSize={8} /></ComposedChart></ResponsiveContainer></div></article>
      </section>

      <section className="wfx-panel wfx-analytics-table-panel"><header><div><span>{t.manager}</span><h3>{t.executive}</h3></div><UsersRound size={20} /></header><div className="wfx-table-wrap"><table className="wfx-table wfx-analytics-table"><thead><tr><th>{t.manager}</th><th>{t.exec}</th><th>{t.depots}</th><th>{t.norm} / {t.active}</th><th>{t.capacity}</th><th>{t.overtime}</th><th>{t.overtimeRate}</th><th>{t.normGap}</th><th>{t.score}</th></tr></thead><tbody>{analytics.executives.slice(0, 20).map((row) => <tr key={`${row.regionalManager}-${row.regionalExecutive}`}><td><strong>{row.regionalManager}</strong></td><td>{row.regionalExecutive}</td><td>{row.warehouses}</td><td>{row.norm} / {row.headcount}</td><td><strong>{row.capacityRate}%</strong></td><td className={row.overtimeMinutes ? "wfx-purple" : ""}>{formatMinutes(row.overtimeMinutes)}</td><td>{row.overtimeRate}%</td><td className={row.normBelow ? "wfx-red" : ""}>{row.normBelow}</td><td><strong>{row.pressureScore}</strong><small>/100</small></td></tr>)}</tbody></table></div></section>

      <section className="wfx-analytics-bottom-grid">
        <article className="wfx-panel wfx-analytics-table-panel"><header><div><span>{t.pressure}</span><h3>{t.pressure}</h3></div><Gauge size={20} /></header><div className="wfx-table-wrap"><table className="wfx-table wfx-analytics-table"><thead><tr><th>{t.warehouse}</th><th>{t.manager}</th><th>{t.norm} / {t.headcount}</th><th>{t.gap}</th><th>{t.checkin}</th><th>{t.overtime}</th><th>{t.anomalies}</th><th>{t.score}</th><th>{t.status}</th></tr></thead><tbody>{analytics.warehouses.slice(0, 12).map((row) => <tr key={row.warehouse}><td><strong>{row.warehouse}</strong><small>{row.regionalExecutive}</small></td><td>{row.regionalManager}</td><td>{row.norm || "—"} / {row.headcount}</td><td className={row.normGap ? "wfx-red" : ""}>{row.normGap || "—"}</td><td>{row.checkInRate}%</td><td className={row.overtimeMinutes ? "wfx-purple" : ""}>{formatMinutes(row.overtimeMinutes)}</td><td>{row.anomalyCount}</td><td><strong>{row.pressureScore}</strong></td><td><Risk value={row.risk} t={t} /><small>{riskText(row.risk)}</small></td></tr>)}</tbody></table></div></article>
        <aside className="wfx-panel wfx-analytics-insights"><header><div><span>{t.interpretation}</span><h3>{t.signals}</h3></div><AlertTriangle size={20} /></header><div>{analytics.insights.map((item) => <article key={item.id} className={item.tone}><strong>{item.value}</strong><span><b>{item.label}</b><small>{item.detail}</small></span></article>)}</div><p><BadgeCheck size={15} />{t.readOnly}</p></aside>
      </section>

      {analytics.avoidable.length ? <section className="wfx-panel wfx-analytics-leakage"><header><div><span>{t.overtimeRate}</span><h3>{t.avoidable}</h3><p>{t.leakage}</p></div><Building2 size={21} /></header><div className="wfx-analytics-leakage-grid">{analytics.avoidable.slice(0, 6).map((row) => <article key={row.warehouse}><strong>{row.warehouse}</strong><small>{row.regionalExecutive}</small><div><span>{row.headcount}/{row.norm} {t.headcount.toLocaleLowerCase(locale)}</span><b>{formatMinutes(row.overtimeMinutes)}</b></div></article>)}</div></section> : null}
    </>}
  </div>;
}
