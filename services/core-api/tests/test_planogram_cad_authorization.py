from __future__ import annotations

import inspect

from app.core.permission_catalog import ALL_PERMISSION_KEYS
from app.modules.planogram.optimizer_router import router


def _route_permissions(path: str) -> set[str]:
    route = next(row for row in router.routes if getattr(row, "path", None) == path)
    required: set[str] = set()
    for dependency in route.dependant.dependencies:
        call = dependency.call
        if call is None:
            continue
        closure = inspect.getclosurevars(call)
        normalized = closure.nonlocals.get("normalized")
        if isinstance(normalized, str) and normalized:
            required.add(normalized)
    return required


def test_planogram_export_permission_is_canonical() -> None:
    assert "action:planogram:export" in ALL_PERMISSION_KEYS


def test_cad_preview_requires_create_and_export_authority() -> None:
    assert _route_permissions("/v1/planogram/cad-preview") == {
        "action:planogram:create",
        "action:planogram:export",
    }


def test_optimizer_preview_does_not_accidentally_gain_export_requirement() -> None:
    assert _route_permissions("/v1/planogram/optimize-preview") == {
        "action:planogram:create",
    }
