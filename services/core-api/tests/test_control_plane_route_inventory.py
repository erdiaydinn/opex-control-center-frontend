from fastapi.routing import APIRoute

from app.core.authorization import require_control_plane_admin
from app.main import app


def _dependency_calls(route: APIRoute) -> set[object]:
    calls: set[object] = set()
    stack = list(route.dependant.dependencies)

    while stack:
        dependency = stack.pop()
        if dependency.call is not None:
            calls.add(dependency.call)
        stack.extend(dependency.dependencies)

    return calls


def test_all_internal_platform_routes_use_canonical_control_plane_authority() -> None:
    """Prevent future /v1/platform/* routes from silently becoming tenant-local admin APIs."""
    platform_routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/v1/platform/")
    ]

    assert platform_routes, "Expected at least one internal /v1/platform/* route"

    unguarded = [
        f"{','.join(sorted(route.methods or []))} {route.path}"
        for route in platform_routes
        if require_control_plane_admin not in _dependency_calls(route)
    ]

    assert not unguarded, (
        "Internal control-plane routes must use the canonical "
        "require_control_plane_admin authority; unguarded routes: "
        + "; ".join(sorted(unguarded))
    )


def test_current_control_plane_inventory_is_explicit() -> None:
    """Make additions to the internal control-plane surface an intentional review event."""
    inventory = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/v1/platform/")
        for method in (route.methods or set())
    }

    assert inventory == {
        ("GET", "/v1/platform/authority"),
        ("GET", "/v1/platform/health"),
    }
