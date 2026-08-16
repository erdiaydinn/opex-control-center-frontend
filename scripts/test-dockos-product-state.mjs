import fs from "node:fs";
import process from "node:process";

const dashboardPath = "src/modules/DockOS/DockOSDashboard.jsx";
const basePath = "src/modules/DockOS/DockOSDashboardBase.jsx";
const dashboard = fs.readFileSync(dashboardPath, "utf8");
const base = fs.readFileSync(basePath, "utf8");

function requireCondition(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

requireCondition(
  dashboard.includes("<div dir={dir} className={`dockos-permission-shell"),
  "DockOS authorized experience must not wrap its canonical dashboard main landmark in another main element.",
);

requireCondition(
  base.includes("const [stats, setStats] = useState(null);"),
  "DockOS KPI state must start unknown instead of presenting synthetic zero values before authoritative load.",
);
requireCondition(
  base.includes('data-eay-product-state={productState}'),
  "DockOS dashboard must expose the canonical product-state boundary.",
);
requireCondition(
  base.includes('aria-busy={apiStatus === "checking"}'),
  "DockOS loading state must expose busy semantics.",
);
requireCondition(
  base.includes('data-eay-product-state="loading"') &&
    base.includes('role="status"') &&
    base.includes('aria-live="polite"'),
  "DockOS loading state must be announced without interrupting the user.",
);
requireCondition(
  base.includes('data-eay-product-state="error"') &&
    base.includes('role="alert"'),
  "DockOS backend failure must expose assertive error semantics.",
);
requireCondition(
  base.includes('apiStatus === "online" && stats'),
  "DockOS KPI and child workspaces must remain hidden until authoritative dashboard data loads successfully.",
);
requireCondition(
  !/error\.message|error\.stack|JSON\.stringify\(error/.test(base),
  "DockOS dashboard must never render raw backend or transport exception details.",
);
requireCondition(
  !base.includes("apiMessage"),
  "DockOS dashboard must not preserve a raw backend-message channel.",
);
requireCondition(
  base.includes('disabled={apiStatus === "checking"}') &&
    base.includes('onClick={loadStats}'),
  "DockOS refresh/retry controls must remain deterministic during loading and available after failure.",
);

console.log("DockOS fail-closed loading/error/ready product-state contract: PASS");
