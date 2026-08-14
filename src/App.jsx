import React from "react";
import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import Login from "./pages/Login.jsx";
import AuthCallback from "./auth/AuthCallback.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";

import ControlCenterHome from "./modules/control-center/ControlCenterHome.jsx";
import PlanogramStudio from "./modules/planogram/PlanogramStudio.jsx";
import BudgetIntelligence from "./modules/budget-intelligence/BudgetIntelligence.jsx";
import DockOSDashboard from "./modules/DockOS/DockOSDashboard.jsx";
import AccessControl from "./modules/access-control/AccessControl.jsx";
import ServerAccounts from "./modules/access-control/ServerAccounts.jsx";
import InventoryDashboard from "./modules/inventory/InventoryDashboard.jsx";
import { InventoryUiProvider } from "./modules/inventory/InventoryUiContext.jsx";
import WorkforceControl from "./modules/workforce/WorkforceControl.jsx";
import WorkforcePickerApp from "./modules/workforce/WorkforcePickerApp.jsx";
import { WorkforceUiProvider } from "./modules/workforce/WorkforceUiContext.jsx";
import RecruitmentControl from "./modules/recruitment/RecruitmentControl.jsx";
import PlatformHealth from "./modules/platform-health/PlatformHealth.jsx";
import AuditLog from "./modules/audit-log/AuditLog.jsx";


const PLATFORM_ADMIN_ROLES = [
  "platform_admin",
  "super_admin",
];


export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={<Login />}
      />

      <Route
        path="/auth/callback"
        element={<AuthCallback />}
      />

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
        path="/dockos"
        element={
          <ProtectedRoute moduleKey="dockos">
            <DockOSDashboard />
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
        path="/inventory"
        element={
          <ProtectedRoute moduleKey="inventory">
            <InventoryUiProvider>
              <InventoryDashboard />
            </InventoryUiProvider>
          </ProtectedRoute>
        }
      />

      <Route
        path="/inventory/access-management"
        element={
          <ProtectedRoute
            moduleKey="inventory"
            action="admin"
          >
            <ServerAccounts />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/accounts"
        element={
          <Navigate
            to="/inventory/access-management"
            replace
          />
        }
      />

      <Route
        path="/workforce"
        element={
          <ProtectedRoute moduleKey="workforce">
            <WorkforceUiProvider>
              <WorkforceControl />
            </WorkforceUiProvider>
          </ProtectedRoute>
        }
      />

      <Route
        path="/workforce/app"
        element={
          <ProtectedRoute moduleKey="workforce">
            <WorkforceUiProvider>
              <WorkforcePickerApp />
            </WorkforceUiProvider>
          </ProtectedRoute>
        }
      />

      <Route
        path="/recruitment"
        element={
          <ProtectedRoute moduleKey="recruitment">
            <RecruitmentControl />
          </ProtectedRoute>
        }
      />

      <Route
        path="/access-control"
        element={
          <ProtectedRoute
            moduleKey="admin_access"
            action="admin"
          >
            <AccessControl />
          </ProtectedRoute>
        }
      />

      <Route
        path="/audit-log"
        element={
          <ProtectedRoute
            roles={PLATFORM_ADMIN_ROLES}
          >
            <AuditLog />
          </ProtectedRoute>
        }
      />

      <Route
        path="/platform-health"
        element={
          <ProtectedRoute
            roles={PLATFORM_ADMIN_ROLES}
          >
            <PlatformHealth />
          </ProtectedRoute>
        }
      />

      <Route
        path="/river"
        element={
          <Navigate
            to="/dockos"
            replace
          />
        }
      />

      <Route
        path="*"
        element={
          <Navigate
            to="/"
            replace
          />
        }
      />
    </Routes>
  );
}
