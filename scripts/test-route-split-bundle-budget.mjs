import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const distAssets = path.resolve("dist/assets");
const maxEntryBytes = Number(process.env.EAY_MAX_MAIN_ENTRY_BYTES || 700_000);
const minAsyncChunks = Number(process.env.EAY_MIN_ASYNC_JS_CHUNKS || 5);

function fail(message) {
  console.error(`Route-split bundle budget: FAIL — ${message}`);
  process.exit(1);
}

if (!Number.isInteger(maxEntryBytes) || maxEntryBytes <= 0) {
  fail("EAY_MAX_MAIN_ENTRY_BYTES must be a positive integer");
}
if (!Number.isInteger(minAsyncChunks) || minAsyncChunks < 1) {
  fail("EAY_MIN_ASYNC_JS_CHUNKS must be a positive integer");
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
