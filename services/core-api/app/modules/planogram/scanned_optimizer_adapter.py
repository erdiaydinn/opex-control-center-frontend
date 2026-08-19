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
) -> dict[str, Any]:
    """Rebuild scanned truth server-side, then run the non-authoritative V6 optimizer."""
    scanned_layout = build_scanned_fixture_layout_preview(
        scan_payload=scan_payload,
        expected_scan_fingerprint=expected_scan_fingerprint,
        classifications=classifications,
        operational_elements=operational_elements,
        fixture_bindings=fixture_bindings,
        review_note=review_note,
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
            "capex_approved": False,
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
            "capex_approved": False,
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
            "server recomputed the fingerprint-reviewed scan, human catalog fixture bindings "
            "and Architecture V2 allocation search; this preview remains outside governed "
            "Store DNA approval, installation and production authority"
        ),
    }
