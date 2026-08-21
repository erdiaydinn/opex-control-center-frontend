"""Platform Core ASGI composition with canonical commercial product routes."""

from app.main import app
from app.modules.audit.evidence_object_routes import router as audit_evidence_object_router
from app.modules.audit.intelligence_routes import router as audit_intelligence_router
from app.modules.audit.privacy_routes import router as audit_privacy_router
from app.modules.audit.routes import router as audit_router
from app.modules.audit.video_routes import router as audit_video_router
from app.modules.audit.visit_routes import router as audit_visit_router
from app.modules.budget.planning_engine_routes import router as budget_planning_router
from app.modules.budget.routes import router as budget_router
from app.modules.planogram.execution_router import router as planogram_execution_router
from app.modules.planogram.optimizer_router import router as planogram_optimizer_router
from app.modules.planogram.router import router as planogram_router

app.include_router(audit_router)
app.include_router(audit_visit_router)
app.include_router(audit_intelligence_router)
app.include_router(audit_evidence_object_router)
app.include_router(audit_privacy_router)
app.include_router(audit_video_router)
app.include_router(budget_router)
app.include_router(budget_planning_router)
app.include_router(planogram_router)
app.include_router(planogram_optimizer_router)
app.include_router(planogram_execution_router)