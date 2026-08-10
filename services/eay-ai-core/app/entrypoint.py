from __future__ import annotations

from .main import app
from .regulatory import router as regulatory_router


app.include_router(regulatory_router)
