
const fs = require("fs");
const path = require("path");

const appPath = path.join(process.cwd(), "src", "App.jsx");
if (fs.existsSync(appPath)) {
  let src = fs.readFileSync(appPath, "utf8");
  src = src.replace(/Digital Twin Studio/g, "AI Operations Digital Twin");
  src = src.replace(/Darkstore Live Twin/g, "Omniverse Live Twin");
  src = src.replace(/Your Warehouse\. Digitally Perfect\.?/g, "Live Operations Command Center");
  fs.writeFileSync(appPath, src, "utf8");
}

console.log("Premium render language final patch applied.");
