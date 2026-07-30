# Release Gates

## V1.7.5 mandatory gates

- `python test_physics_engine_v174.py`
- `python test_release_gate_v175.py`
- Backend starts with `python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload`
- Frontend starts with `npm run dev -- --host 0.0.0.0 --port 5174`
- `/stores/{store_code}/readiness` returns a single source of truth for Store DNA, ABC, embedded catalog and merge state.
- Physical capacity cannot exceed shelf width, depth, height, or weight.
- Storage mismatch never produces placement.
- Unplaced report is not optional.
- Decision traces exist for placed and unplaced products.

## Production blockers

- Default layout is used in production mode.
- Catalog upload is requested from store users.
- 3D renders mock products instead of engine state.
- Any shelf utilization exceeds 100% without explicit diagnostic violation.
- Ice cream is placed outside `ALGIDA_FREEZER` / ICE_CREAM fixture.
- Chilled/frozen mismatch is allowed.
- Food and odor non-food share the same shelf.
