"""Platform Core ASGI composition with canonical Budget Intelligence routes."""

from app.main import app
from app.modules.budget.routes import router as budget_router

app.include_router(budget_router)
