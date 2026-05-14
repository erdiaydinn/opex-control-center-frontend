import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Portal from "./pages/Portal.jsx";
import PlanogramStudio from "./modules/planogram/PlanogramStudio.jsx";
import BudgetIntelligence from "./modules/budget-intelligence/BudgetIntelligence.jsx";
import DockOSDashboard from "./modules/DockOS/DockOSDashboard.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Portal />} />
      <Route path="/planogram" element={<PlanogramStudio />} />
      <Route path="/budget" element={<BudgetIntelligence />} />
      <Route path="/dockos" element={<DockOSDashboard />} />
      <Route path="/river" element={<Navigate to="/dockos" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}