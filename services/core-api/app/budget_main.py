"""Platform Core ASGI composition with canonical commercial product routes."""

from app.main import app
from app.modules.budget.assurance_routes import router as budget_assurance_router
from app.modules.budget.planning_engine_routes import router as budget_planning_router
from app.modules.budget.routes import router as budget_router
from app.modules.planogram.execution_router import router as planogram_execution_router
from app.modules.planogram.optimizer_router import router as planogram_optimizer_router
from app.modules.planogram.router import router as planogram_router

app.include_router(budget_router)
app.include_router(budget_planning_router)
app.include_router(budget_assurance_router)
app.include_router(planogram_router)
app.include_router(planogram_optimizer_router)
app.include_router(planogram_execution_router)
