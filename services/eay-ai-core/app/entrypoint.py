from __future__ import annotations

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


def _signature(route) -> tuple[str, tuple[str, ...], str]:
    path = str(getattr(route, "path", ""))
    methods = tuple(sorted(getattr(route, "methods", set()) or set()))
    name = str(getattr(route, "name", ""))
    return path, methods, name


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


def compose_app() -> FastAPI:
    """Idempotently compose the production AI Core surface.

    Public product routes and cryptographically authenticated internal routes
    share one runtime, but tenant-scoped retrieval is only exposed through the
    dedicated internal router. A partially present router is treated as
    corruption rather than silently duplicating or weakening the API surface.
    """

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
    return app


app = compose_app()
