from __future__ import annotations

import csv
import io
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse

from .commands import run_command
from .domain import safe_csv_cell
from .evidence import emit_financial_event
from .imports import stage_import
from .ledger import post_invoice, resolve_reconciliation
from .permissions import (
    BUDGET_ACTIVATE_PLAN,
    BUDGET_APPROVE_REQUEST,
    BUDGET_CLOSE_PERIOD,
    BUDGET_CREATE_FORECAST,
    BUDGET_CREATE_PLAN,
    BUDGET_CREATE_PO,
    BUDGET_CREATE_REQUEST,
    BUDGET_EXPORT,
    BUDGET_IMPORT,
    BUDGET_MANAGE_COST_CENTERS,
    BUDGET_MANAGE_LINES,
    BUDGET_MANAGE_PERIODS,
    BUDGET_POST_INVOICE,
    BUDGET_RECONCILE,
    BUDGET_VIEW,
    BUDGET_VIEW_AUDIT,
    BudgetUnitOfWork,
    require_budget,
)
from .planning import (
    activate_plan,
    close_period,
    create_cost_center,
    create_forecast,
    create_line,
    create_period,
    create_plan,
)
from .procurement import create_po, create_request, decide_request
from .read_models import financial_events, variance_summary
from .schemas import (
    ApprovalDecision,
    BudgetLineCreate,
    CostCenterCreate,
    ForecastCreate,
    ImportStage,
    InvoiceCreate,
    PeriodCreate,
    PlanCreate,
    PurchaseOrderCreate,
    PurchaseRequestCreate,
    ReconciliationResolve,
)

router = APIRouter(prefix="/v1/budget", tags=["budget"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)]
ViewSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_VIEW))]
PlanCreateSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_CREATE_PLAN, all_cost_centers=True))]
PlanActivateSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_ACTIVATE_PLAN, all_cost_centers=True))]
PeriodSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_MANAGE_PERIODS, all_cost_centers=True))]
CostCenterSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_MANAGE_COST_CENTERS, all_cost_centers=True))]
LineSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_MANAGE_LINES, all_cost_centers=True))]
RequestSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_CREATE_REQUEST))]
ApprovalSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_APPROVE_REQUEST))]
POSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_CREATE_PO))]
InvoiceSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_POST_INVOICE))]
ForecastSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_CREATE_FORECAST))]
ImportSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_IMPORT, all_cost_centers=True))]
ReconciliationSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_RECONCILE))]
ClosePeriodSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_CLOSE_PERIOD, all_cost_centers=True))]
AuditSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_VIEW_AUDIT))]
ExportSession = Annotated[BudgetUnitOfWork, Depends(require_budget(BUDGET_EXPORT, all_cost_centers=True))]


@router.get("/summary")
async def get_summary(uow: ViewSession):
    return await variance_summary(uow)


@router.post("/plans", status_code=201)
async def post_plan(body: PlanCreate, key: IdempotencyKey, uow: PlanCreateSession):
    return await run_command(uow, key=key, operation="budget.plan.create", payload=body, perform=lambda: create_plan(uow, body))


@router.post("/plans/{plan_id}/activate")
async def post_plan_activation(plan_id: UUID, key: IdempotencyKey, uow: PlanActivateSession):
    return await run_command(uow, key=key, operation="budget.plan.activate", payload={"plan_id": plan_id}, perform=lambda: activate_plan(uow, plan_id))


@router.post("/periods", status_code=201)
async def post_period(body: PeriodCreate, key: IdempotencyKey, uow: PeriodSession):
    return await run_command(uow, key=key, operation="budget.period.create", payload=body, perform=lambda: create_period(uow, body))


@router.post("/cost-centers", status_code=201)
async def post_cost_center(body: CostCenterCreate, key: IdempotencyKey, uow: CostCenterSession):
    return await run_command(uow, key=key, operation="budget.cost_center.create", payload=body, perform=lambda: create_cost_center(uow, body))


@router.post("/lines", status_code=201)
async def post_line(body: BudgetLineCreate, key: IdempotencyKey, uow: LineSession):
    return await run_command(uow, key=key, operation="budget.line.create", payload=body, perform=lambda: create_line(uow, body))


@router.post("/requests", status_code=201)
async def post_request(body: PurchaseRequestCreate, key: IdempotencyKey, uow: RequestSession):
    return await run_command(uow, key=key, operation="budget.request.create", payload=body, perform=lambda: create_request(uow, body))


@router.post("/requests/{request_id}/decision")
async def post_request_decision(request_id: UUID, body: ApprovalDecision, key: IdempotencyKey, uow: ApprovalSession):
    return await run_command(uow, key=key, operation="budget.request.decision", payload={"request_id": request_id, "body": body}, perform=lambda: decide_request(uow, request_id, body))


@router.post("/purchase-orders", status_code=201)
async def post_purchase_order(body: PurchaseOrderCreate, key: IdempotencyKey, uow: POSession):
    return await run_command(uow, key=key, operation="budget.po.create", payload=body, perform=lambda: create_po(uow, body))


@router.post("/invoices", status_code=201)
async def post_invoice_route(body: InvoiceCreate, key: IdempotencyKey, uow: InvoiceSession):
    return await run_command(uow, key=key, operation="budget.invoice.post", payload=body, perform=lambda: post_invoice(uow, body))


@router.post("/forecasts", status_code=201)
async def post_forecast(body: ForecastCreate, key: IdempotencyKey, uow: ForecastSession):
    return await run_command(uow, key=key, operation="budget.forecast.create", payload=body, perform=lambda: create_forecast(uow, body))


@router.post("/imports/stage", status_code=201)
async def post_import(body: ImportStage, key: IdempotencyKey, uow: ImportSession):
    return await run_command(uow, key=key, operation="budget.import.stage", payload=body, perform=lambda: stage_import(uow, body))


@router.post("/reconciliation/{issue_id}/resolve")
async def post_reconciliation(issue_id: UUID, body: ReconciliationResolve, key: IdempotencyKey, uow: ReconciliationSession):
    return await run_command(uow, key=key, operation="budget.reconciliation.resolve", payload={"issue_id": issue_id, "body": body}, perform=lambda: resolve_reconciliation(uow, issue_id, body))


@router.post("/periods/{period_id}/close")
async def post_period_close(period_id: UUID, key: IdempotencyKey, uow: ClosePeriodSession):
    return await run_command(uow, key=key, operation="budget.period.close", payload={"period_id": period_id}, perform=lambda: close_period(uow, period_id))


@router.get("/financial-events")
async def get_financial_events(uow: AuditSession, limit: int = 200):
    return await financial_events(uow, limit)


@router.get("/export/variance.csv")
async def export_variance(uow: ExportSession):
    report = await variance_summary(uow)
    fields = ["budget_line_id", "cost_center", "category", "supplier_id", "supplier_name", "store_code", "budget_base_amount", "actual_base_amount", "committed_base_amount", "forecast_base_amount", "variance_base_amount"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in report["items"]:
        writer.writerow({field: safe_csv_cell(row.get(field)) for field in fields})
    await emit_financial_event(uow, event_type="VARIANCE_EXPORTED", aggregate_type="variance_export", aggregate_id=uuid4(), payload={"row_count": report["count"], "format": "csv"})
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=budget-variance.csv"})
