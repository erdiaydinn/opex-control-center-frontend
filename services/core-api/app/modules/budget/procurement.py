from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .evidence import emit_financial_event
from .permissions import BudgetUnitOfWork
from .schemas import ApprovalDecision, PurchaseOrderCreate, PurchaseRequestCreate


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def create_request(uow: BudgetUnitOfWork, body: PurchaseRequestCreate) -> dict[str, object]:
    line_result = await uow.session.execute(text("""SELECT l.*,p.status plan_status,fp.status period_status FROM budget_line l JOIN budget_plan p ON p.tenant_id=l.tenant_id AND p.id=l.plan_id JOIN fiscal_period fp ON fp.tenant_id=l.tenant_id AND fp.id=l.fiscal_period_id WHERE l.tenant_id=:tenant AND l.id=:line AND l.fiscal_period_id=:period AND l.cost_center_id=:center FOR UPDATE OF l"""), {"tenant": uow.tenant_id, "line": body.budget_line_id, "period": body.fiscal_period_id, "center": body.cost_center_id})
    line = line_result.first()
    if line is None:
        raise HTTPException(status_code=404, detail="Budget Line not found")
    if line.plan_status != "ACTIVE" or line.period_status != "OPEN":
        raise HTTPException(status_code=409, detail="Purchase Request requires ACTIVE plan and OPEN period")
    exposure_result = await uow.session.execute(text("""SELECT COALESCE((SELECT SUM(base_amount) FROM actual WHERE tenant_id=:tenant AND budget_line_id=:line),0) + COALESCE((SELECT SUM(remaining_base_amount) FROM commitment WHERE tenant_id=:tenant AND budget_line_id=:line AND status='OPEN'),0) + COALESCE((SELECT SUM(r.requested_base_amount) FROM purchase_request r WHERE r.tenant_id=:tenant AND r.budget_line_id=:line AND r.status IN ('SUBMITTED','APPROVED') AND NOT EXISTS (SELECT 1 FROM purchase_order p WHERE p.tenant_id=r.tenant_id AND p.purchase_request_id=r.id AND p.status <> 'CANCELED')),0) amount"""), {"tenant": uow.tenant_id, "line": body.budget_line_id})
    exposure = Decimal(str(exposure_result.scalar_one()))
    if exposure + body.requested_base_amount > line.budget_base_amount:
        raise HTTPException(status_code=409, detail="Purchase Request exceeds Budget Line")
    result = await uow.session.execute(text("""INSERT INTO purchase_request(tenant_id,budget_line_id,fiscal_period_id,cost_center_id,source_system,external_ref,supplier_id,supplier_name,category,store_code,description,requested_base_amount,created_by) VALUES (:tenant,:line,:period,:center,'MANUAL',:external_ref,:supplier_id,:supplier_name,:category,:store,:description,:amount,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "line": body.budget_line_id, "period": body.fiscal_period_id, "center": body.cost_center_id, "external_ref": body.external_ref, "supplier_id": body.supplier_id, "supplier_name": body.supplier_name, "category": body.category, "store": body.store_code, "description": body.description, "amount": body.requested_base_amount, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="PURCHASE_REQUEST_CREATED", aggregate_type="purchase_request", aggregate_id=item["id"], cost_center_id=item["cost_center_id"], payload=item)
    return item


async def decide_request(uow: BudgetUnitOfWork, request_id: UUID, body: ApprovalDecision) -> dict[str, object]:
    result = await uow.session.execute(text("SELECT * FROM purchase_request WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": request_id})
    pr = result.first()
    if pr is None:
        raise HTTPException(status_code=404, detail="Purchase Request not found")
    if pr.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Purchase Request is not pending")
    if pr.created_by == uow.actor:
        raise HTTPException(status_code=409, detail="Purchase Request requires four-eyes approval")
    await uow.session.execute(text("""INSERT INTO approval(tenant_id,purchase_request_id,fiscal_period_id,cost_center_id,step,decision,actor_id,reason) VALUES (:tenant,:request,:period,:center,1,:decision,:actor,:reason)"""), {"tenant": uow.tenant_id, "request": request_id, "period": pr.fiscal_period_id, "center": pr.cost_center_id, "decision": body.decision, "actor": uow.actor, "reason": body.reason})
    status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    update = await uow.session.execute(text("""UPDATE purchase_request SET status=:status, approved_at=CASE WHEN :status='APPROVED' THEN now() ELSE approved_at END WHERE tenant_id=:tenant AND id=:id RETURNING *"""), {"tenant": uow.tenant_id, "id": request_id, "status": status})
    item = _row(update.one())
    await emit_financial_event(uow, event_type=f"PURCHASE_REQUEST_{status}", aggregate_type="purchase_request", aggregate_id=item["id"], cost_center_id=item["cost_center_id"], payload={"status": status, "decision": body.decision, "reason": body.reason})
    return item


async def create_po(uow: BudgetUnitOfWork, body: PurchaseOrderCreate) -> dict[str, object]:
    result = await uow.session.execute(text("""SELECT r.*,a.actor_id approver FROM purchase_request r JOIN approval a ON a.tenant_id=r.tenant_id AND a.purchase_request_id=r.id AND a.step=1 AND a.decision='APPROVE' WHERE r.tenant_id=:tenant AND r.id=:id FOR UPDATE OF r"""), {"tenant": uow.tenant_id, "id": body.purchase_request_id})
    pr = result.first()
    if pr is None or pr.status != "APPROVED":
        raise HTTPException(status_code=409, detail="PO requires approved Purchase Request")
    if pr.approver == uow.actor:
        raise HTTPException(status_code=409, detail="Approver cannot create PO")
    mismatch = body.base_amount != pr.requested_base_amount or (pr.supplier_id is not None and body.supplier_id != pr.supplier_id)
    po_result = await uow.session.execute(text("""INSERT INTO purchase_order(tenant_id,purchase_request_id,budget_line_id,fiscal_period_id,cost_center_id,source_system,external_id,supplier_id,supplier_name,category,store_code,base_amount,status,created_by) VALUES (:tenant,:request,:line,:period,:center,'MANUAL',:external_id,:supplier_id,:supplier_name,:category,:store,:amount,:status,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "request": pr.id, "line": pr.budget_line_id, "period": pr.fiscal_period_id, "center": pr.cost_center_id, "external_id": body.external_id, "supplier_id": body.supplier_id, "supplier_name": body.supplier_name, "category": body.category, "store": body.store_code, "amount": body.base_amount, "status": "RECONCILIATION_HOLD" if mismatch else "OPEN", "actor": uow.actor})
    po = po_result.one()
    po_item = _row(po)
    if mismatch:
        issue_result = await uow.session.execute(text("""INSERT INTO reconciliation_issue(tenant_id,cost_center_id,entity_type,entity_id,reason,expected_base_amount,observed_base_amount,created_by) VALUES (:tenant,:center,'PURCHASE_ORDER',:id,'PO_REQUEST_MISMATCH',:expected,:observed,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "center": pr.cost_center_id, "id": po.id, "expected": pr.requested_base_amount, "observed": body.base_amount, "actor": uow.actor})
        issue = _row(issue_result.one())
        await emit_financial_event(uow, event_type="RECONCILIATION_OPENED", aggregate_type="reconciliation_issue", aggregate_id=issue["id"], cost_center_id=issue["cost_center_id"], payload=issue)
    else:
        commitment_result = await uow.session.execute(text("""INSERT INTO commitment(tenant_id,purchase_order_id,budget_line_id,fiscal_period_id,cost_center_id,original_base_amount,remaining_base_amount) VALUES (:tenant,:po,:line,:period,:center,:amount,:amount) RETURNING *"""), {"tenant": uow.tenant_id, "po": po.id, "line": pr.budget_line_id, "period": pr.fiscal_period_id, "center": pr.cost_center_id, "amount": body.base_amount})
        commitment = _row(commitment_result.one())
        await emit_financial_event(uow, event_type="COMMITMENT_OPENED", aggregate_type="commitment", aggregate_id=commitment["id"], cost_center_id=commitment["cost_center_id"], payload=commitment)
    await emit_financial_event(uow, event_type="PURCHASE_ORDER_CREATED", aggregate_type="purchase_order", aggregate_id=po_item["id"], cost_center_id=po_item["cost_center_id"], payload=po_item)
    return po_item
