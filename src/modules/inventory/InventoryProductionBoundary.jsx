import React from "react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import InventoryDashboard from "./InventoryDashboard.jsx";

/**
 * The current web InventoryDashboard is a local pilot surface. The authoritative
 * production Inventory execution path lives in the backend/PostgreSQL contract
 * and managed Android terminal. Never let local demo state impersonate that
 * production truth boundary.
 */
export default function InventoryProductionBoundary() {
  const { t } = usePlatformPreferences();

  if (import.meta.env.DEV) {
    return <InventoryDashboard />;
  }

  return (
    <section
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
      data-eay-product-state="error"
      data-inventory-authority="production-backend-native-terminal"
    >
      <h1>{t("errorTitle")}</h1>
      <p>{t("emptyTitle")}</p>
    </section>
  );
}
