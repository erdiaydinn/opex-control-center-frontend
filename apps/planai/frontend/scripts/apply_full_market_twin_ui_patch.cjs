const fs = require("fs");
const path = require("path");

function ensureImport(src, importLine) {
  if (src.includes(importLine)) return src;
  const imports = [...src.matchAll(/^import .*?;$/gm)];
  if (!imports.length) return importLine + "\n" + src;
  const last = imports[imports.length - 1];
  const idx = last.index + last[0].length;
  return src.slice(0, idx) + "\n" + importLine + src.slice(idx);
}

const appPath = path.join(process.cwd(), "src", "App.jsx");
const appCssPath = path.join(process.cwd(), "src", "App.premium.css");
const authCssPath = path.join(process.cwd(), "src", "components", "auth", "PlonagramAuth.css");

if (fs.existsSync(appPath)) {
  let src = fs.readFileSync(appPath, "utf8");
  src = ensureImport(src, 'import StudioRealismHero from "./components/StudioRealismHero";');
  src = ensureImport(src, 'import "./components/StudioRealismHero.css";');

  // Replace old Intelligence hero block if class is present
  src = src.replace(
    /<section className="os-hero">[\s\S]*?<\/section>/,
    `<StudioRealismHero onGenerate={generatePlanogram} onOpenStudio={() => setView("3D")} />`
  );

  // If no old os-hero section, inject before first Digital Twin Studio section if possible
  if (!src.includes("<StudioRealismHero")) {
    src = src.replace(
      /<section className="os-studio-section">/,
      `<StudioRealismHero onGenerate={generatePlanogram} onOpenStudio={() => setView("3D")} />\n<section className="os-studio-section">`
    );
  }

  fs.writeFileSync(appPath, src, "utf8");
  console.log("App.jsx hero patched.");
}

if (fs.existsSync(authCssPath)) {
  let css = fs.readFileSync(authCssPath, "utf8");
  if (!css.includes("auth-hero-visual")) {
    css += `\n.auth-hero-visual{margin-top:22px;max-width:1180px}.auth-hero-visual .mtv-shell{border-radius:30px}\n`;
    fs.writeFileSync(authCssPath, css, "utf8");
  }
}

console.log("Full market twin UI patch applied.");
