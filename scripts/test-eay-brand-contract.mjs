import fs from "node:fs";

function read(path) {
  return fs.readFileSync(path, "utf8");
}

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const contract = JSON.parse(read("config/eay_brand_v1.json"));
const branding = read("src/config/branding.js");
const home = read("src/modules/control-center/ControlCenterHome.jsx");
const login = read("src/pages/Login.jsx");
const brandCss = read("src/platform/brand/eay-brand.css");
const brandComponent = read("src/platform/brand/EayBrand.jsx");
const fieldTheme = read("android-field-ui/field-ui/src/main/java/com/eay/mobile/fieldui/EayFieldTheme.kt");
const androidName = read("android-inventory/app/src/main/res/values/eay_mobile_app.xml");
const manifest = read("android-inventory/app/src/main/AndroidManifest.xml");
const fontProvenance = read("docs/brand/MANROPE_PROVENANCE.md");

const expected = {
  navy: "#07235B",
  magenta: "#D20A6D",
  electric_blue: "#1F6BFF",
  charcoal: "#111827",
  white: "#FFFFFF",
};
for (const [key, value] of Object.entries(expected)) {
  requireCondition(contract.colors[key] === value, `Brand color drifted: ${key}`);
  requireCondition(brandCss.toLowerCase().includes(value.toLowerCase()), `Web token missing ${value}`);
}

requireCondition(contract.architecture.master.name === "EAY", "Master brand must remain EAY");
requireCondition(contract.architecture.platform.name === "EAY One", "Platform brand must remain EAY One");
requireCondition(contract.architecture.terminal.name === "EAY Terminal", "Terminal brand must remain EAY Terminal");
requireCondition(contract.typography.family === "Manrope", "Canonical brand font must remain Manrope");
requireCondition(contract.typography.asset_state === "SELF_HOST_BINARY_PENDING", "Font asset truth boundary drifted");
requireCondition(fontProvenance.includes("23dcf5e05a97f19a3567d40ebb3765580a4325f7"), "Reviewed Manrope upstream blob provenance missing");
requireCondition(fontProvenance.includes("OFL-1.1"), "Manrope OFL-1.1 provenance missing");
requireCondition(!fs.existsSync("public/fonts/Manrope-wght.ttf"), "Bundled Manrope exists but asset_state still claims pending");
for (const forbiddenRemote of ["fonts.googleapis.com", "fonts.gstatic.com", "@import url("]) {
  requireCondition(!brandCss.toLowerCase().includes(forbiddenRemote), `Remote runtime font dependency forbidden: ${forbiddenRemote}`);
}

requireCondition(branding.includes('"EAY One"'), "Default platform name must be EAY One");
requireCondition(branding.includes('"EAY"'), "Default company name must be EAY");
requireCondition(!branding.includes("EAY OneOps"), "Legacy OneOps product name remains");

requireCondition(home.includes("EayBrand"), "Control Center must render the EAY brand component");
requireCondition(home.includes('variant="one"'), "Control Center must use EAY One identity");
requireCondition(!home.includes("Sparkles"), "Generic sparkle must not be the platform mark");
requireCondition(!home.includes("OneOps"), "Legacy OneOps lockup remains in Control Center");

requireCondition(login.includes("EayBrand"), "Login must render the EAY brand component");
requireCondition(login.includes('variant="one"'), "Login must use EAY One identity");
requireCondition(!login.includes("<strong>OPEX</strong>"), "Legacy OPEX loading brand remains");
requireCondition(!/[A-Za-zÀ-ž]\?[A-Za-zÀ-ž]/u.test(login), "Login contains mojibake question-mark text");

for (const token of ["#07235B", "#D20A6D", "#1F6BFF", "#111827"]) {
  requireCondition(fieldTheme.includes(token.replace("#", "0xFF")), `Android theme missing ${token}`);
}
requireCondition(androidName.includes(">EAY Terminal<"), "Rugged app must be named EAY Terminal");
requireCondition(manifest.includes('android:icon="@mipmap/ic_launcher"'), "Terminal adaptive icon is not bound");
requireCondition(manifest.includes('android:roundIcon="@mipmap/ic_launcher_round"'), "Terminal round icon is not bound");

for (const variant of ["master", "one", "terminal"]) {
  requireCondition(brandComponent.includes(`${variant}:`), `Brand component label missing: ${variant}`);
}

console.log("EAY cross-platform brand contract: PASS");
