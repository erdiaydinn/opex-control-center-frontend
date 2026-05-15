import React from "react";
import { Lock, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import DockOSDashboardBase from "./DockOSDashboardBase.jsx";
import DockOSPermissionBanner from "./DockOSPermissionBanner.jsx";
import { getDockOSPermissionClassNames } from "./dockosPermissions.js";
import "./dockos-permissions.css";

export default function DockOSDashboard() {
  const navigate = useNavigate();
  const { can, canFeature } = useAuth();

  if (!can("dockos", "view")) {
    return (
      <main className="dockos-locked-page">
        <section className="dockos-locked-card">
          <div>
            <Lock size={34} />
          </div>

          <h1>DockOS erişimi yok.</h1>
          <p>Bu kullanıcı için DockOS modül erişimi Access Control üzerinden açılmalı.</p>

          <button type="button" onClick={() => navigate("/")}>
            Control Center’a dön
          </button>
        </section>
      </main>
    );
  }

  if (!canFeature("dockos", "dashboard")) {
    return (
      <main className="dockos-locked-page">
        <section className="dockos-locked-card">
          <div>
            <ShieldCheck size={34} />
          </div>

          <h1>DockOS dashboard yetkisi kapalı.</h1>
          <p>Modüle erişimin var ama dashboard ekranı için detay yetkisi verilmemiş.</p>

          <button type="button" onClick={() => navigate("/")}>
            Control Center’a dön
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className={`dockos-permission-shell ${getDockOSPermissionClassNames()}`}>
      <DockOSPermissionBanner />
      <DockOSDashboardBase />
    </main>
  );
}
