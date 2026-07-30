
from pathlib import Path
import shutil
from datetime import datetime

ENGINE = Path("engine.py")
MASTER = Path("master_products_api.py")
NORMALIZER = Path("storage_normalizer.py")
MARK_ENGINE = "# === PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_ENGINE ==="
MARK_MASTER = "# === PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_MASTER ==="

def backup(path: Path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(path, path.with_suffix(path.suffix + f".bak_storage_v3_{stamp}"))

def append_once(path: Path, mark: str, block: str):
    if not path.exists():
        print(f"{path} bulunamadı.")
        return False
    text = path.read_text(encoding="utf-8")
    if mark in text:
        print(f"{path} zaten patchli.")
        return True
    backup(path)
    path.write_text(text.rstrip() + "\n\n" + block.strip() + "\n", encoding="utf-8")
    print(f"{path} patchlendi.")
    return True

engine_block = """
# === PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_ENGINE ===
try:
    from storage_normalizer import normalize_storage_type as _plonagram_normalize_storage_type
    def storage_type(p):
        return _plonagram_normalize_storage_type(p)
except Exception as _plonagram_storage_patch_err:
    print("PLONAGRAM storage normalizer engine override devreye alınamadı:", _plonagram_storage_patch_err)
# === END PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_ENGINE ===
"""

master_block = """
# === PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_MASTER ===
try:
    from storage_normalizer import normalize_storage_type as _plonagram_normalize_storage_type
    def _storage(row):
        return _plonagram_normalize_storage_type(row)
except Exception as _plonagram_storage_patch_err:
    print("PLONAGRAM storage normalizer master override devreye alınamadı:", _plonagram_storage_patch_err)
# === END PLONAGRAM_STORAGE_NORMALIZER_FORCE_PATCH_V3_MASTER ===
"""

if not NORMALIZER.exists():
    print("storage_normalizer.py bulunamadı. ZIP içindeki dosyayı backend klasörüne kopyala.")
else:
    ok1 = append_once(ENGINE, MARK_ENGINE, engine_block)
    ok2 = append_once(MASTER, MARK_MASTER, master_block)
    print({"engine_patch": ok1, "master_patch": ok2})
