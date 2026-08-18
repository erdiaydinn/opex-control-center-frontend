"""Master 52-55 UAT, penetration, accessibility, and language acceptance matrix."""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_MODULES = {
    "workforce_standalone",
    "inventory_standalone",
    "dockos_standalone",
    "academy_standalone",
}
REQUIRED_CROSS = {
    "workforce_kpi",
    "field_planogram",
    "dock_inventory",
    "hiring_workforce_academy",
    "budget_operations",
    "jarvis_all_entitled_modules",
}
REQUIRED_PEN = {
    "cross_tenant_api_rls_cache_object",
    "ai_prompt_tool_authorization",
    "admin_control_plane",
}
REQUIRED_LANGS = {
    "tr",
    "en",
    "de",
    "ar_rtl",
    "fr",
    "es",
    "it",
    "nl",
    "pl",
    "pt_br",
}


def load_acceptance_matrix(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported acceptance matrix")
    if not set(data["module_uat"]) >= REQUIRED_MODULES:
        raise ValueError("standalone module UAT matrix incomplete")
    if not set(data["cross_module_uat"]) >= REQUIRED_CROSS:
        raise ValueError("cross-module UAT matrix incomplete")
    if not set(data["security_penetration"]) >= REQUIRED_PEN:
        raise ValueError("security penetration matrix incomplete")
    if not set(data["accessibility_language"]) >= REQUIRED_LANGS:
        raise ValueError("ten-language field acceptance incomplete")
    return data
