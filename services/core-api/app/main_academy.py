"""Production composition root for Platform Core + EAY Academy.

The Platform Core app remains untouched; Academy is composed as an independently
reviewable module and the Academy container entrypoint targets this module.
"""

from app.main import app
from app.modules.academy.router import router as academy_router

app.include_router(academy_router)
