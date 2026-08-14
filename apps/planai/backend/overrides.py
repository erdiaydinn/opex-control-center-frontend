"""Minimal persistent product override store used by approval flows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


PATH = Path(__file__).resolve().parent / "data" / "product_overrides.json"


def _read() -> Dict[str, Any]:
    if not PATH.exists():
        return {}
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(data: Dict[str, Any]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_product_override(sku: str, values: Dict[str, Any]) -> Dict[str, Any]:
    data = _read()
    current = data.setdefault(str(sku), {})
    current.update({k: v for k, v in values.items() if v is not None})
    _write(data)
    return current


def apply_overrides_to_product(product: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(product or {})
    values = _read().get(str(result.get("sku") or result.get("SKU") or ""), {})
    result.update(values)
    return result
