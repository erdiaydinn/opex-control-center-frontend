from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import Any

from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    _load_modules,
    _module_from_root,
)
from app.modules.planogram.store_scan_fixture_layout import (
    build_scanned_fixture_layout_preview,
)


@lru_cache(maxsize=1)
def _load_scanned_optimizer() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "physical_optimizer_v6_scanned.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram scanned-store optimizer is unavailable")
    return _module_from_root("physical_optimizer_v6_scanned", root)


@lru_cache(maxsize=1)
def _load_picker_tour_v2() -> ModuleType:
    root, _, _, _ = _load_modules()
    path = root / "picker_tour_simulation_v2.py"
    if not path.is_file():
        raise PlanogramEngineUnavailable("Planogram Architecture V2 picker tour is unavailable")
    return _module_from_root("picker_tour_simulation_v2", root)


def _bounded_tour_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    """Project selected V2 basket routes without carrying raw identity or authority."""
    if raw.get("production_evidence") is not False or raw.get("preview_only") is not True:
        raise PlanogramEngineUnavailable("Planogram V2 tour violated evidence boundary")
    explained = []
    for index, row in enumerate(raw.get("explained_orders") or []):
        if index >= 3 or not isinstance(row, dict):
            break
        segments = []
        for segment in row.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            path = [
                [float(point[0]), float(point[1])]
                for point in segment.get("path_m") or []
                if isinstance(point, list) and len(point) >= 2
            ][:64]
            segments.append(
                {
                    "from": str(segment.get("from") or ""),
                    "to": str(segment.get("to") or ""),
                    "distance_m": float(segment.get("distance_m") or 0.0),
                    "path_m": path,
                }
            )
        explained.append(
            {
                "basket_ref": f"basket:{index + 1}",
                "sku_count": int(row.get("sku_count") or 0),
                "unique_stop_count": int(row.get("unique_stop_count") or 0),
                "distance_m": float(row.get("distance_m") or 0.0),
                "segments": segments,
            }
        )
    return {
        "simulation_version": raw.get("simulation_version"),
        "available": bool(raw.get("available")),
        "preview_only": True,
        "production_evidence": False,
        "routing_algorithm": raw.get("routing_algorithm"),
        "grid_resolution_m": raw.get("grid_resolution_m"),
        "orders": dict(raw.get("orders") or {}),
        "distance_m": dict(raw.get("distance_m") or {}),
        "explained_orders": explained,
        "architecture_fingerprint": raw.get("architecture_fingerprint"),
        "non_orthogonal_element_count": raw.get("non_orthogonal_element_count"),
        "non_orthogonal_module_count": raw.get("non_orthogonal_module_count"),
        "evidence_boundary": (
            "only three anonymized representative basket paths are projected for Digital Twin "
            "explainability; this remains repository preview evidence, not field proof"
        ),
    }


def generate_scanned_store_optimizer_preview(
    *,
    scan_payload: dict[str, Any],
    expected_scan_fingerprint: str,
    classifications: list[dict[str, Any]],
    operational_elements: list[dict[str, Any]],
    fixture_bindings: list[dict[str, Any]],
    products: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    review_note: str | None = None,
    max_candidates: int = 24,
    uncertainty_resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebuild reviewed scanned truth server-side, then run the preview V6 optimizer."""
    scanned_layout = build_scanned_fixture_layout_preview(
        scan_payload=scan_payload,
        expected_scan_fingerprint=expected_scan_fingerprint,
        classifications=classifications,
        operational_elements=operational_elements,
        fixture_bindings=fixture_bindings,
        review_note=review_note,
        uncertainty_resolutions=uncertainty_resolutions or [],
    )
    if not scanned_layout.get("available"):
        return {
            "available": False,
            "reason": "scanned_fixture_layout_unavailable",
            "scanned_layout": scanned_layout,
            "preview_only": True,
            "production_authority": False,
            "store_dna_authority": False,
            "physical_layout_authority": False,
            "installation_approved": False,
            "relocation_execution_allowed": False,
            "capex_approved": False,
            "global_optimum_claim": False,
            "field_evidence": False,
        }
    if not scanned_layout.get("layout_draft_ready"):
        return {
            "available": False,
            "reason": "scanned_fixture_layout_not_ready",
            "scanned_layout": scanned_layout,
            "preview_only": True,
            "production_authority": False,
            "store_dna_authority": False,
            "physical_layout_authority": False,
            "installation_approved": False,
            "relocation_execution_allowed": False,
            "capex_approved": False,
            "global_optimum_claim": False,
            "field_evidence": False,
        }

    optimizer = getattr(_load_scanned_optimizer(), "optimize_scanned_store", None)
    if not callable(optimizer):
        raise PlanogramEngineUnavailable(
            "Planogram scanned-store optimizer entrypoint is unavailable"
        )
    result = optimizer(
        products=products,
        layout=scanned_layout["physical_layout_preview"],
        store_dna=scanned_layout["reviewed_store_dna_v2_preview"],
        orders=orders,
        max_candidates=max_candidates,
    )
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Planogram scanned-store optimizer returned invalid data")
    for key in (
        "production_authority",
        "store_dna_authority",
        "installation_approved",
        "relocation_execution_allowed",
        "capex_approved",
        "global_optimum_claim",
        "field_evidence",
    ):
        if result.get(key) is not False:
            raise PlanogramEngineUnavailable(
                f"Planogram scanned-store optimizer violated {key} boundary"
            )

    if result.get("allowed") and isinstance(result.get("planogram"), dict):
        simulator = getattr(_load_picker_tour_v2(), "simulate_picker_tours_v2", None)
        if not callable(simulator):
            raise PlanogramEngineUnavailable(
                "Planogram Architecture V2 picker-tour entrypoint is unavailable"
            )
        raw_tour = simulator(
            result={"planogram": result["planogram"]},
            layout=result["planogram"],
            store_dna=scanned_layout["reviewed_store_dna_v2_preview"],
            orders=orders,
        )
        if not isinstance(raw_tour, dict):
            raise PlanogramEngineUnavailable("Planogram V2 picker tour returned invalid data")
        result["picker_tour_evidence_v2"] = _bounded_tour_evidence(raw_tour)

    return {
        "available": bool(result.get("allowed")),
        "preview_only": True,
        "scanned_layout": scanned_layout,
        "optimizer": result,
        "production_authority": False,
        "store_dna_authority": False,
        "physical_layout_authority": False,
        "installation_approved": False,
        "relocation_execution_allowed": False,
        "capex_approved": False,
        "global_optimum_claim": False,
        "field_evidence": False,
        "evidence_boundary": (
            "server recomputed the fingerprint-reviewed scan, explicit human uncertainty "
            "decisions, human catalog fixture bindings and Architecture V2 allocation search; "
            "this preview remains outside governed Store DNA, installation and production"
        ),
    }
