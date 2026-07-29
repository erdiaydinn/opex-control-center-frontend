# PLONAGRAM OS V1.9.3 — Visual Product Twin Integration

## Purpose

Connect V1.9/V1.9.2 data pipeline to the frontend and 3D Twin product visual layer.

Core rule:

```text
ABC = image + stock + %Orders + %Stops + ABC + rank
Catalog = dimensions + storage + weight + case pack
Store DNA = fixtures + shelf/cooler/freezer capacity
Engine = target location
Location from ABC = delta only
```

## Backend files

```text
backend/services/visual_twin_payload.py
backend/routers/visual_twin_routes.py
backend/tests/test_v193_visual_twin_integration.py
backend/MAIN_INCLUDE_SNIPPET_v193.py
```

## Frontend files

```text
frontend/src/services/plonagramVisualTwinApi.js
frontend/src/components/DataPipeline/ABCUploadPanel.jsx
frontend/src/components/DataPipeline/ABCUploadPanel.css
frontend/src/components/Live3D/ProductTile3D.jsx
frontend/src/components/Live3D/ShelfProductTiles.jsx
```

## Backend integration

Copy backend files, then add to `main.py` after `app = FastAPI(...)`:

```python
try:
    from routers.visual_twin_routes import router as visual_twin_router
    app.include_router(visual_twin_router)
except Exception as exc:
    print(f"PLONAGRAM V1.9.3 visual-twin router disabled: {exc}")
```

## Test

```powershell
cd C:\Users\ErdiAydın\planai\backend
python .\tests\test_v193_visual_twin_integration.py
```

Expected:

```text
✅ V1.9.3 visual product twin integration tests passed
```

## Frontend integration

Import `ABCUploadPanel` in Command Center or Product Placement page:

```jsx
import ABCUploadPanel from "./components/DataPipeline/ABCUploadPanel.jsx";
```

Use:

```jsx
<ABCUploadPanel onPipelineReady={(payload) => setPipelinePayload(payload)} />
```

ProductTile3D/ShelfProductTiles should replace floating product text labels inside the Twin scene.

## Acceptance

- Product names are not default floating labels.
- Image URLs from ABC/Catalog render as product tiles.
- Missing images render fallback package tiles.
- Excluded products do not enter scene.
- Review products are visible in review/admin flow.