"""Thin adapter to the canonical PlanAI deterministic/physical-truth engine.

The implementation deliberately does not copy placement rules into Core API.
`apps/planai/backend` remains the single source of truth; this module only
loads that reviewed library and exposes a narrow fail-closed product boundary.
"""

from __future__ import annotations

import importlib
import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


class PlanogramEngineUnavailable(RuntimeError):
    """Raised when the canonical PlanAI library cannot be loaded safely."""


def _candidate_roots() -> tuple[Path, ...]:
    configured = os.getenv("OPEX_PLANOGRAM_ENGINE_ROOT", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))

    # Source checkout: services/core-api/app/modules/planogram -> repository root.
    try:
        candidates.append(Path(__file__).resolve().parents[5] / "apps" / "planai" / "backend")
    except IndexError:
        pass

    # Immutable Core API image target.
    candidates.append(Path("/opt/eay/planai"))

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def _resolve_engine_root() -> Path:
    required = ("engine.py", "physical_truth.py", "physical_engine.py")
    for root in _candidate_roots():
        if all((root / filename).is_file() for filename in required):
            return root
    raise PlanogramEngineUnavailable("Canonical Planogram engine source is unavailable")


def _module_from_root(name: str, root: Path) -> ModuleType:
    existing = sys.modules.get(name)
    if existing is not None:
        source = getattr(existing, "__file__", None)
        if source is None or Path(source).resolve().parent != root:
            raise PlanogramEngineUnavailable(
                f"Unsafe Python module collision while loading Planogram dependency: {name}"
            )
        return existing

    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    module = importlib.import_module(name)
    source = getattr(module, "__file__", None)
    if source is None or Path(source).resolve().parent != root:
        raise PlanogramEngineUnavailable(
            f"Planogram dependency resolved outside canonical engine root: {name}"
        )
    return module


@lru_cache(maxsize=1)
def _load_modules() -> tuple[Path, ModuleType, ModuleType, ModuleType]:
    root = _resolve_engine_root()
    engine = _module_from_root("engine", root)
    physical_truth = _module_from_root("physical_truth", root)
    physical_engine = _module_from_root("physical_engine", root)
    return root, engine, physical_truth, physical_engine


def engine_status() -> dict[str, Any]:
    """Return non-sensitive deployment status for the canonical library."""
    _, engine, physical_truth, physical_engine = _load_modules()
    return {
        "available": True,
        "contract": "physical-truth-gated-deterministic-v1",
        "foundation": "deterministic-best-fit-v4.2",
        "library_mode": True,
        "legacy_bridge_enabled": False,
        "production_ai_dimensions_allowed": False,
        "source_modules": {
            "engine": Path(engine.__file__ or "").name,
            "physical_truth": Path(physical_truth.__file__ or "").name,
            "physical_engine": Path(physical_engine.__file__ or "").name,
        },
    }


def generate_preview(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    """Evaluate request-supplied candidate data through the canonical engine.

    This is intentionally only a preview. The caller cannot turn request data
    into production authority; the route layer always marks the result as
    unattested and non-releasable.
    """
    _, _, _, physical_engine = _load_modules()
    generator = getattr(physical_engine, "generate_production_plan", None)
    if not callable(generator):
        raise PlanogramEngineUnavailable("Canonical production Planogram entrypoint is unavailable")

    result = generator(products, layout, store_dna, mode=mode)
    if not isinstance(result, dict):
        raise PlanogramEngineUnavailable("Canonical Planogram engine returned an invalid result")
    return result
