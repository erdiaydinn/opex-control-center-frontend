const fs = require("fs");
const path = require("path");

const appPath = path.join(process.cwd(), "src", "App.jsx");

if (fs.existsSync(appPath)) {
  let src = fs.readFileSync(appPath, "utf8");

  // Remove old hero if it exists so 3D Studio becomes the hero experience instead of placeholder hero.
  src = src.replace(/<section className="os-hero">[\s\S]*?<\/section>/, "");

  // Replace old studio wrapper title with operations command center naming.
  src = src.replace(/Your Warehouse\. Digitally Perfect\.\.?/g, "Live Operations Command Center");
  src = src.replace(/Darkstore Live Twin/g, "Omniverse Live Twin");
  src = src.replace(/Digital Twin Studio/g, "AI Operations Digital Twin");

  fs.writeFileSync(appPath, src, "utf8");
  console.log("App.jsx cleaned: old placeholder hero removed if present.");
} else {
  console.warn("src/App.jsx bulunamadı.");
}
