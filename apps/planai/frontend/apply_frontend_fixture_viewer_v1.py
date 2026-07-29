from pathlib import Path
import shutil
import re

ROOT = Path.cwd()
SRC = ROOT / "src"
COMPONENTS = SRC / "components"
FIXTURE = COMPONENTS / "fixture"

print("Plonagram Frontend Fixture Viewer v1 patch kontrolü...")

if not SRC.exists():
    raise SystemExit("Hata: Bu script frontend klasörü içinde çalışmalı. Örnek: C:\\Users\\ErdiAydın\\planai\\frontend")

# Component files are already copied if this script came with package tree.
print(f"Fixture component path: {FIXTURE}")

shelf_editor = COMPONENTS / "ShelfEditor.jsx"
if not shelf_editor.exists():
    print("ShelfEditor.jsx bulunamadı. Component dosyaları oluşturuldu; importu manuel eklemen gerekecek.")
    raise SystemExit(0)

backup = COMPONENTS / "ShelfEditor_before_fixture_viewer_v1.jsx"
if not backup.exists():
    shutil.copy2(shelf_editor, backup)
    print(f"Backup alındı: {backup}")

txt = shelf_editor.read_text(encoding="utf-8")

import_line = 'import FixtureViewerRouter from "./fixture/FixtureViewerRouter";'
if "FixtureViewerRouter" not in txt:
    # add after last import line
    lines = txt.splitlines()
    last_import = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("import "):
            last_import = i
    if last_import >= 0:
        lines.insert(last_import + 1, import_line)
        txt = "\n".join(lines) + "\n"
        print("Import eklendi.")
    else:
        txt = import_line + "\n" + txt
        print("Import başa eklendi.")
else:
    print("Import zaten var.")

# We avoid dangerous JSX rewrites. We add a comment marker near the component start if possible.
marker = """
/*
FIXTURE VIEWER V1 MANUAL MOUNT:
Seçili raf/modül ürünlerini gösterdiğin büyük panelde eski ürün gridinin üstüne veya yerine şunu koy:

<FixtureViewerRouter
  shelf={selectedShelf?.shelf || selectedShelf}
  module={selectedShelf?.module}
  aisle={selectedShelf?.aisle}
  products={(selectedShelf?.shelf || selectedShelf)?.products || []}
/>

Bu component fixture_viewer_type / fixture_need / storage_type alanlarından otomatik görünüm seçer.
*/
"""

if "FIXTURE VIEWER V1 MANUAL MOUNT" not in txt:
    txt = txt.replace("export default", marker + "\nexport default", 1) if "export default" in txt else marker + "\n" + txt
    print("Manuel mount notu eklendi.")

shelf_editor.write_text(txt, encoding="utf-8")
print("Tamamlandı. Şimdi ShelfEditor.jsx içinde nottaki <FixtureViewerRouter /> bloğunu seçili raf paneline yerleştir.")
