from fastapi import APIRouter, HTTPException, Query
from ._storage_v1 import read_json

router = APIRouter(prefix="/core/stores", tags=["core-stores"])

def load_stores():
    return [s for s in read_json("stores_master.json", []) if s.get("store_code")]

@router.get("")
def list_stores(
    q: str = "",
    city: str = "",
    region: str = "",
    store_type: str = "",
    limit: int = Query(500, ge=1, le=1000)
):
    ql = q.lower().strip()
    city_l = city.lower().strip()
    region_l = region.lower().strip()
    type_l = store_type.lower().strip()
    stores = load_stores()

    def ok(s):
        hay = " ".join(str(s.get(k, "")) for k in [
            "store_code", "vendor_id", "store_name", "display_name",
            "city", "district", "region", "zone", "regional_executive", "regional_manager"
        ]).lower()
        if ql and ql not in hay:
            return False
        if city_l and city_l not in str(s.get("city", "")).lower():
            return False
        if region_l and region_l not in str(s.get("region", "")).lower():
            return False
        if type_l and type_l not in str(s.get("store_type", "")).lower():
            return False
        return True

    filtered = [s for s in stores if ok(s)][:limit]
    return {
        "success": True,
        "total": len(stores),
        "count": len(filtered),
        "stores": filtered,
        "cities": sorted({s.get("city") for s in stores if s.get("city")}),
        "regions": sorted({s.get("region") for s in stores if s.get("region")}),
        "types": sorted({s.get("store_type") for s in stores if s.get("store_type")}),
    }

@router.get("/{store_code}")
def get_store(store_code: str):
    needle = store_code.lower().strip()
    for s in load_stores():
        if str(s.get("store_code", "")).lower() == needle or str(s.get("vendor_id", "")).lower() == needle:
            return {"success": True, "store": s}
    raise HTTPException(status_code=404, detail="Depo bulunamadı.")