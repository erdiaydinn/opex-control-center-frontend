from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text

from .permissions import BudgetUnitOfWork

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")


def _request_hash(operation: str, payload: object) -> str:
    canonical = json.dumps(
        {"operation": operation, "payload": jsonable_encoder(payload)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def run_command(
    uow: BudgetUnitOfWork,
    *,
    key: str,
    operation: str,
    payload: object,
    perform: Callable[[], Awaitable[object]],
):
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    request_hash = _request_hash(operation, payload)
    result = await uow.session.execute(
        text("""
        INSERT INTO budget_command (tenant_id,idempotency_key,operation,request_hash,status,actor_id)
        VALUES (:tenant,:key,:operation,:hash,'PROCESSING',:actor)
        ON CONFLICT (tenant_id,idempotency_key) DO NOTHING
        RETURNING id
        """),
        {"tenant": uow.tenant_id, "key": key, "operation": operation, "hash": request_hash, "actor": uow.actor},
    )
    inserted = result.first()
    if inserted is None:
        existing = await uow.session.execute(
            text("SELECT * FROM budget_command WHERE tenant_id=:tenant AND idempotency_key=:key FOR UPDATE"),
            {"tenant": uow.tenant_id, "key": key},
        )
        command = existing.first()
        if command is None:
            raise HTTPException(status_code=503, detail="Idempotency state unavailable")
        if (
            command.actor_id != uow.actor
            or command.operation != operation
            or command.request_hash != request_hash
        ):
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used for a different command",
            )
        if command.status == "COMPLETED":
            return command.response
        raise HTTPException(status_code=409, detail="Command is already processing")

    response = await perform()
    encoded = jsonable_encoder(response)
    await uow.session.execute(
        text("UPDATE budget_command SET status='COMPLETED',response=CAST(:response AS jsonb),completed_at=now() WHERE tenant_id=:tenant AND idempotency_key=:key"),
        {"response": json.dumps(encoded, ensure_ascii=False, sort_keys=True), "tenant": uow.tenant_id, "key": key},
    )
    return encoded
