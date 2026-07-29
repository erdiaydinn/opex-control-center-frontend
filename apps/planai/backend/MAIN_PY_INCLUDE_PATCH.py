
# Add these lines to your FastAPI main.py
from routers.system_security import router as system_security_router
from routers.ai_council_router import router as ai_council_router
from routers.photo_compliance import router as photo_compliance_router

app.include_router(system_security_router)
app.include_router(ai_council_router)
app.include_router(photo_compliance_router)
