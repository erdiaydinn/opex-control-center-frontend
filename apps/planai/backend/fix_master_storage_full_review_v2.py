# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import pandas as pd
from storage_normalizer import normalize_row_storage

DATA_DIR = Path("data")
TARGETS = [DATA_DIR / "master_products.csv", DATA_DIR / "master_products_cleaned.csv"]

def apply_file(path: Path):
    if not path.exists():
        return {"file": str(path), "status": "missing"}

    df = pd.read_csv(path, encoding="utf-8-sig")
    rows = [normalize_row_storage(r) for r in df.to_dict(orient="records")]
    out = pd.DataFrame(rows)

    changed = (out["storage_type_before_fix"].astype(str).str.upper() != out["storage_type"].astype(str).str.upper()).sum()

    backup = path.with_suffix(path.suffix + ".storage_v2_backup")
    if not backup.exists():
        path.rename(backup)
    else:
        path.unlink()

    out.to_csv(path, index=False, encoding="utf-8-sig")

    return {
        "file": str(path),
        "status": "updated",
        "rows": len(out),
        "changed": int(changed),
        "storage_types": out["storage_type"].value_counts(dropna=False).to_dict(),
        "top_fix_reasons": out["storage_fix_reason"].value_counts(dropna=False).head(20).to_dict(),
        "backup": str(backup),
    }

def main():
    print("PLONAGRAM storage normalization full review v2")
    for p in TARGETS:
        print(apply_file(p))

if __name__ == "__main__":
    main()
