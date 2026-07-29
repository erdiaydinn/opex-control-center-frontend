# -*- coding: utf-8 -*-
from pathlib import Path
import re

ENGINE = Path("engine.py")
MASTER_API = Path("master_products_api.py")

ENGINE_NEW = """def storage_type(p: Dict[str, Any]) -> str:
    try:
        from storage_normalizer import normalize_storage_type
        return normalize_storage_type(p)
    except Exception:
        raw = key(
            f"{get(p, ['storage_type', 'Storage Type', 'Storage'], '')} "
            f"{product_name(p)} "
            f"{category_l1(p)} "
            f"{category_l2(p)}"
        )

        if any(x in raw for x in ["FROZEN", "DONUK", "-18", "DONDUR", "ICE CREAM", "FREEZER", "ALGIDA"]):
            return "FROZEN"

        if any(x in raw for x in ["CHILLED", "COLD", "+4", "SÜT", "SUT", "DAIRY", "YOĞURT", "YOGURT", "FRIDGE"]):
            return "CHILLED"

        return "AMBIENT"
"""

MASTER_NEW = """def _storage(row):
    try:
        from storage_normalizer import normalize_storage_type
        return normalize_storage_type(row)
    except Exception:
        raw = str(row.get("storage_type") or "").upper().strip()
        name = f"{row.get('product_name','')} {row.get('frontend_category_local','')} {row.get('frontend_subcategory_local','')} {row.get('pim_cat_l1','')} {row.get('pim_cat_l2','')}".lower()
        if raw in ("FROZEN", "CHILLED", "AMBIENT"):
            return raw
        if any(x in name for x in ["dondurma", "frozen", "donuk", "-18", "ice cream"]):
            return "FROZEN"
        if any(x in name for x in ["tavuk", "et", "süt", "yoğurt", "peynir", "chilled", "soğuk", "+4"]):
            return "CHILLED"
        if any(x in name for x in ["pide", "ekmek", "fırın", "bakery", "la lorraine"]):
            return "BAKERY_INFERRED"
        return "AMBIENT"
"""

def patch_engine():
    if not ENGINE.exists():
        print("engine.py yok, atlandı")
        return
    text = ENGINE.read_text(encoding="utf-8")
    backup = ENGINE.with_suffix(".py.before_storage_normalizer_v2")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    pattern = r"def storage_type\\(p: Dict\\[str, Any\\]\\) -> str:\\n(?:    .*\\n)+?\\n(?=def shelf_storage)"
    new_text, n = re.subn(pattern, ENGINE_NEW + "\\n", text, flags=re.MULTILINE)
    if n != 1:
        print("engine.py storage_type patch başarısız veya dosya yapısı farklı. Manuel kontrol gerekli.")
        return
    ENGINE.write_text(new_text, encoding="utf-8")
    print("engine.py patched")

def patch_master_api():
    if not MASTER_API.exists():
        print("master_products_api.py yok, atlandı")
        return
    text = MASTER_API.read_text(encoding="utf-8")
    backup = MASTER_API.with_suffix(".py.before_storage_normalizer_v2")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    pattern = r"def _storage\\(row\\):\\n(?:    .*\\n)+?\\n(?=def _normalize)"
    new_text, n = re.subn(pattern, MASTER_NEW + "\\n", text, flags=re.MULTILINE)
    if n != 1:
        print("master_products_api.py _storage patch başarısız veya dosya yapısı farklı. Manuel kontrol gerekli.")
        return
    MASTER_API.write_text(new_text, encoding="utf-8")
    print("master_products_api.py patched")

if __name__ == "__main__":
    patch_engine()
    patch_master_api()
