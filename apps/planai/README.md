# Planogram Studio

Planogram Studio is the fixture-first, constraint-first planning module inside OPEX Control Center.

## Runtime

Backend:

    cd apps/planai/backend
    python -m pip install -r requirements.txt
    python -m uvicorn main:app --host 0.0.0.0 --port 8001

Frontend:

    cd apps/planai/frontend
    npm install
    npm run dev -- --host 0.0.0.0 --port 5174

The frontend uses VITE_API_BASE_URL for the backend base URL; default is http://127.0.0.1:8001.

## Source of truth

catalog → normalization → deterministic engine → strict validation → 2D/3D renderers

3D does not invent products, pallets, routes or capacity. Layout Architect refuses save while an object is outside the measured boundary or collides with another object.

Production data, databases, credentials, caches and backup folders are intentionally not committed.