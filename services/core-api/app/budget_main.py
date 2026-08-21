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
from app.modules.planogram.commercial_router import router as planogram_commercial_router
from app.modules.planogram.economics_router import router as planogram_economics_router
from app.modules.planogram.execution_router import router as planogram_execution_router
from app.modules.planogram.optimizer_router import router as planogram_optimizer_router
from app.modules.planogram.realogram_router import router as planogram_realogram_router
from app.modules.planogram.retail_intelligence_router import (
    router as planogram_retail_intelligence_router,
)
from app.modules.planogram.router import router as planogram_router
from app.modules.planogram.scenario_router import router as planogram_scenario_router
from app.modules.planogram.shelf_scan_router import router as planogram_shelf_scan_router
from app.modules.planogram.store_scan_fixture_router import (
    router as planogram_store_scan_fixture_router,
)
from app.modules.planogram.store_scan_review_router import (
    router as planogram_store_scan_review_router,
)

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
app.include_router(planogram_shelf_scan_router)
app.include_router(planogram_economics_router)
app.include_router(planogram_scenario_router)
app.include_router(planogram_store_scan_review_router)
app.include_router(planogram_store_scan_fixture_router)
app.include_router(planogram_commercial_router)
app.include_router(planogram_realogram_router)
app.include_router(planogram_retail_intelligence_router)
