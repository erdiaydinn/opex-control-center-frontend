from __future__ import annotations

from .company_knowledge import router as company_knowledge_router
from .employment_intelligence import router as employment_intelligence_router
from .employment_temporal_grounding import router as employment_grounding_router
from .eval_guardrails import router as eval_router
from .grounded_chat import router as grounded_chat_router
from .legal_api import router as legal_router
from .legal_knowledge import router as legal_knowledge_router
from .legal_review import router as legal_review_router
from .legal_verification import router as legal_verification_router
from .main import app
from .learning_export_guard import router as learning_export_router
from .model_registry import router as model_registry_router
from .observability import router as observability_router
from .payroll_engine import router as payroll_router
from .regulatory import router as regulatory_router
from .tool_execution import router as tool_execution_router
from .tool_intent import router as tool_intent_router
from .tool_router import router as tool_router
from .training_manifest import router as training_manifest_router
from .vision_audit import router as vision_audit_router
from .vision_provenance import router as vision_provenance_router
from .voice_ws_api import router as voice_ws_router


# The core app owns one gated learning-export wrapper. The entrypoint
# composes review/manifest/model routers without deleting or duplicating it.
app.include_router(regulatory_router)
app.include_router(legal_router)
app.include_router(legal_review_router)
app.include_router(legal_verification_router)
app.include_router(legal_knowledge_router)
app.include_router(company_knowledge_router)
app.include_router(employment_intelligence_router)
app.include_router(employment_grounding_router)
app.include_router(payroll_router)
app.include_router(grounded_chat_router)
app.include_router(tool_router)
app.include_router(tool_intent_router)
app.include_router(tool_execution_router)
# Deliberately do not expose bigquery_safe_executor.router. The executor classes are an
# internal implementation detail used only after vetted template, scope, semantic, schema
# and runtime-contract gates in tool_execution. Publishing /v1/bigquery/execute would let
# callers submit arbitrary read-only SQL and bypass those governed KPI/legal contracts.
app.include_router(eval_router)
app.include_router(observability_router)
app.include_router(vision_audit_router)
app.include_router(vision_provenance_router)
app.include_router(training_manifest_router)
app.include_router(learning_export_router)
app.include_router(model_registry_router)
app.include_router(voice_ws_router)
