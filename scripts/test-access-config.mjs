import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  clearAuthorizationSnapshot,
  getAuthorizationSnapshot,
  publishAuthorizationSnapshot,
} from "../src/auth/authorizationStore.js";
import { commandModules } from "../src/modules/control-center/commandCenterModules.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const legacyAccessConfig = resolve(root, "src/auth/accessConfig.js");
const authorizationStorePath = resolve(root, "src/auth/authorizationStore.js");
const moduleCatalogPath = resolve(root, "config/module_catalog.json");

assert.equal(
  existsSync(legacyAccessConfig),
  false,
  "Legacy browser-local accessConfig.js must not return; authorization is server-authoritative"
);

const authorizationStoreSource = readFileSync(authorizationStorePath, "utf8");
for (const forbidden of ["localStorage", "sessionStorage", "saveAccessConfig", "refreshAccessConfig"]) {
  assert.equal(
    authorizationStoreSource.includes(forbidden),
    false,
    `Authorization snapshot store must not contain browser-local authority primitive: ${forbidden}`
  );
}

const serverPayload = {
  user: { email: "operator@example.test", displayName: "Operator" },
  tenantId: "tenant-ys-tr",
  roles: ["operations_manager"],
  permissions: ["module:planogram:view", "module:dockos:view"],
  permissionAssignments: [
    {
      key: "module:planogram:view",
      role_key: "operations_manager",
      scope: { warehouse_id: "WH-FULYA" },
    },
  ],
};

publishAuthorizationSnapshot(serverPayload);
const snapshot = getAuthorizationSnapshot();

assert.equal(snapshot.tenantId, "tenant-ys-tr");
assert.deepEqual(snapshot.roles, ["operations_manager"]);
assert.deepEqual(snapshot.permissions, ["module:planogram:view", "module:dockos:view"]);
assert.deepEqual(snapshot.permissionAssignments, [
  {
    key: "module:planogram:view",
    role_key: "operations_manager",
    scope: { warehouse_id: "WH-FULYA" },
  },
]);
assert.equal(snapshot.user.email, "operator@example.test");

assert.ok(Object.isFrozen(snapshot), "Authorization snapshot must be immutable");
assert.ok(Object.isFrozen(snapshot.user), "Published user identity must be immutable");
assert.ok(Object.isFrozen(snapshot.roles), "Published roles must be immutable");
assert.ok(Object.isFrozen(snapshot.permissions), "Published permissions must be immutable");
assert.ok(Object.isFrozen(snapshot.permissionAssignments), "Permission assignments must be immutable");
assert.ok(Object.isFrozen(snapshot.permissionAssignments[0]), "Permission assignment must be immutable");
assert.ok(Object.isFrozen(snapshot.permissionAssignments[0].scope), "Permission scope must be immutable");

serverPayload.user.displayName = "Tampered";
serverPayload.roles.push("super_admin");
serverPayload.permissions.push("admin_access:admin");
serverPayload.permissionAssignments[0].scope.warehouse_id = "WH-OTHER";

assert.equal(snapshot.user.displayName, "Operator", "Published user must not track caller mutations");
assert.deepEqual(snapshot.roles, ["operations_manager"], "Published roles must not track caller mutations");
assert.deepEqual(
  snapshot.permissions,
  ["module:planogram:view", "module:dockos:view"],
  "Published permissions must not track caller mutations"
);
assert.equal(
  snapshot.permissionAssignments[0].scope.warehouse_id,
  "WH-FULYA",
  "Published scope must not track caller mutations"
);

const catalog = JSON.parse(readFileSync(moduleCatalogPath, "utf8"));
const commercialKeys = new Set(catalog.commercial_modules.map((module) => module.key));
const commandKeys = new Set(commandModules.map((module) => module.moduleKey));

for (const moduleKey of ["planogram", "dockos", "budget", "workforce", "inventory", "academy"]) {
  assert.ok(commercialKeys.has(moduleKey), `Canonical module catalog is missing ${moduleKey}`);
  assert.ok(commandKeys.has(moduleKey), `Command Center is missing canonical module card ${moduleKey}`);
}

clearAuthorizationSnapshot();
const cleared = getAuthorizationSnapshot();
assert.equal(cleared.user, null);
assert.equal(cleared.tenantId, null);
assert.deepEqual(cleared.roles, []);
assert.deepEqual(cleared.permissions, []);
assert.deepEqual(cleared.permissionAssignments, []);

publishAuthorizationSnapshot(null);
assert.equal(getAuthorizationSnapshot().user, null, "Invalid payload must fail closed to empty authorization");

console.log(
  `Server-authoritative access smoke OK: ${commandModules.length} command cards, no browser-local grant store.`
);
