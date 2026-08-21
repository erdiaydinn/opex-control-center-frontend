import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const config = JSON.parse(fs.readFileSync("config/ui_i18n_guard.json", "utf8"));
const baseline = String(config.baseline_sha || "").trim();
const roots = Array.isArray(config.scan_roots) ? config.scan_roots : ["src"];
const extensions = new Set(config.extensions || [".jsx", ".tsx"]);
const attributes = config.user_facing_attributes || ["placeholder", "title", "aria-label", "alt"];
const allowedExact = new Set(config.allowed_exact_literals || []);
const escapeMarkers = config.documented_escape_markers || [];

function git(args, options = {}) {
  return execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], ...options });
}

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

requireCondition(/^[0-9a-f]{40}$/.test(baseline), "UI i18n baseline_sha must be a full 40-character commit SHA");
try {
  git(["cat-file", "-e", `${baseline}^{commit}`]);
} catch {
  throw new Error(`UI i18n baseline ${baseline} is not available. Product Quality checkout must use fetch-depth: 0.`);
}
try {
  execFileSync("git", ["merge-base", "--is-ancestor", baseline, "HEAD"], { stdio: "ignore" });
} catch {
  throw new Error(`UI i18n baseline ${baseline} is not an ancestor of HEAD; rotate the baseline through an explicit governance change.`);
}

const diff = git(["diff", "--unified=0", "--no-color", `${baseline}...HEAD`, "--", ...roots]);
const attrPattern = new RegExp(`\\b(${attributes.map((value) => value.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")).join("|")})\\s*=\\s*[\"']([^\"']+)[\"']`, "gu");
const jsxTextPattern = />\s*([^<>{}]*\p{L}[^<>{}]*)\s*</gu;
const messageCallPattern = /\b(?:setError|setMessage|setStatusMessage|alert|confirm|toast(?:\.\w+)?)\s*\(\s*["'`]([^"'`]*\p{L}[^"'`]*)["'`]/gu;
const labelPropertyPattern = /\b(?:label|helperText|emptyText|description)\s*:\s*["'`]([^"'`]*\p{L}[^"'`]*)["'`]/gu;

function normalizeLiteral(value) {
  return value.replace(/\s+/g, " ").trim();
}

function brandOnly(value) {
  const normalized = normalizeLiteral(value);
  if (allowedExact.has(normalized)) return true;
  const punctuationStripped = normalized.replace(/[·|:—–\-]/gu, " ").replace(/\s+/g, " ").trim();
  return allowedExact.has(punctuationStripped);
}

function jsxTernaryPredicate(value) {
  const normalized = normalizeLiteral(value);
  // The zero-context diff scanner can see the JavaScript predicate between
  // adjacent JSX tags as if it were visible text. Ignore only a narrow ternary
  // predicate grammar; actual prose and string literals remain guarded.
  return /^[!A-Za-z_$][\w.$()[\]!\s]*\.length\s*(?:===|!==|[<>]=?)\s*\d+\s*\?$/u.test(normalized);
}

function jsxArrowExpressionFragment(value) {
  const normalized = normalizeLiteral(value);
  // In an added expression such as `items.filter((item) => item.active).length <= 1`,
  // the zero-context scanner sees the text between `>` and `<` as JSX. Ignore only
  // the code-shaped fragment ending in `).length`; human-facing prose stays guarded.
  return /^[A-Za-z_$][\w.$]*\)\.length$/u.test(normalized);
}

function meaningful(value) {
  const normalized = normalizeLiteral(value);
  return Boolean(
    normalized
    && /\p{L}/u.test(normalized)
    && !brandOnly(normalized)
    && !jsxTernaryPredicate(normalized)
    && !jsxArrowExpressionFragment(normalized)
  );
}

function documentedEscape(line) {
  for (const marker of escapeMarkers) {
    const index = line.indexOf(marker);
    if (index < 0) continue;
    const reason = line
      .slice(index + marker.length)
      .replace(/[}*\/]+$/g, "")
      .trim();
    if (!reason) throw new Error(`UI i18n escape marker requires a reason: ${marker}`);
    return `${marker} ${reason}`;
  }
  return null;
}

const violations = [];
let currentFile = "";
let nextNewLine = 0;
let pendingEscape = null;

for (const rawLine of diff.split("\n")) {
  if (rawLine.startsWith("+++ b/")) {
    currentFile = rawLine.slice(6);
    pendingEscape = null;
    continue;
  }
  if (rawLine.startsWith("@@")) {
    const match = rawLine.match(/\+(\d+)(?:,(\d+))?/u);
    nextNewLine = match ? Number(match[1]) : 0;
    pendingEscape = null;
    continue;
  }
  if (!currentFile || !extensions.has(path.extname(currentFile))) continue;
  if (rawLine.startsWith("-") && !rawLine.startsWith("---")) continue;
  if (!rawLine.startsWith("+") || rawLine.startsWith("+++")) {
    if (rawLine.startsWith(" ")) nextNewLine += 1;
    continue;
  }

  const lineNumber = nextNewLine;
  nextNewLine += 1;
  const source = rawLine.slice(1);
  const trimmed = source.trim();
  const escape = documentedEscape(source);
  if (escape && (/^(?:\/\/|\/\*|\{\/\*)/u.test(trimmed))) {
    pendingEscape = escape;
    continue;
  }
  if (!trimmed) continue;
  if (/^(?:\/\/|\*|\/\*)/u.test(trimmed)) continue;

  const activeEscape = escape || pendingEscape;
  pendingEscape = null;
  if (activeEscape) continue;

  const found = [];
  for (const match of source.matchAll(attrPattern)) {
    if (meaningful(match[2])) found.push({ kind: `attribute:${match[1]}`, literal: match[2] });
  }
  for (const match of source.matchAll(jsxTextPattern)) {
    if (meaningful(match[1])) found.push({ kind: "jsx-text", literal: match[1] });
  }
  for (const match of source.matchAll(messageCallPattern)) {
    if (meaningful(match[1])) found.push({ kind: "user-message", literal: match[1] });
  }
  for (const match of source.matchAll(labelPropertyPattern)) {
    if (meaningful(match[1])) found.push({ kind: "label-property", literal: match[1] });
  }

  const unique = new Map(found.map((item) => [`${item.kind}\u0000${normalizeLiteral(item.literal)}`, item]));
  for (const item of unique.values()) {
    violations.push({
      file: currentFile,
      line: lineNumber,
      kind: item.kind,
      literal: normalizeLiteral(item.literal),
    });
  }
}

if (violations.length) {
  console.error("New hard-coded user-facing UI strings are not allowed. Use the platform i18n layer.");
  for (const item of violations) {
    console.error(`- ${item.file}:${item.line} [${item.kind}] ${JSON.stringify(item.literal)}`);
  }
  console.error("For a true brand/data literal, add a documented i18n-brand-literal: or i18n-data-literal: reason in the preceding or same added line.");
  process.exit(1);
}

console.log(`No new hard-coded user-facing JSX/TSX strings since baseline ${baseline}: PASS`);
