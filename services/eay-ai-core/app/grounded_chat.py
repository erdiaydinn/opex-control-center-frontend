from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .legal_engine import LegalEngine
from .legal_interaction_audit import LegalInteractionAuditStore
from .legal_temporal import LegalTemporalResolver, LegalTemporalState
from .main import (
    ANSWER_SCHEMA,
    SYSTEM_PROMPT,
    ChatAnswer,
    ChatRequest,
    Evidence,
    _format_evidence,
    ollama,
    settings,
    store,
    validate_citations,
)

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
legal_engine = LegalEngine(DB_PATH)
temporal_resolver = LegalTemporalResolver(DB_PATH)
legal_interaction_audit = LegalInteractionAuditStore(DB_PATH)
router = APIRouter(prefix="/v1/grounded", tags=["grounded-chat"])

_TENANT_SCOPED_LAYERS = frozenset({"company", "operational"})
_ALLOWED_ENVIRONMENTS = frozenset({"development", "test", "production"})


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
    temporal_resolution_fingerprint: str | None = None


class GroundedChatAnswer(BaseModel):
    response: ChatAnswer
    provenance: list[ProvenanceItem] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    temporal_resolution_fingerprint: str | None = None
    legal_audit_fingerprint: str | None = None


def _enforce_grounded_retrieval_truth_boundary(request: ChatRequest) -> None:
    """Keep tenant-scoped retrieval closed until Core tenant authority is bound.

    EAY AI Core's local SQLite/FTS store currently has no authoritative tenant
    discriminator. A client-supplied company or tenant string therefore cannot
    be treated as isolation authority. Local development/test remains available
    for single-company research, while production allows only global legal and
    standard retrieval until the canonical Core identity/tenant context is
    carried into the retrieval store and query.
    """

    environment = os.getenv("EAY_ENVIRONMENT", "development").strip().lower()
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise HTTPException(
            status_code=503,
            detail="Grounded retrieval environment is invalid",
        )

    if environment != "production":
        return

    tenant_scoped = sorted(_TENANT_SCOPED_LAYERS.intersection(request.layers))
    if tenant_scoped:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "tenant_scoped_retrieval_not_production_ready",
                "layers": tenant_scoped,
                "truth_boundary": (
                    "central tenant authority is not bound to grounded retrieval"
                ),
            },
        )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _provenance_for_evidence(
    evidence_ids: list[str],
    temporal_resolution_fingerprint: str | None = None,
) -> list[ProvenanceItem]:
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
                    temporal_resolution_fingerprint=temporal_resolution_fingerprint,
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


def _resolve_temporal_state(as_of: date) -> LegalTemporalState:
    state = temporal_resolver.resolve(as_of)
    if not state.resolved:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "legal_temporal_resolution_blocked",
                "as_of": state.as_of,
                "blockers": list(state.blockers),
                "resolution_fingerprint": state.resolution_fingerprint,
            },
        )
    return state


def _filter_temporally_active_legal_evidence(
    evidence: list[Evidence],
    state: LegalTemporalState,
) -> list[Evidence]:
    """Remove legal chunks whose source instrument is not active at `state.as_of`.

    Legal evidence without a verified legal-chunk provenance row is also excluded.
    This keeps older/manual `legal` knowledge rows from bypassing the temporal graph.
    Non-legal evidence is preserved unchanged.
    """
    legal_ids = [item.id for item in evidence if item.layer == "legal"]
    if not legal_ids:
        return evidence

    placeholders = ",".join("?" for _ in legal_ids)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "legal_knowledge_chunks"):
            legal_sources: dict[str, str] = {}
        else:
            legal_sources = {
                row["id"]: row["instrument_id"]
                for row in conn.execute(
                    f"SELECT id, instrument_id FROM legal_knowledge_chunks WHERE id IN ({placeholders})",
                    legal_ids,
                ).fetchall()
            }

    active = set(state.active_instrument_ids)
    return [
        item
        for item in evidence
        if item.layer != "legal" or legal_sources.get(item.id) in active
    ]


@router.post("/chat", response_model=GroundedChatAnswer)
async def grounded_chat(request: ChatRequest):
    _enforce_grounded_retrieval_truth_boundary(request)

    temporal_state: LegalTemporalState | None = None
    if "legal" in request.layers:
        temporal_state = _resolve_temporal_state(request.as_of)

    retrieval_limit = settings.top_k
    if temporal_state is not None:
        # Inactive historical legal chunks can occupy lexical top-k positions. Search
        # a bounded wider window, apply the temporal graph, then restore the public cap.
        retrieval_limit = min(max(settings.top_k * 4, settings.top_k), 32)

    evidence = store.search(
        request.message,
        request.as_of,
        request.layers,
        retrieval_limit,
    )
    if temporal_state is not None:
        evidence = _filter_temporally_active_legal_evidence(evidence, temporal_state)
        evidence = evidence[: settings.top_k]

    prompt = f"""
AS_OF: {request.as_of.isoformat()}
COMPANY: {request.company or 'not_specified'}
LEGAL_TEMPORAL_RESOLUTION: {temporal_state.resolution_fingerprint if temporal_state else 'not_requested'}

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

    legal_audit_fingerprint: str | None = None
    if temporal_state is not None:
        audit = legal_interaction_audit.record(
            interaction_id=interaction_id,
            as_of=request.as_of.isoformat(),
            temporal_resolution_fingerprint=temporal_state.resolution_fingerprint,
            active_instrument_ids=temporal_state.active_instrument_ids,
            evidence_ids=[item.id for item in evidence],
        )
        legal_audit_fingerprint = audit.audit_fingerprint

    if answer.confidence < settings.low_confidence_threshold:
        store.create_low_confidence_candidate(interaction_id)

    conflicts = [
        item.model_dump()
        for item in legal_engine.compare_company_to_law(request.as_of)
    ]
    temporal_fingerprint = (
        temporal_state.resolution_fingerprint if temporal_state is not None else None
    )
    provenance = _provenance_for_evidence(
        [item.id for item in evidence],
        temporal_resolution_fingerprint=temporal_fingerprint,
    )
    return GroundedChatAnswer(
        response=answer,
        provenance=provenance,
        conflicts=conflicts,
        temporal_resolution_fingerprint=temporal_fingerprint,
        legal_audit_fingerprint=legal_audit_fingerprint,
    )