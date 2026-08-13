import assert from "node:assert/strict";

import {
  ACCESS_MODULES,
  MODULE_DETAIL_CONFIG,
  getAccessConfig,
  refreshAccessConfig,
  saveAccessConfig,
} from "../src/auth/accessConfig.js";
import { commandModules } from "../src/modules/control-center/commandCenterModules.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

globalThis.CustomEvent = class CustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
};

globalThis.window = {
  localStorage: new MemoryStorage(),
  dispatchEvent() {},
};

const legacyConfig = {
  groups: {
    custom_ops: {
      id: "custom_ops",
      name: "Custom Ops",
      status: "active",
      modules: {
        dockos: {
          view: true,
          admin: false,
          details: {
            features: { dashboard: true },
            actions: { view: true, delete: false },
            scope: { type: "warehouse", warehouses: ["Fulya (İstanbul)"] },
          },
        },
      },
    },
  },
  users: {
    "admin@yemeksepeti.com": {
      email: "admin@yemeksepeti.com",
      name: "Admin User",
      role: "admin",
      status: "active",
      groups: [],
      modules: {
        dockos: { view: true, admin: false },
      },
    },
  },
};

window.localStorage.setItem("opex_access_config_v4", JSON.stringify(legacyConfig));

const migrated = getAccessConfig();
assert.ok(migrated.groups.custom_ops, "Custom group must survive migration");
assert.deepEqual(migrated.users["admin@yemeksepeti.com"].groups, [], "Explicit group removals must survive migration");
assert.equal(migrated.groups.custom_ops.modules.dockos.view, true, "Existing module permission must survive");
assert.deepEqual(
  migrated.groups.custom_ops.modules.dockos.details.scope.warehouses,
  ["Fulya (İstanbul)"],
  "Existing data scope must survive"
);

for (const module of ACCESS_MODULES) {
  assert.ok(migrated.groups.custom_ops.modules[module.key], `Missing migrated module: ${module.key}`);
  assert.ok(MODULE_DETAIL_CONFIG[module.key], `Missing detail permission catalog: ${module.key}`);
}

const commandKeys = new Set(commandModules.map((module) => module.moduleKey));
for (const module of ACCESS_MODULES) {
  assert.ok(commandKeys.has(module.key), `Command Center is missing module card: ${module.key}`);
}

const withoutViewers = structuredClone(migrated);
delete withoutViewers.groups.viewers;
saveAccessConfig(withoutViewers);
assert.equal(getAccessConfig().groups.viewers, undefined, "Save must not silently restore a deleted group");

const rawAfterDeletion = structuredClone(withoutViewers);
delete rawAfterDeletion.groups.custom_ops.modules.workforce;
const refreshed = refreshAccessConfig(rawAfterDeletion);
assert.equal(refreshed.groups.viewers, undefined, "Module refresh must not recreate a deleted group");
assert.ok(refreshed.groups.custom_ops.modules.workforce, "Module refresh should add a missing platform entry");
assert.equal(refreshed.groups.custom_ops.modules.dockos.view, true, "Refresh must preserve existing grants");
assert.deepEqual(
  refreshed.groups.custom_ops.modules.dockos.details.scope.warehouses,
  ["Fulya (İstanbul)"],
  "Refresh must preserve existing scope"
);

console.log(`Access catalog OK: ${ACCESS_MODULES.length} modules, existing grants preserved.`);
