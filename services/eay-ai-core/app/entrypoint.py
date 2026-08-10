from __future__ import annotations

from .company_knowledge import router as company_knowledge_router
from .grounded_chat import router as grounded_chat_router
from .legal_api import router as legal_router
from .legal_knowledge import router as legal_knowledge_router
from .legal_review import router as legal_review_router
from .legal_verification import router as legal_verification_router
from .main import app
from .regulatory import router as regulatory_router


app.include_router(regulatory_router)
app.include_router(legal_router)
app.include_router(legal_review_router)
app.include_router(legal_verification_router)
app.include_router(legal_knowledge_router)
app.include_router(company_knowledge_router)
app.include_router(grounded_chat_router)
