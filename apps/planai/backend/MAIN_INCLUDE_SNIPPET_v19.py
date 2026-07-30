# Add this to backend/main.py after app = FastAPI(...)
try:
    from routers.data_pipeline_routes import router as data_pipeline_router
    app.include_router(data_pipeline_router)
except Exception as exc:
    print(f"PLONAGRAM V1.9 data-pipeline router disabled: {exc}")
