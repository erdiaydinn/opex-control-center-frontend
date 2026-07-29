const fs = require("fs");
const path = require("path");

const authPath = path.join(process.cwd(), "src", "components", "auth", "PlonagramAuth.jsx");
const authCssPath = path.join(process.cwd(), "src", "components", "auth", "PlonagramAuth.css");

if (!fs.existsSync(authPath)) {
  console.error("PlonagramAuth.jsx bulunamadı.");
  process.exit(1);
}

console.log("Omniverse auth screen installed.");
