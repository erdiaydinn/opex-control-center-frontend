import React from "react";
import { MapPin, ShieldCheck, UserRound } from "lucide-react";
import { useAuth } from "../../auth/AuthContext.jsx";
import { getDockOSPermissionSnapshot } from "./dockosPermissions.js";
import { useDockOSUi } from "./DockOSUiContext.jsx";
import "./dockos-permissions.css";

function scopeText(scope, t) {
  if (!scope || scope.type === "all") return t("allTurkey");
  if (scope.type === "warehouse") return (scope.warehouses || []).join(", ") || t("warehouseMissing");
  if (scope.type === "supplier") return (scope.suppliers || []).join(", ") || t("supplierMissing");
  if (scope.type === "region") return (scope.regions || []).join(", ") || t("regionMissing");
  return t("noScope");
}

export default function DockOSPermissionBanner() {
  const { user } = useAuth();
  const { t } = useDockOSUi();
  const snapshot = getDockOSPermissionSnapshot();

  const enabledFeatureCount = Object.values(snapshot.features || {}).filter(Boolean).length;
  const enabledActionCount = Object.values(snapshot.actions || {}).filter(Boolean).length;

  return (
    <section className="dockos-permission-banner">
      <div className="dockos-permission-main">
        <div className="dockos-permission-icon">
          <ShieldCheck size={20} />
        </div>
        <div>
          <span>{t("accessProfile")}</span>
          <strong>{user?.email || snapshot.user?.email || t("userMissing")}</strong>
          <p>{enabledFeatureCount} {t("screens")} ? {enabledActionCount} {t("actions")}</p>
        </div>
      </div>

      <div className="dockos-permission-summary">
        <div>
          <UserRound size={15} />
          <span>{t("permission")}</span>
          <strong>{enabledFeatureCount} {t("screens")} · {enabledActionCount} {t("actions")}</strong>
        </div>
        <div>
          <MapPin size={15} />
          <span>{t("dataScope")}</span>
          <strong>{scopeText(snapshot.scope, t)}</strong>
        </div>
      </div>
    </section>
  );
}
