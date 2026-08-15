import fs from "node:fs";
import process from "node:process";

function fail(message) {
  console.error(`Supply-chain lock integrity: FAIL — ${message}`);
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));

if (Number(lock.lockfileVersion) < 3) {
  fail(`package-lock.json must use lockfileVersion >= 3; found ${lock.lockfileVersion}`);
}

const root = lock.packages?.[""];
if (!root || typeof root !== "object") {
  fail("package-lock.json is missing the canonical root package entry");
}

const manifestDependencies = manifest.dependencies || {};
const lockedRootDependencies = root.dependencies || {};
const manifestNames = Object.keys(manifestDependencies).sort();
const lockedNames = Object.keys(lockedRootDependencies).sort();

if (JSON.stringify(manifestNames) !== JSON.stringify(lockedNames)) {
  fail("package.json and package-lock.json direct dependency names drifted");
}

for (const name of manifestNames) {
  const requested = String(manifestDependencies[name]);
  const lockedRequested = String(lockedRootDependencies[name]);
  if (requested !== lockedRequested) {
    fail(`${name}: package.json spec does not match lockfile root spec`);
  }
  if (requested === "*" || requested.toLowerCase() === "latest") {
    fail(`${name}: floating direct dependency specs are prohibited`);
  }
  if (/^(?:git\+|git:|ssh:|http:)/i.test(requested)) {
    fail(`${name}: insecure or mutable direct dependency source is prohibited: ${requested}`);
  }

  if (/^https:/i.test(requested)) {
    const packageEntry = lock.packages?.[`node_modules/${name}`];
    if (!packageEntry) {
      fail(`${name}: direct HTTPS artifact is missing its node_modules lock entry`);
    }
    if (packageEntry.resolved !== requested) {
      fail(`${name}: direct HTTPS artifact resolved URL drifted from package.json`);
    }
    if (!/^sha(?:256|384|512)-/i.test(String(packageEntry.integrity || ""))) {
      fail(`${name}: direct HTTPS artifact must be integrity-pinned in package-lock.json`);
    }
  }
}

let remoteArtifacts = 0;
for (const [path, entry] of Object.entries(lock.packages || {})) {
  if (!path || !entry || typeof entry !== "object" || !entry.resolved) continue;

  const resolved = String(entry.resolved);
  if (/^(?:git\+|git:|ssh:|http:)/i.test(resolved)) {
    fail(`${path}: insecure or mutable resolved source is prohibited: ${resolved}`);
  }

  if (/^https:/i.test(resolved)) {
    remoteArtifacts += 1;
    if (!/^sha(?:256|384|512)-/i.test(String(entry.integrity || ""))) {
      fail(`${path}: HTTPS artifact is missing a cryptographic integrity hash`);
    }
  }
}

if (remoteArtifacts === 0) {
  fail("lockfile unexpectedly contains no HTTPS artifacts to verify");
}

console.log(
  `Supply-chain lock integrity: PASS (${manifestNames.length} direct dependencies, ${remoteArtifacts} integrity-pinned HTTPS artifacts)`,
);
