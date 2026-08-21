import pytest
from fastapi import FastAPI

from app.entrypoint import (
    _LEGACY_PUBLIC_RETRIEVAL_PATHS,
    _PRODUCTION_UNSCOPED_PATHS,
    _quarantine_legacy_public_retrieval,
    _runtime_environment,
)


def _app_with_legacy_routes() -> FastAPI:
    candidate = FastAPI()

    @candidate.post("/v1/chat")
    def legacy_chat():
        return {"ok": True}

    @candidate.post("/v1/knowledge")
    def legacy_knowledge():
        return {"ok": True}

    @candidate.post("/v1/internal/grounded/retrieve")
    def governed_retrieval():
        return {"evidence": []}

    return candidate


def _app_with_all_unscoped_routes() -> FastAPI:
    candidate = FastAPI()
    for index, path in enumerate(sorted(_PRODUCTION_UNSCOPED_PATHS)):
        candidate.add_api_route(
            path,
            lambda: {"ok": True},
            methods=["POST"],
            name=f"unscoped_route_{index}",
        )

    @candidate.post("/v1/internal/grounded/retrieve")
    def governed_retrieval():
        return {"evidence": []}

    return candidate


def _paths(candidate: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "")) for route in candidate.routes}


def test_production_composition_removes_legacy_unscoped_retrieval_routes():
    candidate = _app_with_legacy_routes()

    _quarantine_legacy_public_retrieval(candidate, "production")

    paths = _paths(candidate)
    assert _LEGACY_PUBLIC_RETRIEVAL_PATHS.isdisjoint(paths)
    assert "/v1/internal/grounded/retrieve" in paths


def test_production_composition_removes_full_unscoped_surface():
    candidate = _app_with_all_unscoped_routes()

    _quarantine_legacy_public_retrieval(candidate, "production")

    paths = _paths(candidate)
    assert _PRODUCTION_UNSCOPED_PATHS.isdisjoint(paths)
    assert "/v1/internal/grounded/retrieve" in paths


def test_production_quarantine_is_idempotent():
    candidate = _app_with_all_unscoped_routes()

    _quarantine_legacy_public_retrieval(candidate, "production")
    _quarantine_legacy_public_retrieval(candidate, "production")

    assert _PRODUCTION_UNSCOPED_PATHS.isdisjoint(_paths(candidate))


def test_partial_legacy_route_inventory_fails_closed():
    candidate = FastAPI()

    @candidate.post("/v1/chat")
    def legacy_chat():
        return {"ok": True}

    with pytest.raises(
        RuntimeError,
        match="ai_core_legacy_retrieval_quarantine_incomplete",
    ):
        _quarantine_legacy_public_retrieval(candidate, "production")


def test_development_and_test_keep_local_research_routes():
    for environment in ("development", "test"):
        candidate = _app_with_all_unscoped_routes()
        _quarantine_legacy_public_retrieval(candidate, environment)
        assert _PRODUCTION_UNSCOPED_PATHS <= _paths(candidate)


def test_invalid_runtime_environment_fails_closed(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "prod-ish")

    with pytest.raises(RuntimeError, match="ai_core_environment_invalid"):
        _runtime_environment()
