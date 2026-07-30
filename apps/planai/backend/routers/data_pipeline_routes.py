from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, Body, HTTPException
from typing import Any, Dict, List

from services.abc_upload_service import parse_abc_upload
from services.catalog_abc_merge import merge_abc_with_catalog, load_master_catalog
from services.product_visual_resolver import resolve_product_visual

router = APIRouter(prefix="/data-pipeline", tags=["data-pipeline"])


@router.post("/abc/parse")
async def parse_abc(file: UploadFile = File(...), strict: bool = True):
    content = await file.read()
    return parse_abc_upload(content, file.filename, strict=strict)


@router.post("/abc/upload-merge")
async def upload_and_merge_abc(file: UploadFile = File(...), strict: bool = True):
    content = await file.read()
    parsed = parse_abc_upload(content, file.filename, strict=strict)
    if not parsed.get("success"):
        return parsed
    merged = merge_abc_with_catalog(parsed["rows"])
    return {
        "success": True,
        "file_name": file.filename,
        "abc": {k: v for k, v in parsed.items() if k != "rows"},
        **merged,
    }


@router.post("/abc/merge")
def merge_abc_rows(payload: Dict[str, Any] = Body(...)):
    rows = payload.get("rows") or payload.get("abc_rows") or []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows listesi gerekli")
    return merge_abc_with_catalog(rows)


@router.post("/visual/resolve")
def resolve_visual(payload: Dict[str, Any] = Body(...)):
    product = payload.get("product") or payload
    return resolve_product_visual(product)


@router.get("/catalog/status")
def catalog_status():
    rows = load_master_catalog()
    return {
        "success": True,
        "catalog_rows": len(rows),
        "with_physical_dimensions": sum(1 for r in rows if (r.get("width_cm") or r.get("product_width_in_cm")) and (r.get("height_cm") or r.get("product_height_in_cm")) and (r.get("depth_cm") or r.get("product_length_in_cm"))),
        "with_image": sum(1 for r in rows if r.get("image_url") or r.get("catalog_image_url") or r.get("pim_image_url")),
    }
