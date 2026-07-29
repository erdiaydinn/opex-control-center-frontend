
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import csv
import math
import re
from difflib import SequenceMatcher
from collections import Counter

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "master_products.csv"

TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
    "ş": "s", "Ş": "s", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})

STOP_WORDS = {
    "ve", "ile", "the", "a", "an", "of", "ml", "gr", "g", "kg", "lt", "l",
    "adet", "x", "li", "lu", "lü", "lı", "pack", "paket", "piece", "pcs"
}

STORAGE_RULES = [
    ("FROZEN", ["algida", "dondurma", "ice cream", "frozen", "donuk", "-18", "la lorraine", "milfoy", "milföy"]),
    ("CHILLED", ["yogurt", "yoğurt", "ayran", "peynir", "cheese", "tavuk", "chicken", "et ", "meat", "sucuk", "salam", "deli", "+4", "chilled", "cold", "marul", "maydanoz", "roka", "dereotu", "nane"]),
    ("AMBIENT", ["maden suyu", "mineral water", "soda", "beypazari", "beypazarı", "water", "su ", "ice tea", "cips", "chips", "çikolata", "cikolata", "chocolate", "bar", "deterjan", "temizlik", "pet", "kedi", "kopek", "köpek", "bebek", "baby", "uht", "ekmek", "bread", "mandalina", "limon", "patates", "muz", "domates"])
]

PACKAGE_HINTS = {
    "bottle": ["su", "water", "kola", "cola", "fanta", "sprite", "soda", "maden suyu", "ayran", "ice tea", "meyve suyu"],
    "bag": ["cips", "chips", "un ", "seker", "şeker", "pirinc", "pirinç", "bulgur", "makarna"],
    "bar": ["gofret", "bar", "çikolata", "cikolata", "chocolate"],
    "carton": ["sut", "süt", "milk", "meyve suyu", "juice"],
    "jar": ["salca", "salça", "recel", "reçel", "sos", "sauce", "tursu", "turşu"],
    "box": ["biskuvi", "bisküvi", "biscuit", "kraker", "cracker", "cereal"],
}

DIMENSION_PRIORS_CM = {
    "bottle": {"width_cm": 8, "depth_cm": 8, "height_cm": 28},
    "bag": {"width_cm": 16, "depth_cm": 6, "height_cm": 24},
    "bar": {"width_cm": 8, "depth_cm": 2, "height_cm": 16},
    "carton": {"width_cm": 8, "depth_cm": 8, "height_cm": 20},
    "jar": {"width_cm": 8, "depth_cm": 8, "height_cm": 12},
    "box": {"width_cm": 12, "depth_cm": 6, "height_cm": 18},
    "unknown": {"width_cm": 10, "depth_cm": 8, "height_cm": 18},
}

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()

def norm(v: Any) -> str:
    return _s(v).translate(TR_MAP).lower().strip()

def tokenise(text: str) -> List[str]:
    raw = re.sub(r"[^a-z0-9]+", " ", norm(text))
    return [t for t in raw.split() if len(t) > 1 and t not in STOP_WORDS]

def num(v: Any, d: float = 0.0) -> float:
    try:
        if v is None or str(v).strip() == "":
            return d
        x = float(str(v).replace(",", "."))
        if math.isnan(x) or math.isinf(x):
            return d
        return x
    except Exception:
        return d

def joined_product_text(row: Dict[str, Any]) -> str:
    keys = [
        "product_name", "product_name_local", "product_name_english",
        "brand", "brand_name", "category_l1", "category_l2",
        "frontend_category_local", "frontend_subcategory_local",
        "pim_cat_l1", "pim_cat_l2", "pim_cat_l3", "storage_type"
    ]
    return " ".join(_s(row.get(k)) for k in keys)

def row_key(row: Dict[str, Any]) -> str:
    return _s(row.get("sku") or row.get("barcode") or row.get("product_barcodes") or row.get("product_name"))

def canonical_storage(row: Dict[str, Any]) -> str:
    raw = norm(row.get("storage_type"))
    ntext = norm(joined_product_text(row))

    # Strong AMBIENT overrides first.
    for st, words in STORAGE_RULES:
        if st == "AMBIENT" and any(w in ntext for w in words):
            return "AMBIENT"

    for st, words in STORAGE_RULES:
        if st != "AMBIENT" and any(w in ntext for w in words):
            return st

    if raw.startswith("frozen"):
        return "FROZEN"
    if raw.startswith("chilled"):
        return "CHILLED"
    return "AMBIENT"

def package_type(row: Dict[str, Any]) -> str:
    text = norm(joined_product_text(row))
    for typ, words in PACKAGE_HINTS.items():
        if any(w in text for w in words):
            return typ
    return "unknown"

def _category(row: Dict[str, Any]) -> str:
    return norm(row.get("category_l2") or row.get("frontend_subcategory_local") or row.get("pim_cat_l2") or row.get("category_l1") or row.get("frontend_category_local"))

def _brand(row: Dict[str, Any]) -> str:
    return norm(row.get("brand") or row.get("brand_name"))

def _name(row: Dict[str, Any]) -> str:
    return norm(row.get("product_name") or row.get("product_name_local") or row.get("product_name_english"))

def product_signature(row: Dict[str, Any]) -> Dict[str, Any]:
    text = joined_product_text(row)
    toks = tokenise(text)
    return {
        "key": row_key(row),
        "sku": _s(row.get("sku")),
        "product_name": _s(row.get("product_name") or row.get("product_name_local") or row.get("product_name_english")),
        "brand": _s(row.get("brand") or row.get("brand_name")),
        "category": _s(row.get("category_l2") or row.get("frontend_subcategory_local") or row.get("category_l1") or row.get("frontend_category_local")),
        "storage_type": canonical_storage(row),
        "package_type": package_type(row),
        "tokens": toks,
        "token_set": set(toks),
        "name_norm": _name(row),
        "brand_norm": _brand(row),
        "category_norm": _category(row),
        "width_cm": num(row.get("width_cm") or row.get("product_width_in_cm"), 0),
        "depth_cm": num(row.get("depth_cm") or row.get("product_length_in_cm"), 0),
        "height_cm": num(row.get("height_cm") or row.get("product_height_in_cm"), 0),
        "sales_qty_7d": num(row.get("sales_qty_7d") or row.get("sales_7d") or row.get("sales"), 0),
        "raw": row,
    }

def similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    a_set, b_set = a["token_set"], b["token_set"]
    jaccard = len(a_set & b_set) / max(1, len(a_set | b_set))
    name_ratio = SequenceMatcher(None, a["name_norm"], b["name_norm"]).ratio()
    brand_bonus = 0.18 if a["brand_norm"] and a["brand_norm"] == b["brand_norm"] else 0
    cat_bonus = 0.22 if a["category_norm"] and a["category_norm"] == b["category_norm"] else 0
    storage_bonus = 0.12 if a["storage_type"] == b["storage_type"] else -0.08
    package_bonus = 0.10 if a["package_type"] == b["package_type"] else 0
    return round(max(0, min(1, 0.40*jaccard + 0.28*name_ratio + brand_bonus + cat_bonus + storage_bonus + package_bonus)), 4)

class ProductSimilarityIndex:
    def __init__(self, data_path: Path = DATA_PATH):
        self.data_path = data_path
        self.rows: List[Dict[str, Any]] = []
        self.signatures: List[Dict[str, Any]] = []
        self.loaded = False

    def load(self, force: bool = False) -> None:
        if self.loaded and not force:
            return
        if not self.data_path.exists():
            self.rows = []
            self.signatures = []
            self.loaded = True
            return
        with self.data_path.open("r", encoding="utf-8-sig", newline="") as f:
            self.rows = [dict(r) for r in csv.DictReader(f)]
        self.signatures = [product_signature(r) for r in self.rows]
        self.loaded = True

    def find_similar(self, product: Dict[str, Any], limit: int = 12, min_score: float = 0.38) -> List[Dict[str, Any]]:
        self.load()
        sig = product_signature(product)
        out = []
        for other in self.signatures:
            if sig.get("sku") and other.get("sku") and str(sig["sku"]) == str(other["sku"]):
                continue
            sc = similarity(sig, other)
            if sc >= min_score:
                out.append({
                    "sku": other["sku"],
                    "product_name": other["product_name"],
                    "brand": other["brand"],
                    "category": other["category"],
                    "storage_type": other["storage_type"],
                    "package_type": other["package_type"],
                    "width_cm": other["width_cm"],
                    "depth_cm": other["depth_cm"],
                    "height_cm": other["height_cm"],
                    "sales_qty_7d": other["sales_qty_7d"],
                    "similarity": sc,
                })
        out.sort(key=lambda x: x["similarity"], reverse=True)
        return out[:limit]

    def decide_from_similar(self, product: Dict[str, Any], limit: int = 16) -> Dict[str, Any]:
        self.load()
        sig = product_signature(product)
        similar = self.find_similar(product, limit=limit, min_score=0.30)

        storage_votes = Counter()
        dim_rows = []
        sales_rows = []

        for s in similar:
            weight = max(0.01, s["similarity"])
            storage_votes[s["storage_type"]] += weight
            if s["width_cm"] > 0 and s["depth_cm"] > 0 and s["height_cm"] > 0:
                dim_rows.append((weight, s))
            if s["sales_qty_7d"] > 0:
                sales_rows.append((weight, s))

        rule_storage = canonical_storage(product)
        ntext = norm(joined_product_text(product))

        if storage_votes:
            voted_storage, vote_weight = storage_votes.most_common(1)[0]
            total_votes = sum(storage_votes.values())
            vote_conf = vote_weight / max(total_votes, 1e-9)

            if rule_storage == "AMBIENT" and any(w in ntext for w in ["maden suyu", "mineral water", "soda", "beypazari", "beypazarı"]):
                suggested_storage = "AMBIENT"
                storage_conf = 0.95
                storage_reason = "strong_rule_ambient_beverage"
            elif vote_conf >= 0.58:
                suggested_storage = voted_storage
                storage_conf = round(0.55 + 0.40 * vote_conf, 3)
                storage_reason = f"similar_products_vote:{dict(storage_votes)}"
            else:
                suggested_storage = rule_storage
                storage_conf = 0.62
                storage_reason = f"rule_fallback_low_vote_confidence:{dict(storage_votes)}"
        else:
            suggested_storage = rule_storage
            storage_conf = 0.55
            storage_reason = "no_similar_products_rule_fallback"

        if dim_rows:
            total_w = sum(w for w, _ in dim_rows)
            dims = {
                "width_cm": round(sum(w * s["width_cm"] for w, s in dim_rows) / total_w, 2),
                "depth_cm": round(sum(w * s["depth_cm"] for w, s in dim_rows) / total_w, 2),
                "height_cm": round(sum(w * s["height_cm"] for w, s in dim_rows) / total_w, 2),
            }
            dim_conf = min(0.9, 0.45 + 0.04 * len(dim_rows))
            dim_reason = f"weighted_average_of_{len(dim_rows)}_similar_products"
        else:
            ptype = sig["package_type"]
            dims = DIMENSION_PRIORS_CM.get(ptype, DIMENSION_PRIORS_CM["unknown"])
            dim_conf = 0.48 if ptype == "unknown" else 0.62
            dim_reason = f"package_prior:{ptype}"

        sales_7d = num(product.get("sales_qty_7d") or product.get("sales_7d") or product.get("sales"), 0)
        if sales_7d <= 0 and sales_rows:
            total_w = sum(w for w, _ in sales_rows)
            sales_7d = round(sum(w * s["sales_qty_7d"] for w, s in sales_rows) / total_w, 2)

        facing = 1
        if sales_7d >= 140:
            facing = 5
        elif sales_7d >= 80:
            facing = 3
        elif sales_7d >= 30:
            facing = 2

        confidence = round((storage_conf * 0.45) + (dim_conf * 0.35) + (min(1, len(similar)/12) * 0.20), 3)

        why = [
            f"{len(similar)} benzer ürün bulundu.",
            f"Storage kararı: {suggested_storage} ({storage_reason}).",
            f"Ölçü kararı: {dim_reason}.",
            f"Facing önerisi satış/benzer satış sinyaline göre {facing}.",
        ]

        return {
            "sku": sig["sku"],
            "product_name": sig["product_name"],
            "decision": {
                "storage_type": suggested_storage,
                "dimensions": dims,
                "facing": facing,
                "confidence": confidence,
                "storage_confidence": storage_conf,
                "dimension_confidence": round(dim_conf, 3),
            },
            "why": why,
            "similar_products": similar,
        }

_INDEX = ProductSimilarityIndex()

def find_similar_products(product: Dict[str, Any], limit: int = 12) -> Dict[str, Any]:
    return {"products": _INDEX.find_similar(product, limit=limit), "indexed_products": len(_INDEX.signatures) if _INDEX.loaded else None}

def decide_product(product: Dict[str, Any], limit: int = 16) -> Dict[str, Any]:
    return _INDEX.decide_from_similar(product, limit=limit)

def reload_similarity_index() -> Dict[str, Any]:
    _INDEX.load(force=True)
    return {"status": "success", "indexed_products": len(_INDEX.signatures), "data_path": str(_INDEX.data_path)}
