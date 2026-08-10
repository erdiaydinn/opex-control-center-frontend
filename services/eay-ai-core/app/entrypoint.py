from __future__ import annotations

from .company_knowledge import router as company_knowledge_router
from .eval_guardrails import router as eval_router
from .grounded_chat import router as grounded_chat_router
from .legal_api import router as legal_router
from .legal_knowledge import router as legal_knowledge_router
from .legal_review import router as legal_review_router
from .legal_verification import router as legal_verification_router
from .main import app
from .observability import router as observability_router
from .regulatory import router as regulatory_router
from .tool_intent import router as tool_intent_router
from .tool_router import router as tool_router


app.include_router(regulatory_router)
app.include_router(legal_router)
app.include_router(legal_review_router)
app.include_router(legal_verification_router)
app.include_router(legal_knowledge_router)
app.include_router(company_knowledge_router)
app.include_router(grounded_chat_router)
app.include_router(tool_router)
app.include_router(tool_intent_router)
app.include_router(eval_router)
app.include_router(observability_router)
