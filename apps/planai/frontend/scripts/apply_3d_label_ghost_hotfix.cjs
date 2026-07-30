const fs = require("fs");
const path = require("path");

const layoutPath = path.join(process.cwd(), "src", "components", "LayoutEditor.jsx");
const cssPath = path.join(process.cwd(), "src", "components", "LayoutEditor.css");

if (!fs.existsSync(layoutPath)) {
  console.error("LayoutEditor.jsx bulunamadı.");
  process.exit(1);
}

let s = fs.readFileSync(layoutPath, "utf8");

// Ensure body class toggles while editor is open
if (!s.includes("layout-architect-open")) {
  const marker = `useEffect(() => {
    if (!open) return;
    setAisles((plan?.aisles || []).map(normalizeAisle));
    setObjects(plan?.layout_objects || []);
    setSelectedAisle("ALL");
    setSelectedId(null);
  }, [open, plan]);`;

  const replacement = `${marker}

  useEffect(() => {
    if (!open) return;
    document.body.classList.add("layout-architect-open");
    return () => document.body.classList.remove("layout-architect-open");
  }, [open]);`;

  if (s.includes(marker)) {
    s = s.replace(marker, replacement);
  } else {
    // fallback: inject before if (!open) return null;
    s = s.replace(
      "if (!open) return null;",
      `useEffect(() => {
    if (!open) return;
    document.body.classList.add("layout-architect-open");
    return () => document.body.classList.remove("layout-architect-open");
  }, [open]);

  if (!open) return null;`
    );
  }
}

fs.writeFileSync(layoutPath, s, "utf8");

// Ensure CSS import is present
if (fs.existsSync(cssPath)) {
  let css = fs.readFileSync(cssPath, "utf8");
  if (!css.includes("LayoutEditor.ghostfix.css")) {
    css += `\n@import "./LayoutEditor.ghostfix.css";\n`;
    fs.writeFileSync(cssPath, css, "utf8");
  }
}

console.log("3D label ghost hotfix applied.");
