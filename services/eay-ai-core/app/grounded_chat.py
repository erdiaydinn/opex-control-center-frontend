from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .legal_engine import LegalEngine
from .main import (
    ANSWER_SCHEMA,
    SYSTEM_PROMPT,
    ChatAnswer,
    ChatRequest,
    _format_evidence,
    ollama,
    settings,
    store,
    validate_citations,
)

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
legal_engine = LegalEngine(DB_PATH)
router = APIRouter(prefix="/v1/grounded", tags=["grounded-chat"])


class ProvenanceItem(BaseModel):
    id: str
    layer: str
    source_id: str | None = None
    verification_id: str | None = None
    version: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_url: str | None = None
    content_sha256: str | None = None
    chunk_sha256: str | None = None


class GroundedChatAnswer(BaseModel):
    response: ChatAnswer
    provenance: list[ProvenanceItem] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _provenance_for_evidence(evidence_ids: list[str]) -> list[ProvenanceItem]:
    if not evidence_ids:
        return []
    placeholders = ",".join("?" for _ in evidence_ids)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        docs = conn.execute(
            f"SELECT * FROM knowledge_documents WHERE id IN ({placeholders})",
            evidence_ids,
        ).fetchall()

        legal_chunks: dict[str, sqlite3.Row] = {}
        if _table_exists(conn, "legal_knowledge_chunks"):
            legal_chunks = {
                row["id"]: row
                for row in conn.execute(
                    f"SELECT * FROM legal_knowledge_chunks WHERE id IN ({placeholders})",
                    evidence_ids,
                ).fetchall()
            }

        company_rows: dict[str, sqlite3.Row] = {}
        if _table_exists(conn, "company_policy_versions"):
            company_rows = {
                f"company:{row['id']}": row
                for row in conn.execute("SELECT * FROM company_policy_versions").fetchall()
            }

    result: list[ProvenanceItem] = []
    for doc in docs:
        legal = legal_chunks.get(doc["id"])
        if legal:
            result.append(
                ProvenanceItem(
                    id=doc["id"],
                    layer="legal",
                    source_id=legal["instrument_id"],
                    verification_id=legal["verification_id"],
                    version=doc["version"],
                    effective_from=date.fromisoformat(doc["effective_from"])
                    if doc["effective_from"]
                    else None,
                    effective_to=date.fromisoformat(doc["effective_to"])
                    if doc["effective_to"]
                    else None,
                    source_url=doc["source_url"],
                    content_sha256=legal["content_sha256"],
                    chunk_sha256=legal["chunk_sha256"],
                )
            )
            continue

        if doc["layer"] == "company" and doc["id"].startswith("company:"):
            parts = doc["id"].split(":")
            key = f"company:{parts[1]}" if len(parts) >= 2 else ""
            policy = company_rows.get(key)
            result.append(
                ProvenanceItem(
                    id=doc["id"],
                    layer="company",
                    source_id=policy["policy_id"] if policy else None,
                    version=policy["version"] if policy else doc["version"],
                    effective_from=date.fromisoformat(doc["effective_from"])
                    if doc["effective_from"]
                    else None,
                    effective_to=date.fromisoformat(doc["effective_to"])
                    if doc["effective_to"]
                    else None,
                    source_url=doc["source_url"],
                    content_sha256=policy["content_sha256"] if policy else None,
                )
            )
            continue

        result.append(
            ProvenanceItem(
                id=doc["id"],
                layer=doc["layer"],
                version=doc["version"],
                effective_from=date.fromisoformat(doc["effective_from"])
                if doc["effective_from"]
                else None,
                effective_to=date.fromisoformat(doc["effective_to"])
                if doc["effective_to"]
                else None,
                source_url=doc["source_url"],
            )
        )
    return result


@router.post("/chat", response_model=GroundedChatAnswer)
async def grounded_chat(request: ChatRequest):
    evidence = store.search(
        request.message,
        request.as_of,
        request.layers,
        settings.top_k,
    )
    prompt = f"""
AS_OF: {request.as_of.isoformat()}
COMPANY: {request.company or 'not_specified'}

USER QUESTION:
{request.message}

RETRIEVED EVIDENCE:
{_format_evidence(evidence)}

Keep LEGAL, COMPANY, STANDARD and OPERATIONAL findings separate. If company and legal layers differ, explain the difference explicitly.
""".strip()
    try:
        parsed, raw = await ollama.chat_json(
            system=SYSTEM_PROMPT,
            user=prompt,
            schema=ANSWER_SCHEMA,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local model unavailable or invalid response: {exc}",
        ) from exc

    interaction_id = str(uuid.uuid4())
    answer = ChatAnswer(
        **parsed,
        evidence=evidence,
        model=settings.model,
        prompt_tokens=raw.get("prompt_eval_count"),
        output_tokens=raw.get("eval_count"),
        interaction_id=interaction_id,
    )
    valid_ids = {item.id for item in evidence}
    has_legal = any(
        item.layer == "legal" and item.authority_level == "binding"
        for item in evidence
    )
    answer = validate_citations(answer, valid_ids, has_legal)
    store.save_interaction(
        interaction_id=interaction_id,
        request=request,
        model=settings.model,
        model_answer=answer.model_dump_json(),
        evidence=evidence,
        confidence=answer.confidence,
    )
    if answer.confidence < settings.low_confidence_threshold:
        store.create_low_confidence_candidate(interaction_id)

    conflicts = [
        item.model_dump()
        for item in legal_engine.compare_company_to_law(request.as_of)
    ]
    provenance = _provenance_for_evidence([item.id for item in evidence])
    return GroundedChatAnswer(
        response=answer,
        provenance=provenance,
        conflicts=conflicts,
    )
