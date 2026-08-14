from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import text

from .domain import batch_hash, normalize_import_row, row_fingerprint
from .evidence import emit_financial_event
from .integration_contracts import validate_external_identity
from .permissions import BudgetUnitOfWork
from .schemas import ImportStage


async def stage_import(uow: BudgetUnitOfWork, body: ImportStage) -> dict[str, object]:
    normalized_rows: list[dict[str, str]] = []
    errors: list[dict[str, object]] = []
    namespace = f"{body.source_system}:{body.entity_type}"
    for index, raw in enumerate(body.rows, start=1):
        normalized = normalize_import_row(raw)
        error = validate_external_identity(body.source_system, body.entity_type, normalized)
        if error:
            errors.append({"row": index, "error": error})
        normalized_rows.append(normalized)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Import validation failed", "rows": errors[:100]})
    content_hash = batch_hash(normalized_rows, namespace=namespace)
    result = await uow.session.execute(text("""INSERT INTO import_batch(tenant_id,source_system,entity_type,content_hash,created_by) VALUES (:tenant,:source,:entity,:hash,:actor) ON CONFLICT (tenant_id,source_system,entity_type,content_hash) DO NOTHING RETURNING id"""), {"tenant": uow.tenant_id, "source": body.source_system, "entity": body.entity_type, "hash": content_hash, "actor": uow.actor})
    created = result.first()
    if created is None:
        existing = await uow.session.execute(text("""SELECT id FROM import_batch WHERE tenant_id=:tenant AND source_system=:source AND entity_type=:entity AND content_hash=:hash"""), {"tenant": uow.tenant_id, "source": body.source_system, "entity": body.entity_type, "hash": content_hash})
        batch_id = existing.scalar_one()
        return {"batch_id": str(batch_id), "content_hash": content_hash, "duplicate_batch": True, "inserted_rows": 0}
    batch_id = created.id
    inserted = 0
    duplicates = 0
    for row in normalized_rows:
        fingerprint = row_fingerprint(row, namespace=namespace)
        row_result = await uow.session.execute(text("""INSERT INTO import_row(tenant_id,batch_id,source_system,entity_type,row_hash,payload) VALUES (:tenant,:batch,:source,:entity,:hash,CAST(:payload AS jsonb)) ON CONFLICT (tenant_id,source_system,entity_type,row_hash) DO NOTHING RETURNING id"""), {"tenant": uow.tenant_id, "batch": batch_id, "source": body.source_system, "entity": body.entity_type, "hash": fingerprint, "payload": json.dumps(row, ensure_ascii=False, sort_keys=True)})
        if row_result.first() is None:
            duplicates += 1
        else:
            inserted += 1
    response = {"batch_id": str(batch_id), "content_hash": content_hash, "duplicate_batch": False, "inserted_rows": inserted, "duplicate_rows": duplicates}
    await emit_financial_event(uow, event_type="IMPORT_STAGED", aggregate_type="import_batch", aggregate_id=batch_id, payload={**response, "source_system": body.source_system, "entity_type": body.entity_type})
    return response
