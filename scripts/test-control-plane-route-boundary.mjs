import fs from "node:fs";
import process from "node:process";

const app = fs.readFileSync("src/App.jsx", "utf8");
const boundary = fs.readFileSync("src/auth/ControlPlaneRoute.jsx", "utf8");
const coreMain = fs.readFileSync("services/core-api/app/main.py", "utf8");

const requiredBoundary = [
  ["apiGet(\"/v1/platform/health\")", "control-plane boundary must probe the canonical protected endpoint"],
  ["setState(\"allowed\")", "successful protected probe must allow the route"],
  ["setState(\"denied\")", "control-plane probe failures must fail closed"],
  ["<Navigate to=\"/\" replace />", "denied control-plane routes must redirect away"],
  ["aria-busy=\"true\"", "control-plane probe loading must expose busy semantics"],
];

for (const [needle, message] of requiredBoundary) {
  if (!boundary.includes(needle)) {
    console.error(`${message}: ${needle}`);
    process.exit(1);
  }
}

if (!app.includes('<ControlPlaneRoute><PlatformHealth /></ControlPlaneRoute>')) {
  console.error("Platform health route must remain wrapped by the server-authoritative ControlPlaneRoute boundary.");
  process.exit(1);
}

if (!coreMain.includes('principal: Principal = Depends(require_control_plane_admin)')) {
  console.error("Canonical platform health endpoint must remain bound to require_control_plane_admin.");
  process.exit(1);
}

if (boundary.includes("payload?.capabilities") || boundary.includes("user.roles")) {
  console.error("Control-plane visibility must not trust browser role/capability reconstruction.");
  process.exit(1);
}

console.log("Server-authoritative control-plane route boundary: PASS");
