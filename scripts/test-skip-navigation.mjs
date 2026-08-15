import fs from "node:fs";
import assert from "node:assert/strict";

const main = fs.readFileSync("src/main.jsx", "utf8");
const app = fs.readFileSync("src/App.jsx", "utf8");
const skip = fs.readFileSync("src/platform/accessibility/SkipToMainContent.jsx", "utf8");
const css = fs.readFileSync("src/platform/accessibility/skip-to-main-content.css", "utf8");
const messages = fs.readFileSync("src/platform/i18n/messages.js", "utf8");

assert.match(main, /<SkipToMainContent\s*\/>/);
assert.match(main, /<main id="eay-main-content" tabIndex="-1">/);
assert.match(main, /<RouteAccessibility\s*\/>/);
assert.doesNotMatch(app, /<RouteAccessibility\s*\/>/);
assert.match(skip, /href="#eay-main-content"/);
assert.match(skip, /t\("skipToContent"\)/);
assert.match(css, /\.eay-skip-link:focus/);
assert.match(css, /prefers-reduced-motion:\s*reduce/);

const localeDefinitions = messages.match(/skipToContent:/g) || [];
assert.ok(localeDefinitions.length >= 10, "skipToContent must remain localized for every supported locale");

console.log("skip navigation accessibility contract: PASS");
