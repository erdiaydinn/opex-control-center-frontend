# V1.8 Acceptance Checklist

## Backend
- [ ] `python -m pytest tests/test_v18_physics_scene.py`
- [ ] `/validate-strict-rules` storage violation = 0
- [ ] `unplaced_products.reason_code` var
- [ ] Scene payload: fixtures, shelves, placements, product visuals ayrı dönüyor

## Frontend
- [ ] `npm run build`
- [ ] Twin scene blank kalmıyor
- [ ] `ProductTile3D` ürün adını default yazmıyor
- [ ] SKU search seçilen rafa fokuslanıyor
- [ ] Camera presets çalışıyor
- [ ] Layout object select/move/rotate çalışıyor

## Bridge
- [ ] `localhost:5173/planogram` route korunuyor
- [ ] `localhost:5174` kapalıysa bridge error state
- [ ] `localhost:5174` açıksa iframe stable
