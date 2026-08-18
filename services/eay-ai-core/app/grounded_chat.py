from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .grounded_critic import (
    CRITIC_SCHEMA,
    CRITIC_SYSTEM_PROMPT,
    GroundedCriticReport,
    apply_critic_constraints,
    build_critic_prompt,
    build_revision_prompt,
    is_high_assurance_critic,
    normalize_critic_report,
    should_run_grounded_critic,
    unavailable_critic_report,
)
from .grounded_evidence_planner import (
    EvidencePlan,
    build_evidence_plan,
    execute_evidence_plan,
    select_evidence,
)
from .grounded_reasoning import (
    DecisionQualityReport,
    assess_and_calibrate_grounded_answer,
)
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
    decision_quality: DecisionQualityReport | None = None
    critic: GroundedCriticReport | None = None
    evidence_plan: EvidencePlan | None = None


def _enforce_grounded_retrieval_truth_boundary(
    request: ChatRequest,
    active_layers: list[str] | None = None,
) -> None:
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

    scoped_layers = active_layers if active_layers is not None else request.layers
    tenant_scoped = sorted(_TENANT_SCOPED_LAYERS.intersection(scoped_layers))
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


def _company_conflicts_for_response(
    request: ChatRequest,
    active_layers: list[str] | None = None,
) -> list[dict]:
    """Project company-vs-law conflicts only where company scope is safe."""

    scoped_layers = active_layers if active_layers is not None else request.layers
    if "company" not in scoped_layers:
        return []

    environment = os.getenv("EAY_ENVIRONMENT", "development").strip().lower()
    if environment == "production":
        return []

    return [
        item.model_dump()
        for item in legal_engine.compare_company_to_law(request.as_of)
    ]


def _model_backend_unavailable() -> HTTPException:
    """Return a stable client-facing model failure without backend diagnostics."""

    return HTTPException(
        status_code=503,
        detail={
            "error": "grounded_model_unavailable",
            "message": "Grounded answer generation is temporarily unavailable",
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
    """Remove legal chunks whose source instrument is not active at `state.as_of`."""
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


def _token(raw: dict[str, Any] | None, key: str) -> int:
    try:
        return int((raw or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


async def _run_grounded_critic(
    *,
    request: ChatRequest,
    answer: ChatAnswer,
    evidence: list[Evidence],
    decision_quality: DecisionQualityReport,
) -> tuple[GroundedCriticReport, dict[str, Any]]:
    if not should_run_grounded_critic(request, answer, decision_quality):
        return GroundedCriticReport(), {}

    try:
        parsed, raw = await ollama.chat_json(
            system=CRITIC_SYSTEM_PROMPT,
            user=build_critic_prompt(
                request=request,
                answer=answer,
                evidence_text=_format_evidence(evidence),
                decision_quality=decision_quality,
            ),
            schema=CRITIC_SCHEMA,
        )
        report = normalize_critic_report(
            parsed,
            current_confidence=answer.confidence,
        )
        return report, raw
    except Exception:
        return (
            unavailable_critic_report(
                current_confidence=answer.confidence,
                high_assurance=is_high_assurance_critic(
                    request,
                    answer,
                    decision_quality,
                ),
            ),
            {},
        )


async def _apply_bounded_revision(
    *,
    request: ChatRequest,
    answer: ChatAnswer,
    evidence: list[Evidence],
    critic: GroundedCriticReport,
    valid_ids: set[str],
    has_legal: bool,
    interaction_id: str,
) -> tuple[ChatAnswer, DecisionQualityReport | None, dict[str, Any]]:
    if critic.verdict not in {"REVISE", "REJECT"} or not critic.revision_instructions:
        return answer, None, {}

    revision_system = (
        SYSTEM_PROMPT
        + "\n\nYou are revising an existing evidence-bound answer after verifier review. "
        "Apply only the supplied observable correction instructions. Do not add "
        "new facts or citations."
    )
    try:
        parsed, raw = await ollama.chat_json(
            system=revision_system,
            user=build_revision_prompt(
                request=request,
                answer=answer,
                evidence_text=_format_evidence(evidence),
                critic=critic,
            ),
            schema=ANSWER_SCHEMA,
        )
        revised = ChatAnswer(
            **parsed,
            evidence=evidence,
            model=settings.model,
            prompt_tokens=answer.prompt_tokens,
            output_tokens=answer.output_tokens,
            interaction_id=interaction_id,
        )
        revised = validate_citations(revised, valid_ids, has_legal)
        revised_quality = assess_and_calibrate_grounded_answer(
            request,
            revised,
            evidence,
        )
        critic.revision_applied = True
        critic.revision_guard_passed = bool(revised_quality.evidence_sufficient)
        if critic.revision_guard_passed:
            return revised, revised_quality, raw
    except Exception:
        pass

    critic.requires_human_review = True
    critic.confidence_cap = min(critic.confidence_cap, 0.40)
    return answer, None, {}


@router.post("/chat", response_model=GroundedChatAnswer)
async def grounded_chat(request: ChatRequest):
    evidence_plan = build_evidence_plan(request, settings.top_k)
    _enforce_grounded_retrieval_truth_boundary(request, evidence_plan.active_layers)

    temporal_state: LegalTemporalState | None = None
    if evidence_plan.legal_temporal_resolution_required:
        temporal_state = _resolve_temporal_state(request.as_of)

    evidence_candidates = execute_evidence_plan(
        evidence_plan,
        store=store,
        as_of=request.as_of,
    )
    if temporal_state is not None:
        evidence_candidates = _filter_temporally_active_legal_evidence(
            evidence_candidates,
            temporal_state,
        )
    evidence = select_evidence(
        evidence_plan,
        evidence_candidates,
        limit=settings.top_k,
    )

    prompt = f"""
AS_OF: {request.as_of.isoformat()}
COMPANY: {request.company or 'not_specified'}
EVIDENCE_ACTIVE_LAYERS: {', '.join(evidence_plan.active_layers) or 'none'}
LEGAL_TEMPORAL_RESOLUTION: {temporal_state.resolution_fingerprint if temporal_state else 'not_requested'}

USER QUESTION:
{request.message}

RETRIEVED EVIDENCE:
{_format_evidence(evidence)}

Keep LEGAL, COMPANY, STANDARD and OPERATIONAL findings separate. If company and legal layers differ, explain the difference explicitly.
""".strip()
    try:
        parsed, initial_raw = await ollama.chat_json(
            system=SYSTEM_PROMPT,
            user=prompt,
            schema=ANSWER_SCHEMA,
        )
    except Exception as exc:
        raise _model_backend_unavailable() from exc

    interaction_id = str(uuid.uuid4())
    answer = ChatAnswer(
        **parsed,
        evidence=evidence,
        model=settings.model,
        prompt_tokens=_token(initial_raw, "prompt_eval_count"),
        output_tokens=_token(initial_raw, "eval_count"),
        interaction_id=interaction_id,
    )
    valid_ids = {item.id for item in evidence}
    has_legal = any(
        item.layer == "legal" and item.authority_level == "binding"
        for item in evidence
    )
    answer = validate_citations(answer, valid_ids, has_legal)
    decision_quality = assess_and_calibrate_grounded_answer(
        request,
        answer,
        evidence,
    )

    critic, critic_raw = await _run_grounded_critic(
        request=request,
        answer=answer,
        evidence=evidence,
        decision_quality=decision_quality,
    )
    revised_answer, revised_quality, revision_raw = await _apply_bounded_revision(
        request=request,
        answer=answer,
        evidence=evidence,
        critic=critic,
        valid_ids=valid_ids,
        has_legal=has_legal,
        interaction_id=interaction_id,
    )
    if revised_quality is not None:
        answer = revised_answer
        decision_quality = revised_quality

    apply_critic_constraints(answer, critic)
    answer.prompt_tokens = (
        _token(initial_raw, "prompt_eval_count")
        + _token(critic_raw, "prompt_eval_count")
        + _token(revision_raw, "prompt_eval_count")
    )
    answer.output_tokens = (
        _token(initial_raw, "eval_count")
        + _token(critic_raw, "eval_count")
        + _token(revision_raw, "eval_count")
    )

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

    conflicts = _company_conflicts_for_response(request, evidence_plan.active_layers)
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
        decision_quality=decision_quality,
        critic=critic,
        evidence_plan=evidence_plan,
    )
