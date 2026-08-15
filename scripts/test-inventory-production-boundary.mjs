import fs from "node:fs";
import process from "node:process";

const appPath = "src/App.jsx";
const boundaryPath = "src/modules/inventory/InventoryProductionBoundary.jsx";
const dashboardPath = "src/modules/inventory/InventoryDashboard.jsx";

const app = fs.readFileSync(appPath, "utf8");
const boundary = fs.readFileSync(boundaryPath, "utf8");
const dashboard = fs.readFileSync(dashboardPath, "utf8");

function requireCondition(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

requireCondition(
  app.includes('lazy(() => import("./modules/inventory/InventoryProductionBoundary.jsx"))'),
  "Inventory route must lazy-load the production truth boundary."
);
requireCondition(
  app.includes("<InventoryProductionBoundary />"),
  "Inventory route must mount the production truth boundary."
);
requireCondition(
  !app.includes('lazy(() => import("./modules/inventory/InventoryDashboard.jsx"))'),
  "InventoryDashboard must not be routed directly in the production shell."
);

requireCondition(
  boundary.includes("if (import.meta.env.DEV)"),
  "Local Inventory pilot dashboard must be explicitly DEV-only."
);
requireCondition(
  boundary.includes("return <InventoryDashboard />"),
  "DEV pilot path must remain available for repository-local testing."
);
requireCondition(
  boundary.includes('data-inventory-authority="production-backend-native-terminal"'),
  "Production Inventory boundary must declare backend/native terminal authority."
);
for (const [needle, label] of [
  ['data-eay-product-state="error"', "explicit fail-closed product state"],
  ['role="alert"', "assertive error semantics"],
  ['aria-live="assertive"', "assertive live region"],
  ['aria-atomic="true"', "atomic announcement"],
  ['t("errorTitle")', "localized error title"],
]) {
  requireCondition(boundary.includes(needle), `Inventory production boundary missing ${label}: ${needle}`);
}

requireCondition(
  dashboard.includes("function allowSensitivePilotStorage()") && dashboard.includes("import.meta.env.DEV"),
  "Inventory pilot storage must remain development-only."
);
requireCondition(
  dashboard.includes("purgeSensitiveInventoryStorage"),
  "Inventory pilot must purge sensitive browser state outside development."
);

console.log("Inventory production truth boundary: PASS");
