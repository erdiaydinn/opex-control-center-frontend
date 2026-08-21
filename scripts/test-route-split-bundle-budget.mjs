import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const distAssets = path.resolve("dist/assets");
const CANONICAL_MAX_ENTRY_BYTES = 700_000;
const CANONICAL_MIN_ASYNC_CHUNKS = 5;

function fail(message) {
  console.error(`Route-split bundle budget: FAIL — ${message}`);
  process.exit(1);
}

function readIntegerOverride(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value)) {
    fail(`${name} must be an integer when provided`);
  }
  return value;
}

const maxEntryBytes = readIntegerOverride(
  "EAY_MAX_MAIN_ENTRY_BYTES",
  CANONICAL_MAX_ENTRY_BYTES
);
const minAsyncChunks = readIntegerOverride(
  "EAY_MIN_ASYNC_JS_CHUNKS",
  CANONICAL_MIN_ASYNC_CHUNKS
);

if (maxEntryBytes <= 0) {
  fail("EAY_MAX_MAIN_ENTRY_BYTES must be a positive integer");
}
if (maxEntryBytes > CANONICAL_MAX_ENTRY_BYTES) {
  fail(
    `EAY_MAX_MAIN_ENTRY_BYTES cannot weaken the canonical ${CANONICAL_MAX_ENTRY_BYTES}-byte ceiling; ` +
      "only stricter overrides are allowed"
  );
}
if (minAsyncChunks < 1) {
  fail("EAY_MIN_ASYNC_JS_CHUNKS must be a positive integer");
}
if (minAsyncChunks < CANONICAL_MIN_ASYNC_CHUNKS) {
  fail(
    `EAY_MIN_ASYNC_JS_CHUNKS cannot weaken the canonical ${CANONICAL_MIN_ASYNC_CHUNKS}-chunk minimum; ` +
      "only stricter overrides are allowed"
  );
}
if (!fs.existsSync(distAssets)) {
  fail("dist/assets is missing; run the production build before this gate");
}

const javascriptAssets = fs
  .readdirSync(distAssets)
  .filter((name) => name.endsWith(".js"))
  .map((name) => ({
    name,
    bytes: fs.statSync(path.join(distAssets, name)).size,
  }))
  .sort((left, right) => right.bytes - left.bytes);

if (!javascriptAssets.length) {
  fail("production build emitted no JavaScript assets");
}

const entryCandidates = javascriptAssets.filter((asset) => /^index-[\w-]+\.js$/.test(asset.name));
if (entryCandidates.length !== 1) {
  fail(`expected exactly one Vite index entry chunk, found ${entryCandidates.length}`);
}

const [entry] = entryCandidates;
const asyncChunks = javascriptAssets.filter((asset) => asset.name !== entry.name);

if (entry.bytes > maxEntryBytes) {
  fail(
    `main entry ${entry.name} is ${entry.bytes} bytes; budget is ${maxEntryBytes} bytes. ` +
      "Protected product routes must remain lazy/route-split instead of returning to a monolithic entry bundle."
  );
}

if (asyncChunks.length < minAsyncChunks) {
  fail(
    `only ${asyncChunks.length} async JavaScript chunks were emitted; minimum is ${minAsyncChunks}. ` +
      "This usually means route-level code splitting regressed."
  );
}

const largestAsync = asyncChunks.slice(0, 5).map((asset) => `${asset.name}=${asset.bytes}`).join(", ");
console.log(
  `Route-split bundle budget: PASS — entry=${entry.name} ${entry.bytes}/${maxEntryBytes} bytes; ` +
    `async_chunks=${asyncChunks.length} (minimum ${minAsyncChunks}); largest_async=[${largestAsync}]`
);
