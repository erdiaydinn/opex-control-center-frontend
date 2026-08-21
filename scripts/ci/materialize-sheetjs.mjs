import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";

const version = "0.20.3";
const url = `https://cdn.sheetjs.com/xlsx-${version}/xlsx-${version}.tgz`;
const target = new URL(`../../vendor/xlsx-${version}.tgz`, import.meta.url);
const expectedSha512 = "oLDq3jw7AcLqKWH2AhCpVTZl8mf6X2YReP+Neh0SJUzV/BdZYjth94tG5toiMB1PPrYtxOCfaoUCkvtuH+3AJA==";

function digest(buffer) {
  return createHash("sha512").update(buffer).digest("base64");
}

async function existingIsValid() {
  try {
    return digest(await readFile(target)) === expectedSha512;
  } catch {
    return false;
  }
}

if (await existingIsValid()) {
  console.log(`SheetJS ${version} already materialized with expected integrity.`);
  process.exit(0);
}

await rm(target, { force: true });
await mkdir(new URL("../../vendor/", import.meta.url), { recursive: true });

const response = await fetch(url, {
  redirect: "follow",
  headers: { "User-Agent": "EAY-Platform-CI/1.0" },
});
if (!response.ok) {
  throw new Error(`SheetJS download failed: HTTP ${response.status}`);
}

const buffer = Buffer.from(await response.arrayBuffer());
const actual = digest(buffer);
if (actual !== expectedSha512) {
  throw new Error(`SheetJS integrity mismatch: expected ${expectedSha512}, got ${actual}`);
}

await writeFile(target, buffer, { flag: "wx" });
console.log(`SheetJS ${version} materialized from the pinned official CDN artifact.`);
