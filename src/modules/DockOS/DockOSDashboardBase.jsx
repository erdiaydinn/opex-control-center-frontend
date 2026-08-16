import React, { useEffect, useState } from "react";
import SupplierReservation from "./SupplierReservation";
import AdminReservations from "./AdminReservations";
import KpiSummary from "./KpiSummary";
import { getPurchaseOrders, getReservations, getSlots, healthCheck } from "./dockosApi";
import { canDockOSAction, canDockOSFeature } from "./dockosPermissions";
import { useDockOSUi } from "./DockOSUiContext";

function StatCard({ label, value }) {
  return (
    <div style={styles.statCard}>
      <div style={styles.statLabel}>{label}</div>
      <div style={styles.statValue}>{value}</div>
    </div>
  );
}

export default function DockOSDashboardBase() {
  const { t, theme, setTheme, locale, setLocale } = useDockOSUi();
  // Phase 1 fail-closed authorization:
  // only screens backed by explicit catalogued DB
  // permissions may enter the navigation.
  //
  // planning / capacity / audit / notifications /
  // access remain quarantined until dedicated DB
  // permissions AND backend enforcement exist.
  const tabs = [];

  if (
    canDockOSFeature("supplierAppointments") &&
    canDockOSAction("create")
  ) {
    tabs.push({
      key: "supplier",
      label: t("supplier"),
      icon: "?",
    });
  }

  if (
    canDockOSFeature("vehicleTracking") &&
    canDockOSAction("edit")
  ) {
    tabs.push({
      key: "admin",
      label: t("admin"),
      icon: "?",
    });
  }

  if (canDockOSFeature("dashboard")) {
    tabs.push({
      key: "kpi",
      label: t("kpi"),
      icon: "?",
    });
  }

  const [activeTab, setActiveTab] = useState(tabs[0]?.key || "kpi");
  const [apiStatus, setApiStatus] = useState("checking");
  const [stats, setStats] = useState(null);

  async function loadStats() {
    setApiStatus("checking");
    setStats(null);

    try {
      await healthCheck();

      const [pos, reservations, slots] = await Promise.all([
        getPurchaseOrders(),
        getReservations(),
        getSlots(),
      ]);

      const activeReservations = reservations.filter((row) => row.status !== "CANCELLED");
      const usages = slots
        .filter((slot) => Number(slot.max_pallet) > 0)
        .map((slot) => {
          const used = Number(slot.max_pallet) - Number(slot.remaining_pallet);
          return Math.round((used / Number(slot.max_pallet)) * 100);
        });

      setStats({
        poCount: pos.length,
        reservationCount: reservations.length,
        activeReservationCount: activeReservations.length,
        avgCapacityUsage: usages.length
          ? Math.round(usages.reduce((sum, value) => sum + value, 0) / usages.length)
          : 0,
      });

      setApiStatus("online");
    } catch {
      // Never surface transport/backend exception text in the product UI.
      // The user-facing message stays localized and stable.
      setStats(null);
      setApiStatus("offline");
    }
  }

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    if (!tabs.some((tab) => tab.key === activeTab)) {
      setActiveTab(tabs[0]?.key || "kpi");
    }
  }, [tabs, activeTab]);

  const productState =
    apiStatus === "checking"
      ? "loading"
      : apiStatus === "offline"
        ? "error"
        : "ready";

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

        <nav style={styles.nav}>
          <span style={styles.navLabel}>{t("workspace")}</span>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              style={{
                ...styles.navButton,
                ...(activeTab === tab.key ? styles.navButtonActive : {}),
              }}
            >
              <span style={styles.navIcon}>{tab.icon}</span><span>{tab.label}</span>
            </button>
          ))}
        </nav>

        <div style={styles.preferences}>
          <span style={styles.navLabel}>{t("appearance")}</span>
          <button type="button" onClick={() => setTheme(theme === "light" ? "dark" : "light")} style={styles.preferenceButton}><span>{theme === "light" ? "☾" : "☀"}</span><b>{theme === "light" ? t("dark") : t("light")}</b></button>
          <label style={styles.languageField}><span>{t("language")}</span><select value={locale} onChange={(event) => setLocale(event.target.value)}><option value="tr">Türkçe</option><option value="en">English</option><option value="de">Deutsch</option><option value="ar">العربية</option></select></label>
        </div>

        <div
          style={styles.apiCard}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <span style={{
            ...styles.apiDot,
            background:
              apiStatus === "online"
                ? "#12b76a"
                : apiStatus === "offline"
                  ? "#f04438"
                  : "#f79009",
          }} />
          <div>
            <strong>
              {apiStatus === "online"
                ? t("connected")
                : apiStatus === "offline"
                  ? t("disconnected")
                  : t("checking")}
            </strong>
            <small>Gateway API</small>
          </div>
        </div>
      </aside>

      <main
        style={styles.main}
        aria-busy={apiStatus === "checking"}
        data-eay-product-state={productState}
      >
        <section style={styles.topbar}>
          <div>
            <p style={styles.kicker}>OPEX Control Center</p>
            <h1 style={styles.title}>DockOS</h1>
            <p style={styles.subtitle}>Inbound Intelligence & Dock Scheduling Platform</p>
          </div>
          <button
            type="button"
            onClick={loadStats}
            style={styles.refreshButton}
            disabled={apiStatus === "checking"}
          >
            {t("refresh")}
          </button>
        </section>

        {apiStatus === "checking" && (
          <section
            style={styles.statePanel}
            role="status"
            aria-live="polite"
            aria-atomic="true"
            data-eay-product-state="loading"
          >
            <strong>{t("checking")}</strong>
          </section>
        )}

        {apiStatus === "offline" && (
          <section
            style={styles.errorPanel}
            role="alert"
            data-eay-product-state="error"
          >
            <strong>{t("backendFailed")}</strong>
            <button type="button" onClick={loadStats} style={styles.retryButton}>
              {t("refresh")}
            </button>
          </section>
        )}

        {apiStatus === "online" && stats && (
          <>
            <section style={styles.statsGrid} data-eay-product-state="ready">
              <StatCard label={t("openPo")} value={stats.poCount} />
              <StatCard label={t("totalReservation")} value={stats.reservationCount} />
              <StatCard label={t("activeReservation")} value={stats.activeReservationCount} />
              <StatCard label={t("avgCapacity")} value={`%${stats.avgCapacityUsage}`} />
            </section>

            {activeTab === "supplier" && <SupplierReservation />}
            {activeTab === "admin" && <AdminReservations />}
            {activeTab === "kpi" && <KpiSummary />}
          </>
        )}
      </main>
    </div>
  );
}

const styles = {
  shell: {
    display: "flex",
    alignItems: "stretch",
    minHeight: "100vh",
    background: "var(--dockos-bg)",
    color: "var(--dockos-text)",
    fontFamily: "Inter, Arial, sans-serif",
  },
  sidebar: {
    position: "sticky",
    top: 0,
    alignSelf: "flex-start",
    width: 260,
    minWidth: 260,
    height: "100vh",
    boxSizing: "border-box",
    background: "var(--dockos-sidebar)",
    color: "#ffffff",
    padding: "20px 14px",
    display: "flex",
    flexDirection: "column",
  },
  logoBox: {
    display: "flex",
    alignItems: "center",
    gap: 11,
    padding: "0 4px",
    marginBottom: 26,
  },
  logo: {
    width: 40,
    height: 40,
    flex: "0 0 40px",
    borderRadius: 14,
    background: "#e5005a",
    display: "grid",
    placeItems: "center",
    color: "#ffffff",
    fontWeight: 900,
    fontSize: 20,
  },
  logoTitle: { color: "#ffffff", fontWeight: 900, fontSize: 17, lineHeight: 1.1 },
  logoSub: { marginTop: 3, color: "#98a2b3", fontSize: 10 },
  nav: { display: "grid", gap: 8 },
  navLabel: { padding: "0 8px", color: "#667085", fontSize: 10, fontWeight: 900, letterSpacing: ".08em", textTransform: "uppercase" },
  navIcon: { display: "grid", placeItems: "center", width: 28, height: 28, borderRadius: 9, background: "rgba(255,255,255,.08)", fontSize: 15 },
  navButton: {
    width: "100%",
    minHeight: 48,
    boxSizing: "border-box",
    border: "1px solid rgba(255,255,255,.11)",
    background: "rgba(255,255,255,.035)",
    color: "#ffffff",
    borderRadius: 14,
    padding: "11px 14px",
    textAlign: "start",
    display: "grid",
    gridTemplateColumns: "28px 1fr",
    alignItems: "center",
    gap: 10,
    lineHeight: 1.25,
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 800,
  },
  navButtonActive: {
    border: "1px solid #e5005a",
    background: "#e5005a",
    color: "#ffffff",
    boxShadow: "0 10px 22px rgba(229,0,90,.24)",
  },
  preferences: { display: "grid", gap: 8, marginTop: "auto", paddingTop: 20 },
  preferenceButton: { display: "grid", gridTemplateColumns: "28px 1fr", alignItems: "center", gap: 9, minHeight: 42, padding: "7px 10px", border: "1px solid rgba(255,255,255,.12)", borderRadius: 12, color: "#fff", background: "rgba(255,255,255,.04)", textAlign: "start", cursor: "pointer" },
  languageField: { display: "grid", gap: 5, padding: "10px", border: "1px solid rgba(255,255,255,.12)", borderRadius: 12, color: "#98a2b3", fontSize: 11 },
  apiCard: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginTop: 12,
    padding: 12,
    border: "1px solid rgba(255,255,255,.1)",
    borderRadius: 14,
    background: "rgba(255,255,255,.04)",
  },
  apiDot: { width: 9, height: 9, borderRadius: "50%" },
  main: { flex: 1, minWidth: 0, padding: 22, overflow: "visible" },
  topbar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 22,
    background: "var(--dockos-surface)",
    border: "1px solid var(--dockos-border)",
    borderRadius: 20,
    marginBottom: 14,
  },
  kicker: { margin: 0, color: "#e5005a", fontWeight: 900 },
  title: { margin: "5px 0 0", color: "var(--dockos-text)", fontSize: 30 },
  subtitle: { margin: "6px 0 0", color: "var(--dockos-muted)" },
  refreshButton: {
    border: 0,
    borderRadius: 13,
    padding: "11px 15px",
    background: "#101828",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
  },
  retryButton: {
    justifySelf: "start",
    border: 0,
    borderRadius: 11,
    padding: "9px 12px",
    background: "#b42318",
    color: "#ffffff",
    fontWeight: 800,
    cursor: "pointer",
  },
  statePanel: {
    display: "grid",
    gap: 4,
    marginBottom: 14,
    padding: 14,
    border: "1px solid var(--dockos-border)",
    borderRadius: 14,
    color: "var(--dockos-text)",
    background: "var(--dockos-surface)",
  },
  errorPanel: {
    display: "grid",
    gap: 10,
    marginBottom: 14,
    padding: 14,
    border: "1px solid #fecdca",
    borderRadius: 14,
    color: "#b42318",
    background: "#fef3f2",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: 12,
    marginBottom: 16,
  },
  statCard: {
    background: "var(--dockos-surface)",
    border: "1px solid var(--dockos-border)",
    borderRadius: 17,
    padding: 16,
  },
  statLabel: { color: "var(--dockos-muted)", fontWeight: 800, fontSize: 12 },
  statValue: { marginTop: 7, color: "var(--dockos-text)", fontSize: 28, fontWeight: 900 },
};
