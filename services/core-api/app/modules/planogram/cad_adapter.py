"""Fail-closed Core adapter for measured Planogram CAD preview exports."""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import Any

from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    _load_modules,
    _module_from_root,
)


@lru_cache(maxsize=1)
def _load_cad_exporter() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "cad_drawing.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Measured Planogram CAD exporter is unavailable")
    return _module_from_root("cad_drawing", root)


def generate_cad_preview_document(
    *,
    optimizer_result: dict[str, Any],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    include_dxf: bool = False,
) -> dict[str, Any]:
    """Render a selected preview plan as SVG/DXF without granting field authority."""
    exporter = _load_cad_exporter()
    build = getattr(exporter, "build_cad_preview", None)
    if not callable(build):
        raise PlanogramEngineUnavailable("Measured Planogram CAD export contract is unavailable")
    result = build(
        result=optimizer_result,
        layout=layout,
        store_dna=store_dna,
        include_dxf=include_dxf,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Measured Planogram CAD exporter returned invalid data")
    if result.get("production_authority") is not False:
        raise PlanogramEngineUnavailable("CAD preview violated production-authority boundary")
    return result
