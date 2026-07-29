
from fastapi import APIRouter
from services.security_scan import latest_scan, run_osv_scan

router = APIRouter(prefix="/system", tags=["security"])

@router.post("/security-scan")
def security_scan():
    return run_osv_scan(".")

@router.get("/security-scan/latest")
def security_scan_latest():
    return latest_scan()
