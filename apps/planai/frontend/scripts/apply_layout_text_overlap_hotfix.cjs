
const fs = require("fs");
const path = require("path");

const file = path.join(process.cwd(), "src", "components", "LayoutEditor.jsx");
if (!fs.existsSync(file)) {
  console.error("LayoutEditor.jsx bulunamadı.");
  process.exit(1);
}
let s = fs.readFileSync(file, "utf8");

// Add short label data attribute to module div if missing
s = s.replace(
  /className=\{`le-module-node \$\{m\.side \|\| ""\} \$\{m\.fixture_type \|\| ""\} \$\{selectedId === m\.id \? "selected" : ""\}`\}\s*style=/,
  'className={`le-module-node ${m.side || ""} ${m.fixture_type || ""} ${selectedId === m.id ? "selected" : ""}`} data-short-label={`${m.side || ""}${m.module_id || ""}`} style='
);

// Remove verbose module inner content block
s = s.replace(
  /<b>\{m\.label\}<\/b>\s*<span>\{m\.fixture_type\}<\/span>/g,
  '<b>{m.side}{m.module_id}</b>'
);

fs.writeFileSync(file, s, "utf8");
console.log("LayoutEditor.jsx text overlap hotfix applied.");
