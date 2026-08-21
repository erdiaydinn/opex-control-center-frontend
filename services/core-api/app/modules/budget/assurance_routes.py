from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from .assurance import build_financial_assurance, build_financial_control_tower
from .domain import safe_csv_cell
from .permissions import BUDGET_EXPORT, BUDGET_VIEW_AUDIT, BudgetUnitOfWork, require_budget

router = APIRouter(prefix="/v1/budget", tags=["budget-control-tower"])
AuditSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_VIEW_AUDIT))]
ExportSession = Annotated[
    BudgetUnitOfWork,
    Depends(require_budget(BUDGET_EXPORT, all_cost_centers=True)),
]


@router.get("/control-tower")
async def get_control_tower(uow: AuditSession):
    return await build_financial_control_tower(uow)


@router.get("/assurance")
async def get_assurance(uow: AuditSession, event_limit: int = 200):
    return await build_financial_assurance(uow, event_limit)


@router.get("/reports/executive.csv")
async def export_executive_report(uow: ExportSession):
    report = await build_financial_control_tower(uow)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["metric", "value"])
    for key, value in report["summary"].items():
        writer.writerow([safe_csv_cell(key), safe_csv_cell(value)])
    writer.writerow([])
    writer.writerow(["cost_center", "budget", "actual", "commitment", "forecast", "forecast_variance"])
    for row in report["cost_centers"]:
        writer.writerow([
            safe_csv_cell(row.get("cost_center")),
            safe_csv_cell(row.get("budget")),
            safe_csv_cell(row.get("actual")),
            safe_csv_cell(row.get("commitment")),
            safe_csv_cell(row.get("forecast")),
            safe_csv_cell(row.get("forecast_variance")),
        ])
    writer.writerow([])
    writer.writerow(["finding_id", "severity", "cost_center", "category", "supplier", "reason", "evidence_fingerprint"])
    for row in report["findings"]:
        writer.writerow([
            safe_csv_cell(row.get("finding_id")),
            safe_csv_cell(row.get("severity")),
            safe_csv_cell(row.get("cost_center")),
            safe_csv_cell(row.get("category")),
            safe_csv_cell(row.get("supplier")),
            safe_csv_cell(row.get("reason")),
            safe_csv_cell(row.get("evidence_fingerprint")),
        ])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=eay-budget-executive-pack.csv"},
    )
