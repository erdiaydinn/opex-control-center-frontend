
from fulya_store_dna_loader import build_fulya_layout

layout = build_fulya_layout()

print("store:", layout["store_code"], layout["store_name"])
print("module_count:", len(layout["modules"]))
print("fixture_capacity_summary:", layout["fixture_capacity_summary"])
print("original_capacity_summary:", layout.get("fulya_original_capacity_summary"))

summary = layout["fixture_capacity_summary"]
ambient = summary["modules_by_storage"].get("AMBIENT", 0)
chilled = summary["modules_by_storage"].get("CHILLED", 0)
frozen = summary["modules_by_storage"].get("FROZEN", 0)

# The JSON has two different capacity signals:
# 1) explicit ambient_layout face/module counts -> 217 AMBIENT modules
# 2) capacity_summary.ambient_module_count_estimated -> 357 estimated modules
# This smoke test validates the explicit parsed layout and warns about the estimate gap.
assert len(layout["modules"]) >= 270, f"Fulya parsed module count unexpectedly low: {len(layout['modules'])}"
assert ambient >= 210, f"Ambient parsed module count unexpectedly low: {ambient}"
assert chilled >= 20, f"Chilled parsed module count unexpectedly low: {chilled}"
assert frozen >= 30, f"Frozen parsed module count unexpectedly low: {frozen}"

estimated_ambient = (layout.get("fulya_original_capacity_summary") or {}).get("ambient_module_count_estimated")
if estimated_ambient and estimated_ambient != ambient:
    print(
        "WARNING: Explicit ambient_layout parsed modules differ from original capacity_summary estimate:",
        {"explicit_ambient_modules": ambient, "estimated_ambient_modules": estimated_ambient, "delta": estimated_ambient - ambient}
    )

print("FULYA_STORE_DNA smoke test OK")
