from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .evidence import emit_financial_event
from .permissions import BudgetUnitOfWork
from .schemas import InvoiceCreate, ReconciliationResolve


def _row(row) -> dict[str, object]:
    return dict(row._mapping)


async def post_invoice(uow: BudgetUnitOfWork, body: InvoiceCreate) -> dict[str, object]:
    po_result = await uow.session.execute(text("""SELECT p.*,fp.status period_status FROM purchase_order p JOIN fiscal_period fp ON fp.tenant_id=p.tenant_id AND fp.id=p.fiscal_period_id WHERE p.tenant_id=:tenant AND p.id=:id FOR UPDATE OF p"""), {"tenant": uow.tenant_id, "id": body.purchase_order_id})
    po = po_result.first()
    if po is None or po.status != "OPEN" or po.period_status != "OPEN":
        raise HTTPException(status_code=409, detail="Invoice requires OPEN PO and fiscal period")
    if po.created_by == uow.actor:
        raise HTTPException(status_code=409, detail="PO creator cannot post invoice")
    commitment_result = await uow.session.execute(text("SELECT * FROM commitment WHERE tenant_id=:tenant AND purchase_order_id=:po FOR UPDATE"), {"tenant": uow.tenant_id, "po": po.id})
    commitment = commitment_result.first()
    if commitment is None or commitment.status != "OPEN":
        raise HTTPException(status_code=409, detail="PO has no open commitment")
    supplier = body.supplier_id.strip().upper()
    expected_supplier = po.supplier_id.strip().upper()
    mismatch = supplier != expected_supplier or body.base_amount > commitment.remaining_base_amount
    result = await uow.session.execute(text("""INSERT INTO invoice(tenant_id,purchase_order_id,budget_line_id,fiscal_period_id,cost_center_id,source_system,invoice_number,supplier_id,supplier_name,category,store_code,invoice_date,base_amount,status,created_by) VALUES (:tenant,:po,:line,:period,:center,'MANUAL',:number,:supplier,:supplier_name,:category,:store,:invoice_date,:amount,:status,:actor) ON CONFLICT (tenant_id,supplier_id,invoice_number) DO NOTHING RETURNING *"""), {"tenant": uow.tenant_id, "po": po.id, "line": po.budget_line_id, "period": po.fiscal_period_id, "center": po.cost_center_id, "number": body.invoice_number.strip().upper(), "supplier": supplier, "supplier_name": body.supplier_name, "category": body.category, "store": body.store_code, "invoice_date": body.invoice_date, "amount": body.base_amount, "status": "HOLD" if mismatch else "POSTED", "actor": uow.actor})
    invoice = result.first()
    if invoice is None:
        raise HTTPException(status_code=409, detail="Duplicate invoice identity")
    invoice_item = _row(invoice)
    if mismatch:
        issue_result = await uow.session.execute(text("""INSERT INTO reconciliation_issue(tenant_id,cost_center_id,entity_type,entity_id,reason,expected_base_amount,observed_base_amount,created_by) VALUES (:tenant,:center,'INVOICE',:id,'INVOICE_PO_MISMATCH',:expected,:observed,:actor) RETURNING *"""), {"tenant": uow.tenant_id, "center": po.cost_center_id, "id": invoice.id, "expected": commitment.remaining_base_amount, "observed": body.base_amount, "actor": uow.actor})
        issue = _row(issue_result.one())
        await emit_financial_event(uow, event_type="RECONCILIATION_OPENED", aggregate_type="reconciliation_issue", aggregate_id=issue["id"], cost_center_id=issue["cost_center_id"], payload=issue)
        await emit_financial_event(uow, event_type="INVOICE_HELD", aggregate_type="invoice", aggregate_id=invoice_item["id"], cost_center_id=invoice_item["cost_center_id"], payload=invoice_item)
        return invoice_item
    actual_result = await uow.session.execute(text("""INSERT INTO actual(tenant_id,invoice_id,budget_line_id,fiscal_period_id,cost_center_id,base_amount) VALUES (:tenant,:invoice,:line,:period,:center,:amount) RETURNING *"""), {"tenant": uow.tenant_id, "invoice": invoice.id, "line": po.budget_line_id, "period": po.fiscal_period_id, "center": po.cost_center_id, "amount": body.base_amount})
    actual = _row(actual_result.one())
    commitment_update = await uow.session.execute(text("""UPDATE commitment SET remaining_base_amount=remaining_base_amount-:amount, status=CASE WHEN remaining_base_amount-:amount=0 THEN 'CLOSED' ELSE 'OPEN' END WHERE tenant_id=:tenant AND id=:id RETURNING *"""), {"tenant": uow.tenant_id, "id": commitment.id, "amount": body.base_amount})
    commitment_item = _row(commitment_update.one())
    await emit_financial_event(uow, event_type="INVOICE_POSTED", aggregate_type="invoice", aggregate_id=invoice_item["id"], cost_center_id=invoice_item["cost_center_id"], payload=invoice_item)
    await emit_financial_event(uow, event_type="ACTUAL_POSTED", aggregate_type="actual", aggregate_id=actual["id"], cost_center_id=actual["cost_center_id"], payload=actual)
    await emit_financial_event(uow, event_type="COMMITMENT_UPDATED", aggregate_type="commitment", aggregate_id=commitment_item["id"], cost_center_id=commitment_item["cost_center_id"], payload=commitment_item)
    return invoice_item


async def resolve_reconciliation(uow: BudgetUnitOfWork, issue_id: UUID, body: ReconciliationResolve) -> dict[str, object]:
    issue_result = await uow.session.execute(text("SELECT * FROM reconciliation_issue WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": issue_id})
    issue = issue_result.first()
    if issue is None or issue.status != "OPEN":
        raise HTTPException(status_code=409, detail="Reconciliation is not open")
    if issue.created_by == uow.actor:
        raise HTTPException(status_code=409, detail="Reconciliation requires a second actor")
    if issue.entity_type == "PURCHASE_ORDER":
        po_result = await uow.session.execute(text("SELECT * FROM purchase_order WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": issue.entity_id})
        po = po_result.one()
        if body.decision == "ACCEPT_OBSERVED":
            line_result = await uow.session.execute(text("SELECT * FROM budget_line WHERE tenant_id=:tenant AND id=:id FOR UPDATE"), {"tenant": uow.tenant_id, "id": po.budget_line_id})
            line = line_result.one()
            exposure_result = await uow.session.execute(text("""SELECT COALESCE((SELECT SUM(base_amount) FROM actual WHERE tenant_id=:tenant AND budget_line_id=:line),0) + COALESCE((SELECT SUM(remaining_base_amount) FROM commitment WHERE tenant_id=:tenant AND budget_line_id=:line AND status='OPEN'),0) amount"""), {"tenant": uow.tenant_id, "line": po.budget_line_id})
            exposure = Decimal(str(exposure_result.scalar_one()))
            if exposure + po.base_amount > line.budget_base_amount:
                raise HTTPException(status_code=409, detail="Accepted PO would exceed Budget Line")
            po_update = await uow.session.execute(text("UPDATE purchase_order SET status='OPEN' WHERE tenant_id=:tenant AND id=:id RETURNING *"), {"tenant": uow.tenant_id, "id": po.id})
            po_item = _row(po_update.one())
            commitment_result = await uow.session.execute(text("""INSERT INTO commitment(tenant_id,purchase_order_id,budget_line_id,fiscal_period_id,cost_center_id,original_base_amount,remaining_base_amount) VALUES (:tenant,:po,:line,:period,:center,:amount,:amount) ON CONFLICT (tenant_id,purchase_order_id) DO NOTHING RETURNING *"""), {"tenant": uow.tenant_id, "po": po.id, "line": po.budget_line_id, "period": po.fiscal_period_id, "center": po.cost_center_id, "amount": po.base_amount})
            commitment = commitment_result.first()
            await emit_financial_event(uow, event_type="PURCHASE_ORDER_RECONCILED", aggregate_type="purchase_order", aggregate_id=po_item["id"], cost_center_id=po_item["cost_center_id"], payload=po_item)
            if commitment is not None:
                commitment_item = _row(commitment)
                await emit_financial_event(uow, event_type="COMMITMENT_OPENED", aggregate_type="commitment", aggregate_id=commitment_item["id"], cost_center_id=commitment_item["cost_center_id"], payload=commitment_item)
        else:
            po_update = await uow.session.execute(text("UPDATE purchase_order SET status='CANCELED' WHERE tenant_id=:tenant AND id=:id RETURNING *"), {"tenant": uow.tenant_id, "id": po.id})
            po_item = _row(po_update.one())
            await emit_financial_event(uow, event_type="PURCHASE_ORDER_REJECTED", aggregate_type="purchase_order", aggregate_id=po_item["id"], cost_center_id=po_item["cost_center_id"], payload=po_item)
    elif issue.entity_type == "INVOICE":
        if body.decision == "ACCEPT_OBSERVED":
            raise HTTPException(status_code=409, detail="Held invoice must be corrected before posting")
        invoice_update = await uow.session.execute(text("UPDATE invoice SET status='REJECTED' WHERE tenant_id=:tenant AND id=:id RETURNING *"), {"tenant": uow.tenant_id, "id": issue.entity_id})
        invoice_item = _row(invoice_update.one())
        await emit_financial_event(uow, event_type="INVOICE_REJECTED", aggregate_type="invoice", aggregate_id=invoice_item["id"], cost_center_id=invoice_item["cost_center_id"], payload=invoice_item)
    else:
        raise HTTPException(status_code=409, detail="Unsupported reconciliation entity")
    result = await uow.session.execute(text("""UPDATE reconciliation_issue SET status='RESOLVED',resolution_decision=:decision,resolution_reason=:reason,resolved_by=:actor,resolved_at=now() WHERE tenant_id=:tenant AND id=:id RETURNING *"""), {"tenant": uow.tenant_id, "id": issue.id, "decision": body.decision, "reason": body.reason, "actor": uow.actor})
    item = _row(result.one())
    await emit_financial_event(uow, event_type="RECONCILIATION_RESOLVED", aggregate_type="reconciliation_issue", aggregate_id=item["id"], cost_center_id=item["cost_center_id"], payload={"decision": body.decision, "reason": body.reason, "resolved_by": uow.actor})
    return item
