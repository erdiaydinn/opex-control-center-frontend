
from pathlib import Path
import shutil
from datetime import datetime

ENGINE = Path("engine.py")
LOADER = Path("fulya_store_dna_loader.py")
DATA = Path("data") / "fulya_depo_layout.json"

MARK = "# === PLONAGRAM_FULYA_STORE_DNA_ENGINE_V1 ==="

PATCH_BLOCK = """
# === PLONAGRAM_FULYA_STORE_DNA_ENGINE_V1 ===
# Fulya prestige/test store DNA loader.
# If layout/store context points to Fulya, generate_planogram uses real Fulya fixture DNA
# instead of generic/default layout.

try:
    from fulya_store_dna_loader import build_fulya_layout as _plonagram_build_fulya_layout
    from fulya_store_dna_loader import should_use_fulya_layout as _plonagram_should_use_fulya_layout

    if "_plonagram_original_generate_planogram_fulya_v1" not in globals():
        _plonagram_original_generate_planogram_fulya_v1 = generate_planogram

    def generate_planogram(
        products,
        layout,
        mode="HYBRID",
        brand_side_rules=None,
        scoring_config=None,
        allow_ai_dimensions=True,
    ):
        raw_layout = layout or {}

        if _plonagram_should_use_fulya_layout(raw_layout):
            raw_layout = _plonagram_build_fulya_layout(make_shelves=make_shelves)

        result = _plonagram_original_generate_planogram_fulya_v1(
            products=products,
            layout=raw_layout,
            mode=mode,
            brand_side_rules=brand_side_rules,
            scoring_config=scoring_config,
            allow_ai_dimensions=allow_ai_dimensions,
        )

        result["store_dna"] = {
            **(result.get("store_dna") or {}),
            "fulya_store_dna_v1": bool(raw_layout.get("source") == "fulya_store_dna_v1"),
            "store_code": raw_layout.get("store_code"),
            "store_name": raw_layout.get("store_name"),
        }

        if raw_layout.get("fixture_capacity_summary"):
            result["fixture_capacity_summary"] = raw_layout.get("fixture_capacity_summary")
        if raw_layout.get("fulya_original_capacity_summary"):
            result["fulya_original_capacity_summary"] = raw_layout.get("fulya_original_capacity_summary")

        return result

    def run_engine(products, layout=None, **kwargs):
        return generate_planogram(products, layout or {}, **kwargs)

except Exception as _plonagram_fulya_patch_error:
    print("PLONAGRAM Fulya Store DNA patch V1 devreye alınamadı:", _plonagram_fulya_patch_error)
# === END PLONAGRAM_FULYA_STORE_DNA_ENGINE_V1 ===
"""

def backup(path: Path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(path, path.with_suffix(path.suffix + f".bak_fulya_dna_v1_{stamp}"))

if not ENGINE.exists():
    raise SystemExit("engine.py bulunamadı. Script backend klasöründe çalıştırılmalı.")
if not LOADER.exists():
    raise SystemExit("fulya_store_dna_loader.py bulunamadı. ZIP içindeki dosyayı backend klasörüne kopyala.")
if not DATA.exists():
    raise SystemExit("data/fulya_depo_layout.json bulunamadı. ZIP içindeki data klasörünü backend'e kopyala.")

text = ENGINE.read_text(encoding="utf-8")
if MARK in text:
    print("engine.py zaten Fulya Store DNA V1 patch içeriyor.")
else:
    backup(ENGINE)
    ENGINE.write_text(text.rstrip() + "\\n\\n" + PATCH_BLOCK.strip() + "\\n", encoding="utf-8")
    print("engine.py patchlendi: Fulya Store DNA V1 aktif.")

print("Tamamlandı.")
