
from fastapi import APIRouter, File, UploadFile
from vision.photo_parser import analyze_planogram_photo

router = APIRouter(prefix="/vision", tags=["vision"])

@router.post("/photo-compliance")
async def photo_compliance(file: UploadFile = File(...)):
    image_bytes = await file.read()
    return analyze_planogram_photo(image_bytes)
