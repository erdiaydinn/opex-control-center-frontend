import React from "react";

export default function KpiSummary() {
  return (
    <div style={styles.page}>
      <section style={styles.hero}>
        <p style={styles.kicker}>DockOS · KPI</p>
        <h1 style={styles.title}>Tedarikçi Performans Özeti</h1>
        <p style={styles.subtitle}>
          İptal oranı, no-show, geç geliş, slot değiştirme sıklığı ve merkez depo performansı burada takip edilecek.
        </p>
      </section>

      <div style={styles.grid}>
        <KpiCard title="İptal Oranı" value="%0" />
        <KpiCard title="No-show" value="0" />
        <KpiCard title="Geç Geliş" value="0" />
        <KpiCard title="Slot Değişimi" value="0" />
      </div>
    </div>
  );
}

function KpiCard({ title, value }) {
  return (
    <section style={styles.card}>
      <p style={styles.cardTitle}>{title}</p>
      <strong style={styles.value}>{value}</strong>
    </section>
  );
}

const styles = {
  page: { padding: 24, background: "#f7f8fb", color: "#111827" },
  hero: {
    background: "white",
    borderRadius: 24,
    padding: 24,
    marginBottom: 18,
    border: "1px solid #e5e7eb",
  },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "8px 0", fontSize: 28 },
  subtitle: { margin: 0, color: "#6b7280" },
  grid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 },
  card: {
    background: "white",
    borderRadius: 22,
    padding: 20,
    border: "1px solid #e5e7eb",
  },
  cardTitle: { color: "#6b7280", fontWeight: 800 },
  value: { display: "block", marginTop: 10, fontSize: 34 },
};