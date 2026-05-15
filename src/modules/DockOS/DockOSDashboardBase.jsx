import React, { useEffect, useState } from "react";
import SupplierReservation from "./SupplierReservation";
import AdminReservations from "./AdminReservations";
import CapacityManagement from "./CapacityManagement";
import KpiSummary from "./KpiSummary";
import { getPurchaseOrders, getReservations, getSlots } from "./dockosApi";

function StatCard({ label, value }) {
  return (
    <div style={styles.statCard}>
      <div style={styles.statLabel}>{label}</div>
      <div style={styles.statValue}>{value}</div>
    </div>
  );
}

export default function DockOSDashboard() {
  const [activeTab, setActiveTab] = useState("supplier");
  const [stats, setStats] = useState({
    poCount: 0,
    reservationCount: 0,
    activeReservationCount: 0,
    avgCapacityUsage: 0,
  });

  async function loadStats() {
    try {
      const [pos, reservations, slots] = await Promise.all([
        getPurchaseOrders(),
        getReservations(),
        getSlots(),
      ]);

      const activeReservations = reservations.filter((r) => r.status !== "CANCELLED");

      const usages = slots.map((s) => {
        const used = s.max_pallet - s.remaining_pallet;
        return Math.round((used / s.max_pallet) * 100);
      });

      const avgUsage =
        usages.length > 0
          ? Math.round(usages.reduce((a, b) => a + b, 0) / usages.length)
          : 0;

      setStats({
        poCount: pos.length,
        reservationCount: reservations.length,
        activeReservationCount: activeReservations.length,
        avgCapacityUsage: avgUsage,
      });
    } catch {
      setStats({
        poCount: 0,
        reservationCount: 0,
        activeReservationCount: 0,
        avgCapacityUsage: 0,
      });
    }
  }

  useEffect(() => {
    loadStats();
  }, []);

  return (
    <div style={styles.shell}>
      <aside style={styles.sidebar}>
        <div style={styles.logoBox}>
          <div style={styles.logo}>D</div>
          <div>
            <div style={styles.logoTitle}>DockOS</div>
            <div style={styles.logoSub}>Inbound Intelligence</div>
          </div>
        </div>

        <button onClick={() => setActiveTab("supplier")} style={{ ...styles.navButton, ...(activeTab === "supplier" ? styles.navButtonActive : {}) }}>
          Tedarikçi Portalı
        </button>

        <button onClick={() => setActiveTab("admin")} style={{ ...styles.navButton, ...(activeTab === "admin" ? styles.navButtonActive : {}) }}>
          Admin Rezervasyon
        </button>

        <button onClick={() => setActiveTab("capacity")} style={{ ...styles.navButton, ...(activeTab === "capacity" ? styles.navButtonActive : {}) }}>
          Kapasite Yönetimi
        </button>

        <button onClick={() => setActiveTab("kpi")} style={{ ...styles.navButton, ...(activeTab === "kpi" ? styles.navButtonActive : {}) }}>
          KPI Özeti
        </button>
      </aside>

      <main style={styles.main}>
        <section style={styles.topbar}>
          <div>
            <p style={styles.kicker}>OPEX Control Center</p>
            <h1 style={styles.title}>DockOS</h1>
            <p style={styles.subtitle}>Inbound Intelligence & Dock Scheduling Platform</p>
          </div>
          <button onClick={loadStats} style={styles.refreshButton}>Verileri Yenile</button>
        </section>

        <section style={styles.statsGrid}>
          <StatCard label="Açık PO" value={stats.poCount} />
          <StatCard label="Toplam Rezervasyon" value={stats.reservationCount} />
          <StatCard label="Aktif Rezervasyon" value={stats.activeReservationCount} />
          <StatCard label="Ortalama Kapasite" value={`%${stats.avgCapacityUsage}`} />
        </section>

        {activeTab === "supplier" && <SupplierReservation />}
        {activeTab === "admin" && <AdminReservations />}
        {activeTab === "capacity" && <CapacityManagement />}
        {activeTab === "kpi" && <KpiSummary />}
      </main>
    </div>
  );
}

const styles = {
  shell: { display: "flex", minHeight: "100vh", background: "#f7f8fb", color: "#111827", fontFamily: "Inter, Arial, sans-serif" },
  sidebar: { width: 260, background: "#111827", color: "white", padding: 20, display: "flex", flexDirection: "column", gap: 12 },
  logoBox: { display: "flex", alignItems: "center", gap: 12, marginBottom: 22 },
  logo: { width: 44, height: 44, borderRadius: 16, background: "#DF1067", display: "grid", placeItems: "center", fontWeight: 900, fontSize: 22 },
  logoTitle: { fontWeight: 900, fontSize: 18 },
  logoSub: { color: "#9ca3af", fontSize: 12 },
  navButton: { border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)", color: "#d1d5db", borderRadius: 16, padding: "13px 14px", textAlign: "left", cursor: "pointer", fontWeight: 800 },
  navButtonActive: { background: "#DF1067", color: "white" },
  main: { flex: 1, padding: 24, overflow: "auto" },
  topbar: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: 24, background: "white", borderRadius: 24, marginBottom: 18 },
  kicker: { margin: 0, color: "#DF1067", fontWeight: 900 },
  title: { margin: "6px 0 0", fontSize: 32 },
  subtitle: { margin: "6px 0 0", color: "#6b7280" },
  refreshButton: { border: "none", borderRadius: 14, padding: "12px 16px", background: "#111827", color: "white", fontWeight: 800, cursor: "pointer" },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 18 },
  statCard: { background: "white", borderRadius: 20, padding: 18 },
  statLabel: { color: "#6b7280", fontWeight: 800, fontSize: 13 },
  statValue: { marginTop: 8, fontSize: 30, fontWeight: 900 },
};