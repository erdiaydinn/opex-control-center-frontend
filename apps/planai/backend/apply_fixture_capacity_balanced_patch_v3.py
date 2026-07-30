
from pathlib import Path
import shutil
from datetime import datetime

ENGINE = Path("engine.py")
MAPPER = Path("fixture_capacity_mapper.py")
MARK = "# === PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V3 ==="

PATCH_BLOCK = """
# === PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V3 ===
# Layout object -> real fixture capacity mapper + cold/frozen capacity expansion.
# This patch wraps generate_planogram/run_engine without deleting existing engine logic.

try:
    from fixture_capacity_mapper import expand_layout_for_product_mix as _plonagram_expand_layout_for_product_mix
    from fixture_capacity_mapper import storage_capacity as _plonagram_storage_capacity

    if "_plonagram_original_generate_planogram_v3" not in globals():
        _plonagram_original_generate_planogram_v3 = generate_planogram

    def generate_planogram(
        products,
        layout,
        mode="HYBRID",
        brand_side_rules=None,
        scoring_config=None,
        allow_ai_dimensions=True,
    ):
        raw_layout = layout or generate_default_layout()

        expanded_layout = _plonagram_expand_layout_for_product_mix(
            raw_layout,
            products or [],
            make_shelves,
        )

        result = _plonagram_original_generate_planogram_v3(
            products=products,
            layout=expanded_layout,
            mode=mode,
            brand_side_rules=brand_side_rules,
            scoring_config=scoring_config,
            allow_ai_dimensions=allow_ai_dimensions,
        )

        plan = result.get("planogram") or {}
        result["engine_patches"] = {
            **(result.get("engine_patches") or {}),
            "fixture_capacity_mapper_v3": True,
            "balanced_capacity_expansion": True,
        }
        result["fixture_capacity_summary"] = expanded_layout.get("ai_fixture_capacity_summary", {})
        result["capacity_after_generation"] = _plonagram_storage_capacity(plan)
        return result

    def run_engine(products, layout=None, **kwargs):
        return generate_planogram(products, layout, **kwargs)

except Exception as _plonagram_fixture_capacity_patch_error:
    print("PLONAGRAM fixture capacity balanced patch V3 devreye alınamadı:", _plonagram_fixture_capacity_patch_error)
# === END PLONAGRAM_FIXTURE_CAPACITY_BALANCED_ENGINE_V3 ===
"""

def backup(path: Path):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(path, path.with_suffix(path.suffix + f".bak_fixture_capacity_v3_{stamp}"))

if not ENGINE.exists():
    raise SystemExit("engine.py bulunamadı. Bu script backend klasöründe çalıştırılmalı.")

if not MAPPER.exists():
    raise SystemExit("fixture_capacity_mapper.py bulunamadı. ZIP içindeki dosyayı backend klasörüne kopyala.")

text = ENGINE.read_text(encoding="utf-8")

if MARK in text:
    print("engine.py zaten fixture capacity balanced V3 patch içeriyor.")
else:
    backup(ENGINE)
    ENGINE.write_text(text.rstrip() + "\\n\\n" + PATCH_BLOCK.strip() + "\\n", encoding="utf-8")
    print("engine.py patchlendi: fixture capacity mapper + balanced placement V3 aktif.")

print("Tamamlandı.")
