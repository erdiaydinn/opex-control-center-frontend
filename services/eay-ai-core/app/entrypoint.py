from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI

from .company_knowledge import router as company_knowledge_router
from .employment_intelligence import router as employment_intelligence_router
from .employment_temporal_grounding import router as employment_grounding_router
from .eval_guardrails import router as eval_router
from .grounded_chat import router as grounded_chat_router
from .legal_api import router as legal_router
from .legal_knowledge import router as legal_knowledge_router
from .legal_review import router as legal_review_router
from .legal_verification import router as legal_verification_router
from .learning_export_guard import router as learning_export_router
from .main import app
from .model_registry import router as model_registry_router
from .observability import router as observability_router
from .payroll_engine import router as payroll_router
from .regulatory import router as regulatory_router
from .tenant_grounded_retrieval import router as tenant_grounded_retrieval_router
from .tool_execution import router as tool_execution_router
from .tool_intent import router as tool_intent_router
from .tool_router import router as tool_router
from .training_manifest import router as training_manifest_router
from .vision_audit import router as vision_audit_router
from .vision_provenance import router as vision_provenance_router
from .voice_ws_api import router as voice_ws_router

_ALLOWED_ENVIRONMENTS = frozenset({"development", "test", "production"})
_LEGACY_PUBLIC_RETRIEVAL_PATHS = frozenset({"/v1/chat", "/v1/knowledge"})

# These routes are backed by the pre-tenant Store in main.py. They remain useful
# for local research, but exposing them in the production-composed app would
# bypass canonical tenant authority. Production therefore removes the whole
# unscoped retrieval + learning surface until a tenant-bound learning store and
# authorization contract exists.
_PRODUCTION_UNSCOPED_PATHS = frozenset(
    {
        *_LEGACY_PUBLIC_RETRIEVAL_PATHS,
        "/v1/feedback",
        "/v1/learning/export",
        "/v1/learning/candidates",
        "/v1/learning/candidates/{candidate_id}/teacher-review",
        "/v1/learning/candidates/{candidate_id}/{decision}",
        "/v1/learning/export-reviews/{candidate_id}",
    }
)


def _signature(route) -> tuple[str, tuple[str, ...], str]:
    path = str(getattr(route, "path", ""))
    methods = tuple(sorted(getattr(route, "methods", set()) or set()))
    name = str(getattr(route, "name", ""))
    return path, methods, name


def _route_paths(target: FastAPI) -> set[str]:
    return {str(getattr(route, "path", "")) for route in target.routes}


def _include_router_once(target: FastAPI, router: APIRouter) -> None:
    expected = {_signature(route) for route in router.routes}
    if not expected:
        return
    present = {_signature(route) for route in target.routes}
    overlap = expected & present
    if overlap == expected:
        return
    if overlap:
        raise RuntimeError("ai_core_partial_router_composition_detected")
    target.include_router(router)


def _runtime_environment() -> str:
    environment = os.getenv("EAY_ENVIRONMENT", "development").strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise RuntimeError("ai_core_environment_invalid")
    return environment


def _quarantine_unscoped_production_routes(
    target: FastAPI,
    environment: str,
) -> None:
    """Remove tenant-unaware retrieval/learning routes from production.

    The inherited ``main.Store`` has no tenant discriminator for interactions,
    feedback, learning candidates or export reviews. Those local-research paths
    must not become a cross-company production data surface merely because the
    production app composes newer tenant-aware routers alongside them.

    The operation is intentionally idempotent so repeated composition is safe.
    Development/test retains the local learning workflow for repository tests
    and offline research.
    """

    if environment != "production":
        return

    target.router.routes = [
        route
        for route in target.router.routes
        if str(getattr(route, "path", "")) not in _PRODUCTION_UNSCOPED_PATHS
    ]

    remaining = _route_paths(target) & _PRODUCTION_UNSCOPED_PATHS
    if remaining:
        raise RuntimeError("ai_core_unscoped_route_quarantine_incomplete")


def _quarantine_legacy_public_retrieval(
    target: FastAPI,
    environment: str,
) -> None:
    """Preserve the original legacy quarantine API atop the stronger boundary.

    The historical contract treats a partially composed legacy public retrieval
    surface as corruption: both old routes must be present together or both must
    already be absent. Keep that invariant because it detects route-composition
    drift before the stronger production quarantine removes all tenant-unaware
    retrieval and learning routes.
    """

    if environment != "production":
        return

    present = _route_paths(target) & _LEGACY_PUBLIC_RETRIEVAL_PATHS
    if present and present != _LEGACY_PUBLIC_RETRIEVAL_PATHS:
        raise RuntimeError("ai_core_legacy_retrieval_quarantine_incomplete")

    _quarantine_unscoped_production_routes(target, environment)


def compose_app() -> FastAPI:
    """Idempotently compose the production AI Core surface.

    Public product routes and cryptographically authenticated internal routes
    share one runtime, but tenant-scoped retrieval is only exposed through the
    dedicated internal router. A partially present router is treated as
    corruption rather than silently duplicating or weakening the API surface.
    Tenant-unaware retrieval and learning endpoints are development/test only
    and are removed from the production route inventory.
    """

    environment = _runtime_environment()
    routers = (
        regulatory_router,
        legal_router,
        legal_review_router,
        legal_verification_router,
        legal_knowledge_router,
        company_knowledge_router,
        employment_intelligence_router,
        employment_grounding_router,
        payroll_router,
        grounded_chat_router,
        tenant_grounded_retrieval_router,
        tool_router,
        tool_intent_router,
        tool_execution_router,
        # Deliberately do not expose bigquery_safe_executor.router. Arbitrary
        # read-only SQL would bypass governed KPI/legal scope contracts.
        eval_router,
        observability_router,
        vision_audit_router,
        vision_provenance_router,
        training_manifest_router,
        learning_export_router,
        model_registry_router,
        voice_ws_router,
    )
    for router in routers:
        _include_router_once(app, router)
    _quarantine_legacy_public_retrieval(app, environment)
    return app


app = compose_app()
