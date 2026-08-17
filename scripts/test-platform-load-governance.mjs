import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workflowPath = ".github/workflows/platform-load-acceptance.yml";
const source = readFileSync(workflowPath, "utf8");

function requireText(fragment, message) {
  assert.ok(source.includes(fragment), message);
}

requireText(
  'default: "1000"',
  "Canonical synthetic load workflow must default to 1000 VUs."
);
requireText(
  "''|*[!0-9]*)",
  "TARGET_VUS must remain strict decimal-integer input before load execution."
);
requireText(
  'if [ "$TARGET_VUS" -lt 1000 ]; then',
  "Manual dispatch must fail closed below the canonical 1000-VU minimum."
);
requireText(
  'echo "$TARGET_VUS" > /tmp/eay-burst-target-vus',
  "Validated burst size must be persisted for post-load correctness accounting."
);

requireText(
  "Run controlled 50-VU latency gate",
  "Controlled runner-relative latency regression gate must remain present."
);
requireText(
  "-e LOAD_PROFILE=latency",
  "Controlled latency run must use the dedicated latency profile."
);
requireText(
  "-e TARGET_VUS=50",
  "Controlled latency regression profile must remain fixed at 50 VUs."
);
requireText(
  "-e ITERATIONS_PER_VU=2",
  "Controlled latency regression profile must retain two iterations per VU."
);
requireText(
  "Allow CI worker pools to drain",
  "Latency and saturation profiles must retain an explicit runner drain boundary."
);

requireText(
  "continue-on-error: true",
  "Burst execution must allow post-load correctness evidence to run before final enforcement."
);
requireText(
  "Verify tenant and audit correctness after load",
  "Post-load tenant/audit correctness verification is a hard governance requirement."
);
requireText(
  "if: always() && steps.burst_gate.outcome != 'skipped'",
  "Post-load correctness and saturation enforcement must survive a failed burst execution."
);
requireText(
  "Enforce 1000-VU saturation result",
  "A failed burst must still make the workflow RED after correctness evidence is collected."
);
requireText(
  'if [ "$BURST_OUTCOME" != "success" ]; then',
  "Saturation failure enforcement must remain explicit and fail closed."
);
requireText(
  "Record synthetic evidence boundary",
  "Synthetic evidence must remain explicitly separated from production capacity proof."
);
requireText(
  "if: success()",
  "Synthetic evidence may only be emitted after every hard gate succeeds."
);
requireText(
  "not a production capacity SLO",
  "1000-VU evidence must never be labeled as a production SLO."
);

const latencyIndex = source.indexOf("Run controlled 50-VU latency gate");
const drainIndex = source.indexOf("Allow CI worker pools to drain");
const burstIndex = source.indexOf("Run 1000-VU tenant isolation saturation gate");
const verifyIndex = source.indexOf("Verify tenant and audit correctness after load");
const enforceIndex = source.indexOf("Enforce 1000-VU saturation result");
const evidenceIndex = source.indexOf("Record synthetic evidence boundary");

assert.ok(latencyIndex >= 0, "Controlled latency gate must remain in the workflow.");
assert.ok(
  drainIndex > latencyIndex && burstIndex > drainIndex,
  "50-VU latency regression, runner drain and 1000-VU saturation must remain ordered."
);
assert.ok(
  verifyIndex >= 0 && enforceIndex > verifyIndex,
  "Correctness verification must run before burst enforcement."
);
assert.ok(
  evidenceIndex > enforceIndex,
  "Synthetic evidence may only be recorded after all hard gates are enforced."
);

const verificationBlock = source.slice(verifyIndex, enforceIndex);
assert.ok(
  verificationBlock.includes("if: always() && steps.burst_gate.outcome != 'skipped'"),
  "Post-load correctness verification must run after a failed burst so correctness evidence is not lost."
);
assert.ok(
  verificationBlock.includes('export BURST_TARGET_VUS="$(cat /tmp/eay-burst-target-vus)"'),
  "Post-load accounting must use the validated burst size rather than reconstructing a weaker default."
);

const enforcementBlock = source.slice(enforceIndex, evidenceIndex);
assert.ok(
  enforcementBlock.includes("if: always() && steps.burst_gate.outcome != 'skipped'"),
  "Burst failure enforcement must execute after correctness verification."
);

const evidenceBlock = source.slice(evidenceIndex);
assert.ok(
  evidenceBlock.includes("if: success()"),
  "Synthetic evidence must not be emitted when latency, burst, tenant, or audit correctness failed."
);

for (const hardGate of [
  "assert observed == {(TENANT_A, SUBJECT_A), (TENANT_B, SUBJECT_B)}, observed",
  "assert counts == expected_counts, (counts, expected_counts)",
  "assert foreign_a == 0, foreign_a",
  "assert foreign_b == 0, foreign_b",
]) {
  requireText(hardGate, `Tenant/correctness hard gate missing: ${hardGate}`);
}

console.log(
  "Synthetic load governance contract: PASS " +
    "(fixed 50-VU regression, >=1000-VU saturation, correctness-first, success-only evidence)"
);
