import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Login from "./pages/Login.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";
import ControlCenterHome from "./modules/control-center/ControlCenterHome.jsx";
import PlanogramStudio from "./modules/planogram/PlanogramStudio.jsx";
import BudgetIntelligence from "./modules/budget-intelligence/BudgetIntelligence.jsx";
import DockOSDashboard from "./modules/DockOS/DockOSDashboard.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <ControlCenterHome />
          </ProtectedRoute>
        }
      />

      <Route
        path="/planogram"
        element={
          <ProtectedRoute moduleKey="planogram">
            <PlanogramStudio />
          </ProtectedRoute>
        }
      />

      <Route
        path="/budget"
        element={
          <ProtectedRoute moduleKey="budget">
            <BudgetIntelligence />
          </ProtectedRoute>
        }
      />

      <Route
        path="/dockos"
        element={
          <ProtectedRoute moduleKey="dockos">
            <DockOSDashboard />
          </ProtectedRoute>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
