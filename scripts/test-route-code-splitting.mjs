import fs from "node:fs";
import process from "node:process";

const appPath = "src/App.jsx";
const source = fs.readFileSync(appPath, "utf8");

function fail(message) {
  console.error(`Route code-splitting contract: FAIL — ${message}`);
  process.exit(1);
}

const lazyRoutes = new Map([
  ["PlanogramStudio", "./modules/planogram/PlanogramStudio.jsx"],
  ["BudgetIntelligence", "./modules/budget-intelligence/BudgetIntelligence.jsx"],
  ["DockOSDashboard", "./modules/DockOS/DockOSDashboard.jsx"],
  ["AccessControl", "./modules/access-control/AccessControl.jsx"],
  ["ServerAccounts", "./modules/access-control/ServerAccounts.jsx"],
  ["InventoryProductionBoundary", "./modules/inventory/InventoryProductionBoundary.jsx"],
  ["WorkforceBootstrapBoundary", "./modules/workforce/WorkforceBootstrapBoundary.jsx"],
  ["WorkforcePickerApp", "./modules/workforce/WorkforcePickerApp.jsx"],
  ["RecruitmentBootstrapBoundary", "./modules/recruitment/RecruitmentBootstrapBoundary.jsx"],
  ["AcademyWorkspace", "./modules/academy/AcademyWorkspace.jsx"],
  ["AcademyPlayer", "./modules/academy/AcademyPlayer.jsx"],
  ["JarvisWorkspace", "./modules/intelligence/JarvisWorkspace.jsx"],
  ["InsightWorkspace", "./modules/intelligence/InsightWorkspace.jsx"],
  ["PlatformHealth", "./modules/platform-health/PlatformHealth.jsx"],
  ["AuditLog", "./modules/audit-log/AuditLog.jsx"],
]);

if (!source.includes('import React, { Suspense, lazy } from "react";')) {
  fail("App shell must retain React.lazy and Suspense as the route-splitting boundary");
}
if (!source.includes("<Suspense fallback={<RouteLoadingFallback />}>") || !source.includes("</Suspense>")) {
  fail("lazy protected routes must remain behind the accessible route loading fallback");
}

for (const [component, modulePath] of lazyRoutes) {
  const lazyDeclaration = `const ${component} = lazy(() => import("${modulePath}"));`;
  if (!source.includes(lazyDeclaration)) {
    fail(`${component} must remain a lazy route import from ${modulePath}`);
  }

  const escapedPath = modulePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const eagerImport = new RegExp(`^import\\s+[^;]+from\\s+["']${escapedPath}["'];`, "m");
  if (eagerImport.test(source)) {
    fail(`${component} regressed to an eager static import from ${modulePath}`);
  }

  if (!source.includes(`<${component}`)) {
    fail(`${component} lazy declaration is no longer used by a route`);
  }
}

const protectedWorkspaceStaticImports = source
  .split("\n")
  .filter((line) => /^import\s+.+from\s+["']\.\/modules\//.test(line))
  .filter((line) => !line.includes("./modules/control-center/ControlCenterHome.jsx"))
  .filter((line) => !line.includes("./modules/inventory/InventoryUiContext.jsx"))
  .filter((line) => !line.includes("./modules/workforce/WorkforceUiContext.jsx"));

if (protectedWorkspaceStaticImports.length) {
  fail(
    "protected workspace modules must not be added to the eager shell without explicit review: " +
      protectedWorkspaceStaticImports.join(" | ")
  );
}

console.log(`Route code-splitting contract: PASS — ${lazyRoutes.size} protected route components remain lazy.`);
