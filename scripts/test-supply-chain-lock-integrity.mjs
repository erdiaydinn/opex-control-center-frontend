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

const truthValidatorPath = "scripts/security/validate_prebuild_evidence_contract.py";
if (!fs.existsSync(truthValidatorPath)) {
  fail("common pre-build evidence truth validator is missing");
}
const truthValidator = fs.readFileSync(truthValidatorPath, "utf8");
for (const required of [
  'ALLOWED_LIFECYCLES = {"pre-build", "build"}',
  '"production_runtime_proof=true"',
  '"deployment_attestation=true"',
  '"runtime_attestation=true"',
  '"reachability_proof=true"',
  '"eay:truth-boundary"',
]) {
  if (!truthValidator.includes(required)) {
    fail(`pre-build evidence truth validator lost required fail-closed rule: ${required}`);
  }
}

for (const generatorPath of [
  "scripts/security/generate_cyclonedx_sbom.py",
  "scripts/security/generate_python_build_cyclonedx.py",
  "scripts/security/gradle_dependency_report_to_cyclonedx.py",
]) {
  const source = fs.readFileSync(generatorPath, "utf8");
  if (!source.includes("from validate_prebuild_evidence_contract import validate_document")) {
    fail(`${generatorPath}: common pre-build evidence validator import is missing`);
  }
  if (!source.includes("validate_document(bom, source=")) {
    fail(`${generatorPath}: generated dependency evidence is not truth-boundary validated`);
  }
}

console.log(
  `Supply-chain lock integrity: PASS (${manifestNames.length} direct dependencies, ${remoteArtifacts} integrity-pinned HTTPS artifacts, 3 truth-boundary-wired SBOM generators)`,
);
