from fastapi import APIRouter
from ._storage_v1 import read_json

router = APIRouter(prefix="/core/object-library", tags=["core-object-library"])

@router.get("")
def get_object_library():
    return {"success": True, "library": read_json("canonical_objects.json", {"objects": []})}