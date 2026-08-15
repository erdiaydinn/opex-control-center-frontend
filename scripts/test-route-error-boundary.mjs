import fs from "node:fs";
import process from "node:process";

const boundaryPath = "src/platform/accessibility/RouteErrorBoundary.jsx";
const appPath = "src/App.jsx";

const boundary = fs.readFileSync(boundaryPath, "utf8");
const app = fs.readFileSync(appPath, "utf8");

const requiredBoundaryContracts = [
  ["React.Component", "route error boundary class"],
  ["getDerivedStateFromError", "render-error capture"],
  ["componentDidCatch", "diagnostic capture"],
  ["role=\"alert\"", "assertive error semantics"],
  ["aria-live=\"assertive\"", "screen-reader error announcement"],
  ["aria-atomic=\"true\"", "atomic error announcement"],
  ["data-eay-product-state=\"error\"", "shared product-state marker"],
  ["tabIndex=\"-1\"", "programmatic error-heading focus"],
  ["this.headingRef.current?.focus()", "deterministic focus transfer"],
  ["previousProps.resetKey !== this.props.resetKey", "route-change reset"],
  ["window.location.reload()", "fresh lazy-chunk recovery"],
  ["typeof window.location?.reload === \"function\"", "browser reload capability guard"],
  ["t(\"errorTitle\")", "localized error title"],
  ["t(\"retry\")", "localized retry action"],
];

for (const [needle, label] of requiredBoundaryContracts) {
  if (!boundary.includes(needle)) {
    console.error(`Missing ${label}: ${needle}`);
    process.exit(1);
  }
}

const retryBody = boundary.match(/retry\(\) \{([\s\S]*?)\n  \}\n\n  render\(\)/)?.[1] || "";
if (!retryBody.includes("window.location.reload()")) {
  console.error("Route retry must perform a clean reload so rejected React.lazy imports can recover.");
  process.exit(1);
}
if (retryBody.indexOf("window.location.reload()") > retryBody.indexOf("this.setState({ error: null })")) {
  console.error("Browser retry must prefer a clean reload before the non-browser state-reset fallback.");
  process.exit(1);
}

const requiredAppContracts = [
  ["useLocation", "route reset source"],
  ["<RouteErrorBoundary resetKey={location.pathname}>", "route error boundary integration"],
  ["data-eay-product-state=\"loading\"", "shared loading-state marker"],
];

for (const [needle, label] of requiredAppContracts) {
  if (!app.includes(needle)) {
    console.error(`Missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (boundary.includes("this.state.error.message") || boundary.includes("this.state.error.stack")) {
  console.error("Raw exception details must not be rendered into the product surface.");
  process.exit(1);
}

console.log("Route error boundary accessibility and recovery contract: PASS");
