const fs = require("fs");
const path = require("path");

function patchFile(file) {
  if (!fs.existsSync(file)) return false;
  let s = fs.readFileSync(file, "utf8");
  let changed = false;

  if (!s.includes("MarketDigitalTwinVisual")) {
    const lastImport = [...s.matchAll(/^import .*?;$/gm)].pop();
    if (lastImport) {
      const idx = lastImport.index + lastImport[0].length;
      s = s.slice(0, idx) + `\nimport MarketDigitalTwinVisual from "./components/visuals/MarketDigitalTwinVisual";` + s.slice(idx);
      changed = true;
    }
  }

  // Replace old generic hero visual if present
  s = s.replace(
    /<div className="os-hero-visual">[\s\S]*?<\/div>\s*<\/div>/,
    `<div className="os-hero-visual os-hero-market-twin">
            <MarketDigitalTwinVisual variant="hero" />
          </div>`
  );

  // If previous block name differs, inject visual into first hero visual container
  s = s.replace(
    /<div className="os-hero-market-twin">\s*[\s\S]*?\s*<\/div>/,
    `<div className="os-hero-market-twin">
            <MarketDigitalTwinVisual variant="hero" />
          </div>`
  );

  if (!s.includes('import "./components/visuals/MarketDigitalTwinVisual.css"') && !s.includes("MarketDigitalTwinVisual.css")) {
    // component imports its own css, no app css import required
  }

  if (changed || s !== fs.readFileSync(file, "utf8")) {
    fs.writeFileSync(file, s, "utf8");
    return true;
  }
  return false;
}

const app = path.join(process.cwd(), "src", "App.jsx");
const auth = path.join(process.cwd(), "src", "components", "auth", "PlonagramAuth.jsx");

let any = false;
any = patchFile(app) || any;

if (fs.existsSync(auth)) {
  let s = fs.readFileSync(auth, "utf8");
  if (!s.includes("MarketDigitalTwinVisual")) {
    const lastImport = [...s.matchAll(/^import .*?;$/gm)].pop();
    if (lastImport) {
      const idx = lastImport.index + lastImport[0].length;
      s = s.slice(0, idx) + `\nimport MarketDigitalTwinVisual from "../visuals/MarketDigitalTwinVisual";` + s.slice(idx);
    }
  }

  // Replace existing auth animation/preview blocks conservatively
  s = s.replace(
    /<div className="[^"]*(?:auth|hero|operation)[^"]*(?:visual|scene|preview)[^"]*"[^>]*>[\s\S]*?<\/div>/,
    `<div className="auth-market-twin-visual">
              <MarketDigitalTwinVisual variant="auth" />
            </div>`
  );

  fs.writeFileSync(auth, s, "utf8");
  any = true;
}

console.log(any ? "Market realism visual patch applied." : "No matching file/block found. Component files are still installed.");
