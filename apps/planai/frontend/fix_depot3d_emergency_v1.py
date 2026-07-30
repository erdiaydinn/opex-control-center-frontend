from pathlib import Path
import re
import shutil

ROOT = Path.cwd()
DEPOT = ROOT / "src" / "components" / "Depot3D.jsx"

if not DEPOT.exists():
    raise SystemExit(
        "Depot3D.jsx bulunamadı. Bu script frontend klasöründe çalışmalı:\n"
        "cd C:\\Users\\ErdiAydın\\planai\\frontend\n"
        "python fix_depot3d_emergency_v1.py"
    )

backup = DEPOT.with_name("Depot3D_before_emergency_hotfix_v1.jsx")
if not backup.exists():
    shutil.copy2(DEPOT, backup)

txt = DEPOT.read_text(encoding="utf-8")

if 'from "three"' not in txt and "from 'three'" not in txt:
    lines = txt.splitlines()
    last_import = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            last_import = i
    lines.insert(last_import + 1, 'import * as THREE from "three";')
    txt = "\n".join(lines) + "\n"

fiber_re = re.compile(r'import\s*\{([^}]+)\}\s*from\s*["\']@react-three/fiber["\'];?')
m = fiber_re.search(txt)
if m:
    names = [x.strip() for x in m.group(1).split(",")]
    changed = False
    for needed in ["Canvas", "useFrame", "useThree"]:
        if needed not in names:
            names.append(needed)
            changed = True
    if changed:
        txt = fiber_re.sub('import { ' + ", ".join(names) + ' } from "@react-three/fiber";', txt, count=1)

if "setActiveTool" in txt and "__plonagramSetActiveToolFallback" not in txt:
    shim = '''

// === PLONAGRAM EMERGENCY HOTFIX V1 ===
// Depot3D içinde setActiveTool tanımsız kalırsa Canvas komple çöküyordu.
// Bu fallback 3D sahneyi ayağa kaldırır. Sonraki sprintte tool state App/Depot3D tarafına temiz bağlanacak.
const __plonagramSetActiveToolFallback = (tool) => {
  try {
    window.__PLONAGRAM_ACTIVE_TOOL__ = tool;
    window.dispatchEvent(new CustomEvent("plonagram:active-tool", { detail: { tool } }));
  } catch (_) {}
};

'''
    lines = txt.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, shim)

    if not re.search(r'(const|let|var)\s+\[?\s*[^;\n]*setActiveTool|function\s+setActiveTool', txt):
        lines.insert(insert_at + 1, 'const setActiveTool = __plonagramSetActiveToolFallback;')
    txt = "\n".join(lines) + "\n"

if "safeOpenFixtureEditor" not in txt:
    helper = '''

// Fixture editor event bridge.
// 3D obje tıklamalarında parent callback bağlı değilse bile event atar.
const safeOpenFixtureEditor = (payload) => {
  try {
    window.dispatchEvent(new CustomEvent("plonagram:open-fixture-editor", { detail: payload || {} }));
  } catch (_) {}
};

'''
    lines = txt.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, helper)
    txt = "\n".join(lines) + "\n"

DEPOT.write_text(txt, encoding="utf-8")

print("Tamamlandı.")
print(f"Backup: {backup}")
print("Şimdi frontend'i yeniden başlat:")
print("npm run dev")
