from fastapi import FastAPI

from app.entrypoint import (
    _PRODUCTION_UNSCOPED_PATHS,
    _quarantine_unscoped_production_routes,
)


EXPECTED_UNSCOPED_PATHS = {
    "/v1/chat",
    "/v1/knowledge",
    "/v1/feedback",
    "/v1/learning/export",
    "/v1/learning/candidates",
    "/v1/learning/candidates/{candidate_id}/teacher-review",
    "/v1/learning/candidates/{candidate_id}/{decision}",
    "/v1/learning/export-reviews/{candidate_id}",
}


def _route_paths(target: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "")) for route in target.routes}


def _app_with_unscoped_routes() -> FastAPI:
    target = FastAPI()

    async def handler():
        return {"ok": True}

    for path in sorted(EXPECTED_UNSCOPED_PATHS):
        target.add_api_route(path, handler, methods=["GET"])
    target.add_api_route(
        "/v1/internal/grounded/retrieve",
        handler,
        methods=["POST"],
    )
    target.add_api_route("/health", handler, methods=["GET"])
    return target


def test_production_quarantine_covers_unscoped_learning_surface() -> None:
    assert _PRODUCTION_UNSCOPED_PATHS == EXPECTED_UNSCOPED_PATHS

    target = _app_with_unscoped_routes()
    _quarantine_unscoped_production_routes(target, "production")

    paths = _route_paths(target)
    assert EXPECTED_UNSCOPED_PATHS.isdisjoint(paths)
    assert "/v1/internal/grounded/retrieve" in paths
    assert "/health" in paths

    # Repeated composition must stay safe instead of reintroducing routes.
    _quarantine_unscoped_production_routes(target, "production")
    assert EXPECTED_UNSCOPED_PATHS.isdisjoint(_route_paths(target))


def test_development_and_test_keep_local_research_routes() -> None:
    for environment in ("development", "test"):
        target = _app_with_unscoped_routes()
        _quarantine_unscoped_production_routes(target, environment)
        assert EXPECTED_UNSCOPED_PATHS.issubset(_route_paths(target))
