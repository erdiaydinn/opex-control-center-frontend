from __future__ import annotations

from .legal_api import router as legal_router
from .main import app
from .regulatory import router as regulatory_router


app.include_router(regulatory_router)
app.include_router(legal_router)
