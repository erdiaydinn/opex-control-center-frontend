import React from "react";
import { Lock } from "lucide-react";
import { useNavigate } from "react-router-dom";
import DockOSDashboardBase from "./DockOSDashboardBase.jsx";
import DockOSExecutiveControlTower from "./DockOSExecutiveControlTower.jsx";
import DockOSPermissionBanner from "./DockOSPermissionBanner.jsx";
import { DockOSUiProvider, useDockOSUi } from "./DockOSUiContext.jsx";
import {
  canDockOSAction,
  canDockOSFeature,
  getDockOSPermissionClassNames,
} from "./dockosPermissions.js";
import "./dockos-permissions.css";

export default function DockOSDashboard() {
  return <DockOSUiProvider><DockOSGate /></DockOSUiProvider>;
}

function DockOSGate() {
  const navigate = useNavigate();
  const { t, theme, dir } = useDockOSUi();
  const canView = canDockOSAction("view") && canDockOSFeature("dashboard");

  if (!canView) {
    return (
      <main dir={dir} className={`dockos-locked-page dockos-theme-${theme}`}>
        <section className="dockos-locked-card">
          <div><Lock size={34} /></div>
          <h1>{t("noAccess")}</h1>
          <p>{t("accessHelp")}</p>
          <button type="button" onClick={() => navigate("/")}>{t("backControl")}</button>
        </section>
      </main>
    );
  }

  return <DockOSExperience />;
}

function DockOSExperience() {
  const { theme, dir } = useDockOSUi();
  return (
    <div dir={dir} className={`dockos-permission-shell dockos-theme-${theme} ${getDockOSPermissionClassNames()}`}>
      <DockOSPermissionBanner />
      <DockOSExecutiveControlTower />
      <DockOSDashboardBase />
    </div>
  );
}
