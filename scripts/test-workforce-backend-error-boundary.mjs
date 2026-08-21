import fs from "node:fs";
import process from "node:process";

const path = "src/modules/workforce/workforceApi.js";
const source = fs.readFileSync(path, "utf8");

function requireCondition(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

requireCondition(
  source.includes("async function safeBackendRequest"),
  "Workforce backend calls must pass through the adapter error boundary.",
);
requireCondition(
  source.includes('safe.name = "WorkforceBackendError"'),
  "Workforce backend failures must expose a stable safe error class.",
);
requireCondition(
  source.includes("SAFE_WORKFORCE_BACKEND_ERROR"),
  "Workforce backend failures need a user-safe fallback message.",
);
requireCondition(
  !source.includes("new Error(event.detail.error)"),
  "Native bridge error details must never be copied directly into UI-visible errors.",
);

const apiCallPattern = /\bapi(?:Get|Post|Put|Patch|Delete)\([^\n]+/g;
const calls = source.match(apiCallPattern) || [];
for (const call of calls) {
  const offset = source.indexOf(call);
  const lineStart = source.lastIndexOf("\n", offset) + 1;
  const lineEnd = source.indexOf("\n", offset);
  const line = source.slice(lineStart, lineEnd === -1 ? source.length : lineEnd);
  requireCondition(
    line.includes("safeBackendRequest("),
    `Direct Workforce backend call bypasses safeBackendRequest: ${line.trim()}`,
  );
}

requireCondition(calls.length >= 20, "Workforce backend error gate unexpectedly covers too few API calls.");
console.log(`Workforce backend error boundary: PASS (${calls.length} guarded API calls)`);
