"""Rule and scoring contract exposed to the frontend rule editor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List
import re

from engine import DEFAULT_SCORING_CONFIG, normalize_storage


RULE_CATALOG: Dict[str, Any] = {
    "hard_rules": [
        {"id": "storage", "label": "Depolama / soğuk zincir", "fields": ["allowed_storage_type"], "locked": True},
        {"id": "dimension", "label": "Fiziksel ölçü uyumu", "fields": ["width_cm", "height_cm", "depth_cm"], "locked": True},
        {"id": "capacity", "label": "Raf kapasitesi", "fields": ["shelf_width_cm", "max_weight_kg"], "locked": True},
        {"id": "food_safety", "label": "Gıda / temizlik ayrımı", "fields": ["merch_group"], "locked": True},
        {"id": "category_allow_block", "label": "Kategori izin / engel listesi", "fields": ["allowed_categories", "blocked_categories"], "locked": False},
    ],
    "soft_weights": [
        {"id": key, "label": key.replace("_", " ").title(), "default": value, "min": 0, "max": 5}
        for key, value in DEFAULT_SCORING_CONFIG.items()
    ],
    "presets": [
        {"id": "HYBRID", "label": "Hibrit: satış + kategori + ABC", "description": "Varsayılan dengeleyici strateji."},
        {"id": "CATEGORY", "label": "Kategori blokları", "description": "Kategori içi yerleşimi öne alır."},
        {"id": "ABC", "label": "ABC / satış", "description": "A ürünleri önce ve erişilebilir bölgelere alınır."},
        {"id": "BRAND", "label": "Marka blokları", "description": "Aynı marka ve alt kategoriyi birlikte tutar."},
        {"id": "PICKING", "label": "Toplama rotası", "description": "Toplama mesafesi ve erişim ergonomisini artırır."},
    ],
    "locales": {
        "tr": {"rule_engine": "Kural ve ağırlık motoru", "generate": "Planı üret", "audit": "Audit log"},
        "en": {"rule_engine": "Rule & weight engine", "generate": "Generate plan", "audit": "Audit log"},
        "de": {"rule_engine": "Regel- und Gewichtungsengine", "generate": "Plan erzeugen", "audit": "Audit-Log"},
        "ar": {"rule_engine": "محرك القواعد والأوزان", "generate": "إنشاء المخطط", "audit": "سجل التدقيق"},
    },
}


def scoring_config_with_defaults(config: Dict[str, Any] | None = None) -> Dict[str, float]:
    result = {**DEFAULT_SCORING_CONFIG}
    for name, value in (config or {}).items():
        if name not in result:
            continue
        try:
            result[name] = max(0.0, min(5.0, float(value)))
        except (TypeError, ValueError):
            continue
    return result


def validate_rule_payload(rule: Dict[str, Any] | None) -> Dict[str, Any]:
    rule = deepcopy(rule or {})
    errors: List[str] = []
    warnings: List[str] = []

    def values_of(value: Any) -> List[str]:
        if isinstance(value, (list, tuple, set)):
            raw = list(value)
        else:
            raw = re.split(r"[,;|\n]+", str(value or ""))
        return [str(x).strip() for x in raw if str(x).strip()]

    storage = rule.get("allowed_storage_type") or rule.get("storage_type")
    if storage:
        values = values_of(storage)
        invalid = [str(x) for x in values if not normalize_storage(x, default="")]
        if invalid:
            errors.append(f"Geçersiz storage_type: {', '.join(invalid)}")
    allowed = values_of(rule.get("allowed_categories"))
    blocked = values_of(rule.get("blocked_categories"))
    allowed_set = {str(x).strip().casefold() for x in allowed if str(x).strip()}
    blocked_set = {str(x).strip().casefold() for x in blocked if str(x).strip()}
    overlap = sorted(allowed_set & blocked_set)
    if overlap:
        errors.append(f"Aynı kategori hem izinli hem engelli: {', '.join(overlap)}")
    if rule.get("brand") and rule.get("brands"):
        warnings.append("brand ve brands birlikte gönderildi; brand önceliklidir.")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "rule": rule}
