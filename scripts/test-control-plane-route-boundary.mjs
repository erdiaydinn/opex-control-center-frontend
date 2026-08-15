import fs from "node:fs";
import process from "node:process";

const app = fs.readFileSync("src/App.jsx", "utf8");
const boundary = fs.readFileSync("src/auth/ControlPlaneRoute.jsx", "utf8");
const coreMain = fs.readFileSync("services/core-api/app/main.py", "utf8");
const authorization = fs.readFileSync("services/core-api/app/core/authorization.py", "utf8");

const requiredBoundary = [
  ["apiGet(\"/v1/context\")", "control-plane boundary must consume server authorization context"],
  ["payload?.capabilities?.control_plane_admin === true", "control-plane access must require explicit true capability"],
  ["setState(\"denied\")", "control-plane capability lookup failures must fail closed"],
  ["<Navigate to=\"/\" replace />", "denied control-plane routes must redirect away"],
  ["aria-busy=\"true\"", "control-plane capability loading must expose busy semantics"],
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

if (!coreMain.includes('"control_plane_admin": await has_control_plane_admin_authority(principal)')) {
  console.error("/v1/context must publish the canonical control-plane capability projection.");
  process.exit(1);
}

for (const needle of [
  "async def has_control_plane_admin_authority(principal: Principal) -> bool:",
  "await require_control_plane_admin(principal)",
  "except HTTPException:\n        return False",
]) {
  if (!authorization.includes(needle)) {
    console.error(`Canonical control-plane capability projection drifted: ${needle}`);
    process.exit(1);
  }
}

console.log("Server-authoritative control-plane route boundary: PASS");
