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


@lru_cache(maxsize=1)
def _load_dxf_exporter() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "cad_dxf.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Measured Planogram DXF exporter is unavailable")
    return _module_from_root("cad_dxf", root)


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
        raise PlanogramEngineUnavailable(
            "Measured Planogram CAD export contract is unavailable"
        )
    result = build(
        result=optimizer_result,
        layout=layout,
        store_dna=store_dna,
        include_dxf=False,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Measured Planogram CAD exporter returned invalid data")
    if result.get("production_authority") is not False:
        raise PlanogramEngineUnavailable("CAD preview violated production-authority boundary")

    if include_dxf and result.get("available"):
        dxf_exporter = _load_dxf_exporter()
        build_dxf = getattr(dxf_exporter, "build_dxf_preview", None)
        if not callable(build_dxf):
            raise PlanogramEngineUnavailable(
                "Measured Planogram DXF export contract is unavailable"
            )
        dxf_result = build_dxf(
            result=optimizer_result,
            layout=layout,
            store_dna=store_dna,
        )
        if (
            not isinstance(dxf_result, dict)
            or dxf_result.get("production_authority") is not False
        ):
            raise PlanogramEngineUnavailable("DXF preview violated production-authority boundary")
        if not dxf_result.get("available"):
            raise PlanogramEngineUnavailable(
                "DXF preview could not be generated from measured geometry"
            )
        result = {
            **result,
            "dxf": dxf_result.get("dxf"),
            "dxf_included": True,
            "dxf_contract": dxf_result.get("contract"),
        }
    else:
        result = {**result, "dxf": None, "dxf_included": False}
    return result
