import fs from "node:fs";
import process from "node:process";

const path = "src/modules/recruitment/recruitmentApi.js";
const source = fs.readFileSync(path, "utf8");

function requireCondition(condition, message) {
  if (!condition) {
    console.error(message);
    process.exit(1);
  }
}

requireCondition(
  source.includes("async function safeBackendRequest"),
  "Recruitment backend calls must pass through the adapter error boundary.",
);
requireCondition(
  source.includes('safe.name = "RecruitmentBackendError"'),
  "Recruitment backend failures must expose a stable safe error class.",
);
requireCondition(
  source.includes("SAFE_RECRUITMENT_BACKEND_ERROR"),
  "Recruitment backend failures need a user-safe fallback message.",
);

const apiCallPattern = /\bapi(?:Get|Post|Put|Upload|Download)\([^\n]+/g;
const calls = source.match(apiCallPattern) || [];
for (const call of calls) {
  const offset = source.indexOf(call);
  const lineStart = source.lastIndexOf("\n", offset) + 1;
  const lineEnd = source.indexOf("\n", offset);
  const line = source.slice(lineStart, lineEnd === -1 ? source.length : lineEnd);
  requireCondition(
    line.includes("safeBackendRequest("),
    `Direct Recruitment backend call bypasses safeBackendRequest: ${line.trim()}`,
  );
}

requireCondition(calls.length >= 9, "Recruitment backend error gate unexpectedly covers too few API calls.");
console.log(`Recruitment backend error boundary: PASS (${calls.length} guarded API calls)`);
