import inspect

from fastapi.params import Depends as DependsParam
from fastapi.routing import APIRoute

from app.core.authorization import require_control_plane_admin
from app.core.security import (
    require_platform_admin,
    require_super_admin,
    require_viewer,
)
from app.main import app

EXPECTED_RBAC = {
    ("GET", "/health/live"): None,
    ("GET", "/health/ready"): None,

    ("GET", "/v1/context"): require_viewer,

    ("GET", "/v1/audit/events"): require_platform_admin,
    ("GET", "/v1/platform/authority"): require_control_plane_admin,
    ("GET", "/v1/platform/health"): require_control_plane_admin,

    ("GET", "/v1/admin/tenant"): require_platform_admin,
    ("PATCH", "/v1/admin/tenant"): require_super_admin,

    ("GET", "/v1/admin/roles"): require_platform_admin,

    ("GET", "/v1/admin/members"): require_platform_admin,
    ("POST", "/v1/admin/members"): require_super_admin,
    ("PATCH", "/v1/admin/members/{membership_id}"): require_super_admin,
}


def _route_dependencies(route: APIRoute) -> set[object]:
    dependencies = set()

    for parameter in inspect.signature(route.endpoint).parameters.values():
        default = parameter.default

        if isinstance(default, DependsParam) and default.dependency is not None:
            dependencies.add(default.dependency)

    return dependencies


def test_endpoint_rbac_matrix_is_complete():
    actual_routes = {}

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        if not (
            route.path.startswith("/health/")
            or route.path.startswith("/v1/")
        ):
            continue

        for method in route.methods:
            actual_routes[(method, route.path)] = route

    assert set(actual_routes) == set(EXPECTED_RBAC)

    for route_key, expected_guard in EXPECTED_RBAC.items():
        route = actual_routes[route_key]
        dependencies = _route_dependencies(route)

        if expected_guard is None:
            assert not {
                require_viewer,
                require_platform_admin,
                require_super_admin,
                require_control_plane_admin,
            }.intersection(dependencies)
        else:
            assert expected_guard in dependencies, (
                f"{route_key} does not use its required RBAC guard"
            )
