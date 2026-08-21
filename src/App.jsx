import React, { Suspense, lazy } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import Login from "./pages/Login.jsx";
import AuthCallback from "./auth/AuthCallback.jsx";
import ControlPlaneRoute from "./auth/ControlPlaneRoute.jsx";
import ProtectedRoute from "./auth/ProtectedRoute.jsx";

import ControlCenterHome from "./modules/control-center/ControlCenterHome.jsx";
import { InventoryUiProvider } from "./modules/inventory/InventoryUiContext.jsx";
import { WorkforceUiProvider } from "./modules/workforce/WorkforceUiContext.jsx";
import RouteErrorBoundary from "./platform/accessibility/RouteErrorBoundary.jsx";
import { usePlatformPreferences } from "./platform/preferences/PlatformPreferencesContext.jsx";

const PlanogramStudio = lazy(() => import("./modules/planogram/PlanogramStudio.jsx"));
const BudgetIntelligence = lazy(() => import("./modules/budget-intelligence/BudgetIntelligence.jsx"));
const DockOSDashboard = lazy(() => import("./modules/DockOS/DockOSDashboard.jsx"));
const AccessControl = lazy(() => import("./modules/access-control/AccessControl.jsx"));
const ServerAccounts = lazy(() => import("./modules/access-control/ServerAccounts.jsx"));
const InventoryProductionBoundary = lazy(() => import("./modules/inventory/InventoryProductionBoundary.jsx"));
const WorkforceBootstrapBoundary = lazy(() => import("./modules/workforce/WorkforceBootstrapBoundary.jsx"));
const WorkforcePickerApp = lazy(() => import("./modules/workforce/WorkforcePickerApp.jsx"));
const RecruitmentBootstrapBoundary = lazy(() => import("./modules/recruitment/RecruitmentBootstrapBoundary.jsx"));
const RecruitmentOnboardingTasks = lazy(() => import("./modules/recruitment/RecruitmentOnboardingTasks.jsx"));
const OnboardingTaskLauncher = lazy(() => import("./modules/recruitment/OnboardingTaskLauncher.jsx"));
const CandidateDocumentPortal = lazy(() => import("./modules/recruitment/CandidateDocumentPortal.jsx"));
const CandidateOfferPortal = lazy(() => import("./modules/recruitment/CandidateOfferPortal.jsx"));
const CandidateInterviewPortal = lazy(() => import("./modules/recruitment/CandidateInterviewPortal.jsx"));
const AcademyWorkspace = lazy(() => import("./modules/academy/AcademyWorkspace.jsx"));
const AcademyPlayer = lazy(() => import("./modules/academy/AcademyPlayer.jsx"));
const AcademyExpansionHub = lazy(() => import("./modules/academy/AcademyExpansionHub.jsx"));
const JarvisWorkspace = lazy(() => import("./modules/intelligence/JarvisWorkspace.jsx"));
const InsightWorkspace = lazy(() => import("./modules/intelligence/InsightWorkspace.jsx"));
const FieldIntelligenceWorkspace = lazy(() => import("./modules/field-intelligence/FieldIntelligenceWorkspace.jsx"));
const FieldMobileCapture = lazy(() => import("./modules/field-intelligence/FieldMobileCapture.jsx"));
const FieldGovernanceWorkspace = lazy(() => import("./modules/field-intelligence/FieldGovernanceWorkspace.jsx"));
const AuditCommandCenter = lazy(() => import("./modules/audit/AuditCommandCenter.jsx"));
const PlatformHealth = lazy(() => import("./modules/platform-health/PlatformHealth.jsx"));
const AuditLog = lazy(() => import("./modules/audit-log/AuditLog.jsx"));

const PLATFORM_ADMIN_ROLES = [
  "platform_admin",
  "super_admin",
];

function RouteLoadingFallback() {
  const { t } = usePlatformPreferences();

  return (
    <div role="status" aria-live="polite" aria-busy="true" data-eay-product-state="loading">
      {t("loading")}
    </div>
  );
}

export default function App() {
  const location = useLocation();

  return (
    <RouteErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<RouteLoadingFallback />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          {/* Candidate capability portals stay outside employee SSO. Secrets live in URL fragments,
              are immediately removed from the address bar and public API calls attach no employee token. */}
          <Route path="/candidate/documents" element={<CandidateDocumentPortal />} />
          <Route path="/candidate/offer" element={<CandidateOfferPortal />} />
          <Route path="/candidate/interview" element={<CandidateInterviewPortal />} />
          <Route path="/" element={<ProtectedRoute><React.Fragment><ControlCenterHome /><OnboardingTaskLauncher /></React.Fragment></ProtectedRoute>} />
          <Route path="/planogram" element={<ProtectedRoute moduleKey="planogram"><PlanogramStudio /></ProtectedRoute>} />
          <Route path="/dockos" element={<ProtectedRoute moduleKey="dockos"><DockOSDashboard /></ProtectedRoute>} />
          <Route path="/budget" element={<ProtectedRoute moduleKey="budget"><BudgetIntelligence /></ProtectedRoute>} />
          <Route path="/academy" element={<ProtectedRoute moduleKey="academy"><AcademyWorkspace /></ProtectedRoute>} />
          <Route path="/academy/experience" element={<ProtectedRoute moduleKey="academy"><AcademyExpansionHub /></ProtectedRoute>} />
          <Route path="/academy/enrollments/:enrollmentId" element={<ProtectedRoute moduleKey="academy"><AcademyPlayer /></ProtectedRoute>} />
          <Route path="/jarvis" element={<ProtectedRoute moduleKey="jarvis"><JarvisWorkspace /></ProtectedRoute>} />
          <Route path="/insight" element={<ProtectedRoute moduleKey="insight"><InsightWorkspace /></ProtectedRoute>} />
          <Route path="/field-intelligence" element={<ProtectedRoute moduleKey="field_intelligence"><FieldIntelligenceWorkspace /></ProtectedRoute>} />
          <Route path="/field-intelligence/mobile" element={<ProtectedRoute moduleKey="field_intelligence"><FieldMobileCapture /></ProtectedRoute>} />
          <Route path="/field-intelligence/governance" element={<ProtectedRoute moduleKey="field_intelligence"><FieldGovernanceWorkspace /></ProtectedRoute>} />
          <Route path="/audit" element={<ProtectedRoute moduleKey="audit"><AuditCommandCenter /></ProtectedRoute>} />
          <Route path="/inventory" element={<ProtectedRoute moduleKey="inventory"><InventoryUiProvider><InventoryProductionBoundary /></InventoryUiProvider></ProtectedRoute>} />
          <Route path="/inventory/access-management" element={<ProtectedRoute moduleKey="admin_access" action="admin"><ServerAccounts /></ProtectedRoute>} />
          <Route path="/admin/accounts" element={<Navigate to="/inventory/access-management" replace />} />
          <Route path="/workforce" element={<ProtectedRoute moduleKey="workforce"><WorkforceUiProvider><WorkforceBootstrapBoundary /></WorkforceUiProvider></ProtectedRoute>} />
          <Route path="/workforce/app" element={<ProtectedRoute moduleKey="workforce"><WorkforceUiProvider><WorkforcePickerApp /></WorkforceUiProvider></ProtectedRoute>} />
          <Route path="/recruitment" element={<ProtectedRoute moduleKey="recruitment"><RecruitmentBootstrapBoundary /></ProtectedRoute>} />
          {/* Cross-functional tasks are not tied to Recruitment module visibility; the backend
              returns only the signed user's owner-role + warehouse-scoped task projection. */}
          <Route path="/onboarding/tasks" element={<ProtectedRoute><RecruitmentOnboardingTasks /></ProtectedRoute>} />
          <Route path="/access-control" element={<ProtectedRoute moduleKey="admin_access" action="admin"><AccessControl /></ProtectedRoute>} />
          <Route path="/audit-log" element={<ProtectedRoute roles={PLATFORM_ADMIN_ROLES}><AuditLog /></ProtectedRoute>} />
          <Route path="/platform-health" element={<ProtectedRoute roles={PLATFORM_ADMIN_ROLES}><ControlPlaneRoute><PlatformHealth /></ControlPlaneRoute></ProtectedRoute>} />
          <Route path="/river" element={<Navigate to="/dockos" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </RouteErrorBoundary>
  );
}
