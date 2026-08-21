import fs from "node:fs";

const routeSource = fs.readFileSync("src/platform/accessibility/RouteAccessibility.jsx", "utf8");
const mainSource = fs.readFileSync("src/main.jsx", "utf8");

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

requireCondition(mainSource.includes('import RouteAccessibility from "./platform/accessibility/RouteAccessibility.jsx"'), "app shell must import route accessibility boundary");
requireCondition(mainSource.includes("<RouteAccessibility />"), "route accessibility boundary must remain mounted outside lazy route content");
requireCondition(routeSource.includes("useLocation"), "route accessibility must observe router path changes");
requireCondition(routeSource.includes("previousPath.current === path"), "same-path updates must not steal keyboard focus");
requireCondition(routeSource.includes("location.pathname"), "hash/query-only changes must not be treated as full page transitions");
requireCondition(routeSource.includes("[role='dialog'][aria-modal='true']"), "route focus must preserve active modal focus authority");
requireCondition(routeSource.includes("focus({ preventScroll: true })"), "route transition must move focus without unexpected scroll jumps");
requireCondition(routeSource.includes("MutationObserver"), "lazy route content must be observed before announcing or focusing its heading");
requireCondition(routeSource.includes('role="status"'), "route changes must expose a polite screen-reader status region");
requireCondition(routeSource.includes('aria-live="polite"'), "route announcement must use polite live-region semantics");
requireCondition(routeSource.includes('aria-atomic="true"'), "route announcement must be atomic for assistive technology");
requireCondition(routeSource.includes('target.setAttribute("tabindex", "-1")'), "non-interactive route headings/main targets must be programmatically focusable");

console.log("EAY route focus and screen-reader announcement: PASS");
