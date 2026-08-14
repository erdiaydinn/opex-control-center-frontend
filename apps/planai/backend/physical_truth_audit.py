"""Read-only physical-truth audit for real Planogram inputs."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from physical_truth import production_acceptance_report


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _num(value: Any) -> Optional[float]:
    try:
        return None if _text(value) == "" else float(_text(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _first(row: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        if row.get(field) not in (None, ""):
            return row[field]
    return ""


def normalize_master_row(row: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    """Preserve raw master evidence; never invent dimensions or images."""
    width = _num(_first(row, "product_width_in_cm", "width_cm"))
    height = _num(_first(row, "product_height_in_cm", "height_cm"))
    depth = _num(_first(row, "product_length_in_cm", "depth_cm", "length_cm"))
    complete = all(value is not None and value > 0 for value in (width, height, depth))
    return {
        **row,
        "sku": _text(_first(row, "sku", "SKU", "product_barcodes", "barcode")) or f"ROW-{index + 1}",
        "product_name": _text(_first(row, "product_name", "product_name_local", "product_name_english", "name")),
        "brand": _text(_first(row, "brand_name", "brand")),
        "category_l1": _text(_first(row, "frontend_category_local", "frontend_category", "pim_cat_l1", "category_l1")),
        "category_l2": _text(_first(row, "frontend_subcategory_local", "frontend_subcategory", "pim_cat_l2", "category_l2")),
        "catalog_storage_condition_raw": _text(_first(row, "catalog_storage_condition_raw", "Saklama Koşulu (Raf/ +4/-18)", "storage_raw", "Storage Type", "storage_type")),
        "width_cm": width or 0,
        "height_cm": height or 0,
        "depth_cm": depth or 0,
        "weight_kg": _num(_first(row, "product_weight_value", "weight_kg", "Weight")) or 0,
        "image_url": _text(_first(row, "image_url", "catalog_image_url", "pim_image_url", "Product Image URL")),
        "catalog_global_product_id": _text(_first(row, "catalog_global_product_id", "global_product_id")),
        "pim_product_id": _text(_first(row, "pim_product_id")),
        "dimension_source": "master" if complete else "missing",
    }


def load_master_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [normalize_master_row(row, index) for index, row in enumerate(csv.DictReader(handle))]


def load_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def build_audit(master_path: Path, store_dna_path: Optional[Path] = None, layout_path: Optional[Path] = None, *, require_images: bool = True) -> Dict[str, Any]:
    products = load_master_csv(master_path)
    report = production_acceptance_report(products, load_json(layout_path), load_json(store_dna_path), require_images=require_images)
    return {"source": {"master_path": str(master_path), "store_dna_path": str(store_dna_path) if store_dna_path else None, "layout_path": str(layout_path) if layout_path else None}, **report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--store-dna", type=Path)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-missing-images", action="store_true")
    args = parser.parse_args()
    report = build_audit(args.master, args.store_dna, args.layout, require_images=not args.allow_missing_images)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("production_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
