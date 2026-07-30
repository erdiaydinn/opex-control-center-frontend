# Add after app = FastAPI(...)
try:
    from routers.visual_twin_routes import router as visual_twin_router
    app.include_router(visual_twin_router)
except Exception as exc:
    print(f"PLONAGRAM V1.9.3 visual-twin router disabled: {exc}")