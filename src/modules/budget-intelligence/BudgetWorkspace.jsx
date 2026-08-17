import React, { useState } from "react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import BudgetIntelligence from "./BudgetIntelligence.jsx";
import BudgetPlanningWorkspace from "./BudgetPlanningWorkspace.jsx";
import "./budget-workspace.css";

export default function BudgetWorkspace() {
  const { t } = usePlatformPreferences();
  const [view, setView] = useState("planning");

  return (
    <div>
      <nav className="budget-workspace-switcher" role="tablist" aria-label={t("budgetPlanning")}>
        <button
          type="button"
          role="tab"
          aria-selected={view === "planning"}
          onClick={() => setView("planning")}
        >
          {t("budgetPlanningView")}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "operational"}
          onClick={() => setView("operational")}
        >
          {t("budgetOperationalView")}
        </button>
      </nav>
      {view === "planning" ? <BudgetPlanningWorkspace /> : <BudgetIntelligence />}
    </div>
  );
}
