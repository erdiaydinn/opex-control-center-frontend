"""Deterministic replay of one V5 physical-layout candidate for preview.

The browser never supplies a replacement layout. It supplies only a fingerprint
previously emitted by the bounded V5 search. This module recomputes the search
from the same products/layout/Store DNA/baskets, verifies the fingerprint still
exists, reconstructs that candidate from the server-generated relocation label,
and reruns V4 allocation for the candidate geometry.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import physical_layout_optimizer_v5 as v5
import physical_optimizer_v4 as allocation_v4
from architecture_truth import layout_architecture_report

PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION = "physical-layout-candidate-preview-v1"
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def _candidate_layout(
    layout: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any] | None:
    if label == "baseline":
        return deepcopy(layout)
    if not label.startswith("swap::") or "<->" not in label:
        return None
    left_key, right_key = label.removeprefix("swap::").split("<->", 1)
    eligible = set(v5._relocation_pairs(layout))
    if (left_key, right_key) not in eligible and (right_key, left_key) not in eligible:
        return None
    return v5._swap_spatial_pose(layout, left_key, right_key)


def preview_physical_layout_candidate(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    layout_fingerprint: str,
    mode: str = "HYBRID",
    max_layout_candidates: int = v5.DEFAULT_LAYOUT_CANDIDATES,
    max_allocation_candidates: int = v5.DEFAULT_ALLOCATION_CANDIDATES,
    require_images: bool = True,
) -> dict[str, Any]:
    fingerprint = str(layout_fingerprint or "").strip().lower()
    if not FINGERPRINT_RE.fullmatch(fingerprint):
        return {
            "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
            "available": False,
            "reason": "layout_fingerprint_invalid",
            "production_authority": False,
            "execution_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    search = v5.optimize_physical_layout(
        products=deepcopy(products),
        layout=deepcopy(layout),
        store_dna=deepcopy(store_dna),
        orders=deepcopy(orders),
        mode=mode,
        max_layout_candidates=max_layout_candidates,
        max_allocation_candidates=max_allocation_candidates,
        require_images=require_images,
    )
    meta = search.get("physical_layout_optimizer") or {}
    candidates = meta.get("candidates") or []
    baseline_summary = next(
        (
            row
            for row in candidates
            if isinstance(row, dict)
            and str(row.get("label") or "") == "baseline"
            and row.get("production_authority") is False
        ),
        None,
    )
    summary = next(
        (
            row
            for row in candidates
            if isinstance(row, dict)
            and str(row.get("layout_fingerprint") or "").lower() == fingerprint
            and row.get("production_authority") is False
        ),
        None,
    )
    if summary is None:
        return {
            "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
            "available": False,
            "reason": "layout_fingerprint_not_in_recomputed_v5_search",
            "production_authority": False,
            "execution_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    candidate_layout = _candidate_layout(layout, label=str(summary.get("label") or ""))
    if candidate_layout is None or v5._layout_fingerprint(candidate_layout) != fingerprint:
        return {
            "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
            "available": False,
            "reason": "layout_candidate_reconstruction_failed",
            "production_authority": False,
            "execution_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    truth = layout_architecture_report(candidate_layout, store_dna)
    if not truth.get("valid"):
        return {
            "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
            "available": False,
            "reason": "layout_candidate_architecture_invalid",
            "blockers": list(truth.get("blockers") or []),
            "production_authority": False,
            "execution_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    candidate_result = allocation_v4.optimize_production_plan(
        products=deepcopy(products),
        layout=deepcopy(candidate_layout),
        store_dna=deepcopy(store_dna),
        orders=deepcopy(orders),
        mode=mode,
        require_images=require_images,
        max_candidates=max_allocation_candidates,
    )
    selected_meta = v5._selected_meta(candidate_result)
    if not isinstance(selected_meta.get("selected_objective"), dict):
        return {
            "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
            "available": False,
            "reason": "candidate_basket_objective_unavailable",
            "production_authority": False,
            "execution_authority": False,
            "installation_approved": False,
            "capex_approved": False,
        }

    return {
        "preview_version": PHYSICAL_LAYOUT_CANDIDATE_PREVIEW_VERSION,
        "available": True,
        "preview_only": True,
        "layout_fingerprint": fingerprint,
        "baseline_candidate_summary": deepcopy(baseline_summary),
        "candidate_summary": deepcopy(summary),
        "physical_layout": candidate_layout,
        "optimizer_result": candidate_result,
        "production_authority": False,
        "execution_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "capex_approved": False,
        "global_optimum_claim": False,
        "evidence_boundary": (
            "candidate was deterministically replayed from the current V5 bounded search; "
            "fixture move feasibility, CAPEX, installation and live KPI effects remain external"
        ),
    }
