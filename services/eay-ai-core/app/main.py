from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl


load_dotenv()


KnowledgeLayer = Literal["legal", "company", "standard", "operational"]
AuthorityLevel = Literal["binding", "company", "voluntary", "operational"]
RiskLevel = Literal["low", "medium", "high", "critical", "unknown"]


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
    ollama_url: str = os.getenv("EAY_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model: str = os.getenv("EAY_MODEL", "eay-ops:0.1")
    teacher_model: str = os.getenv("EAY_TEACHER_MODEL", "").strip()
    top_k: int = int(os.getenv("EAY_TOP_K", "8"))
    low_confidence_threshold: float = float(
        os.getenv("EAY_LOW_CONFIDENCE_THRESHOLD", "0.62")
    )


settings = Settings()
settings.db_path.parent.mkdir(parents=True, exist_ok=True)


class KnowledgeUpsert(BaseModel):
    id: str = Field(min_length=3, max_length=180)
    layer: KnowledgeLayer
    title: str = Field(min_length=3, max_length=500)
    content: str = Field(min_length=5)
    source_name: str = Field(min_length=2, max_length=300)
    source_url: HttpUrl | None = None
    jurisdiction: str = Field(default="TR", max_length=32)
    authority_level: AuthorityLevel
    effective_from: date | None = None
    effective_to: date | None = None
    version: str | None = Field(default=None, max_length=100)


class Evidence(BaseModel):
    id: str
    layer: KnowledgeLayer
    title: str
    excerpt: str
    source_name: str
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    authority_level: AuthorityLevel
    score: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=2)
    as_of: date = Field(default_factory=date.today)
    company: str | None = Field(default=None, max_length=150)
    user_id: str | None = Field(default=None, max_length=150)
    layers: list[KnowledgeLayer] = Field(
        default_factory=lambda: ["legal", "company", "standard", "operational"]
    )


class LayerFinding(BaseModel):
    status: str
    summary: str
    citations: list[str] = Field(default_factory=list)


class ChatAnswer(BaseModel):
    answer: str
    legal: LayerFinding
    company: LayerFinding
    standards: LayerFinding
    operational: LayerFinding
    recommendation: str
    risk: RiskLevel = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    model: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    interaction_id: str


class FeedbackRequest(BaseModel):
    interaction_id: str
    rating: int = Field(ge=1, le=5)
    corrected_answer: str | None = None
    reason: str | None = None
    user_id: str | None = None


class LearningCandidate(BaseModel):
    id: str
    interaction_id: str
    status: Literal["pending", "approved", "rejected"]
    reason: str
    user_message: str
    model_answer: str
    corrected_answer: str | None
    created_at: datetime


class TeacherReviewResponse(BaseModel):
    candidate_id: str
    teacher_model: str
    critique: str
    improved_answer: str
    principles: list[str]


_TOKEN_RE = re.compile(r"[\wÇĞİÖŞÜçğıöşü-]{2,}", re.UNICODE)


class Store:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT,
                    jurisdiction TEXT NOT NULL,
                    authority_level TEXT NOT NULL,
                    effective_from TEXT,
                    effective_to TEXT,
                    version TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    doc_id UNINDEXED,
                    title,
                    content,
                    tokenize='unicode61 remove_diacritics 2'
                );

                CREATE TABLE IF NOT EXISTS interactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    user_message TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    model TEXT NOT NULL,
                    model_answer TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id TEXT NOT NULL,
                    user_id TEXT,
                    rating INTEGER NOT NULL,
                    corrected_answer TEXT,
                    reason TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learning_candidates (
                    id TEXT PRIMARY KEY,
                    interaction_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT NOT NULL,
                    corrected_answer TEXT,
                    teacher_review_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_knowledge(self, doc: KnowledgeUpsert) -> None:
        payload = doc.model_dump()
        payload["source_url"] = str(doc.source_url) if doc.source_url else None
        payload["effective_from"] = (
            doc.effective_from.isoformat() if doc.effective_from else None
        )
        payload["effective_to"] = (
            doc.effective_to.isoformat() if doc.effective_to else None
        )
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO knowledge_documents (
                    id, layer, title, content, source_name, source_url,
                    jurisdiction, authority_level, effective_from, effective_to,
                    version, updated_at
                ) VALUES (
                    :id, :layer, :title, :content, :source_name, :source_url,
                    :jurisdiction, :authority_level, :effective_from, :effective_to,
                    :version, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    layer=excluded.layer,
                    title=excluded.title,
                    content=excluded.content,
                    source_name=excluded.source_name,
                    source_url=excluded.source_url,
                    jurisdiction=excluded.jurisdiction,
                    authority_level=excluded.authority_level,
                    effective_from=excluded.effective_from,
                    effective_to=excluded.effective_to,
                    version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                payload,
            )
            conn.execute("DELETE FROM knowledge_fts WHERE doc_id = ?", (doc.id,))
            conn.execute(
                "INSERT INTO knowledge_fts (doc_id, title, content) VALUES (?, ?, ?)",
                (doc.id, doc.title, doc.content),
            )

    @staticmethod
    def _fts_query(text: str) -> str:
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return '\"\"'
        return " OR ".join(f'\"{token}\"' for token in tokens[:16])

    def search(
        self,
        query: str,
        as_of: date,
        layers: list[KnowledgeLayer],
        limit: int,
    ) -> list[Evidence]:
        if not layers:
            return []
        placeholders = ",".join("?" for _ in layers)
        params = [
            self._fts_query(query),
            *layers,
            as_of.isoformat(),
            as_of.isoformat(),
            limit,
        ]
        sql = f"""
            SELECT d.*, bm25(knowledge_fts) AS raw_score
            FROM knowledge_fts
            JOIN knowledge_documents d ON d.id = knowledge_fts.doc_id
            WHERE knowledge_fts MATCH ?
              AND d.layer IN ({placeholders})
              AND (d.effective_from IS NULL OR d.effective_from <= ?)
              AND (d.effective_to IS NULL OR d.effective_to >= ?)
            ORDER BY raw_score ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        output: list[Evidence] = []
        for row in rows:
            content = row["content"].strip()
            output.append(
                Evidence(
                    id=row["id"],
                    layer=row["layer"],
                    title=row["title"],
                    excerpt=content[:1400] + ("…" if len(content) > 1400 else ""),
                    source_name=row["source_name"],
                    source_url=row["source_url"],
                    effective_from=(
                        date.fromisoformat(row["effective_from"])
                        if row["effective_from"]
                        else None
                    ),
                    effective_to=(
                        date.fromisoformat(row["effective_to"])
                        if row["effective_to"]
                        else None
                    ),
                    authority_level=row["authority_level"],
                    score=1.0 / (1.0 + abs(float(row["raw_score"] or 0.0))),
                )
            )
        return output

    def save_interaction(
        self,
        *,
        interaction_id: str,
        request: ChatRequest,
        model: str,
        model_answer: str,
        evidence: list[Evidence],
        confidence: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interactions (
                    id, user_id, user_message, as_of, model, model_answer,
                    evidence_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id,
                    request.user_id,
                    request.message,
                    request.as_of.isoformat(),
                    model,
                    model_answer,
                    json.dumps(
                        [item.model_dump(mode="json") for item in evidence],
                        ensure_ascii=False,
                    ),
                    confidence,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def record_feedback(self, feedback: FeedbackRequest) -> str | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            interaction = conn.execute(
                "SELECT id FROM interactions WHERE id = ?",
                (feedback.interaction_id,),
            ).fetchone()
            if interaction is None:
                raise KeyError("interaction_not_found")
            conn.execute(
                """
                INSERT INTO feedback (
                    interaction_id, user_id, rating, corrected_answer, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.interaction_id,
                    feedback.user_id,
                    feedback.rating,
                    feedback.corrected_answer,
                    feedback.reason,
                    now,
                ),
            )
            if feedback.rating > 2 and not feedback.corrected_answer:
                return None
            candidate_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO learning_candidates (
                    id, interaction_id, status, reason, corrected_answer, created_at
                ) VALUES (?, ?, 'pending', ?, ?, ?)
                """,
                (
                    candidate_id,
                    feedback.interaction_id,
                    feedback.reason
                    or ("user_correction" if feedback.corrected_answer else "low_rating"),
                    feedback.corrected_answer,
                    now,
                ),
            )
            return candidate_id

    def create_low_confidence_candidate(self, interaction_id: str) -> str:
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM learning_candidates
                WHERE interaction_id = ?
                  AND reason = 'low_model_confidence'
                  AND status = 'pending'
                """,
                (interaction_id,),
            ).fetchone()
            if existing:
                return existing["id"]
            candidate_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO learning_candidates (
                    id, interaction_id, status, reason, created_at
                ) VALUES (?, ?, 'pending', 'low_model_confidence', ?)
                """,
                (
                    candidate_id,
                    interaction_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return candidate_id

    def list_candidates(self, limit: int) -> list[LearningCandidate]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, i.user_message, i.model_answer
                FROM learning_candidates c
                JOIN interactions i ON i.id = c.interaction_id
                ORDER BY c.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            LearningCandidate(
                id=row["id"],
                interaction_id=row["interaction_id"],
                status=row["status"],
                reason=row["reason"],
                user_message=row["user_message"],
                model_answer=row["model_answer"],
                corrected_answer=row["corrected_answer"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def candidate_context(self, candidate_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT c.*, i.user_message, i.model_answer, i.evidence_json
                FROM learning_candidates c
                JOIN interactions i ON i.id = c.interaction_id
                WHERE c.id = ?
                """,
                (candidate_id,),
            ).fetchone()

    def save_teacher_review(
        self, candidate_id: str, review: TeacherReviewResponse
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE learning_candidates SET teacher_review_json = ? WHERE id = ?",
                (review.model_dump_json(), candidate_id),
            )

    def set_candidate_status(self, candidate_id: str, status: str) -> None:
        with self._connect() as conn:
            count = conn.execute(
                "UPDATE learning_candidates SET status = ? WHERE id = ?",
                (status, candidate_id),
            ).rowcount
            if count == 0:
                raise KeyError("candidate_not_found")

    def export_approved(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, i.user_message, i.model_answer
                FROM learning_candidates c
                JOIN interactions i ON i.id = c.interaction_id
                WHERE c.status = 'approved'
                ORDER BY c.created_at ASC
                """
            ).fetchall()
        result = []
        for row in rows:
            teacher = (
                json.loads(row["teacher_review_json"])
                if row["teacher_review_json"]
                else None
            )
            target = (
                row["corrected_answer"]
                or (teacher or {}).get("improved_answer")
                or row["model_answer"]
            )
            result.append(
                {
                    "messages": [
                        {"role": "user", "content": row["user_message"]},
                        {"role": "assistant", "content": target},
                    ],
                    "metadata": {
                        "candidate_id": row["id"],
                        "reason": row["reason"],
                        "teacher_reviewed": bool(teacher),
                    },
                }
            )
        return result


class Ollama:
    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{settings.ollama_url}/api/version")
                return response.is_success
        except httpx.HTTPError:
            return False

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict,
        model: str | None = None,
    ) -> tuple[dict, dict]:
        payload = {
            "model": model or settings.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0.2},
        }
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            raw = response.json()
        content = raw.get("message", {}).get("content", "")
        try:
            return json.loads(content), raw
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama returned invalid JSON: {content[:500]}"
            ) from exc


ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "legal": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "citations"],
        },
        "company": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "citations"],
        },
        "standards": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "citations"],
        },
        "operational": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "citations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "summary", "citations"],
        },
        "recommendation": {"type": "string"},
        "risk": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical", "unknown"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "requires_human_review": {"type": "boolean"},
    },
    "required": [
        "answer",
        "legal",
        "company",
        "standards",
        "operational",
        "recommendation",
        "risk",
        "confidence",
        "requires_human_review",
    ],
}

TEACHER_SCHEMA = {
    "type": "object",
    "properties": {
        "critique": {"type": "string"},
        "improved_answer": {"type": "string"},
        "principles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["critique", "improved_answer", "principles"],
}

SYSTEM_PROMPT = """
You are EAY-Ops, a local-first Food & Retail Operations Intelligence model.

Evidence layers:
LEGAL = binding legislation/regulatory evidence.
COMPANY = internal company standards/SOPs.
STANDARD = voluntary or sector standards/best practices.
OPERATIONAL = live or historical operational facts.

Rules:
1. Never collapse evidence layers into one.
2. Never claim a legal obligation unless LEGAL evidence directly supports it.
3. Cite only evidence IDs supplied below.
4. Company policy may be stricter than law. State both explicitly.
5. If company policy appears incompatible with binding law, require human compliance/legal review.
6. Never invent law names, article numbers, dates, thresholds, limits, citations, company rules, or facts.
7. If evidence is insufficient, say so.
8. Prefer concise, operationally useful Turkish unless another language is clearly requested.
9. Critical, irreversible, employee-impacting, financial, legal, or external communication actions require human review.
10. Return only JSON matching the supplied schema.
""".strip()


store = Store(settings.db_path)
ollama = Ollama()
app = FastAPI(
    title="EAY AI Core",
    version="0.1.0",
    description="Local-first, regulatory-aware Food & Retail Operations Intelligence.",
)


def _format_evidence(items: list[Evidence]) -> str:
    if not items:
        return "NO EVIDENCE"
    return "\n\n---\n\n".join(
        "\n".join(
            [
                f"ID: {item.id}",
                f"LAYER: {item.layer.upper()}",
                f"TITLE: {item.title}",
                f"SOURCE: {item.source_name}",
                f"AUTHORITY: {item.authority_level}",
                f"EFFECTIVE_FROM: {item.effective_from or 'unknown'}",
                f"EFFECTIVE_TO: {item.effective_to or 'open/unknown'}",
                f"URL: {item.source_url or 'not_provided'}",
                f"EXCERPT: {item.excerpt}",
            ]
        )
        for item in items
    )


def validate_citations(
    answer: ChatAnswer,
    valid_ids: set[str],
    has_legal: bool,
) -> ChatAnswer:
    for section_name in ("legal", "company", "standards", "operational"):
        section: LayerFinding = getattr(answer, section_name)
        section.citations = [
            citation for citation in section.citations if citation in valid_ids
        ]

    if not has_legal:
        answer.legal = LayerFinding(
            status="insufficient",
            summary=(
                "Bu soru için yürürlük tarihine uygun bağlayıcı mevzuat kaynağı "
                "getirilemedi; kesin yasal hüküm verilemez."
            ),
            citations=[],
        )
        answer.requires_human_review = True
    return answer


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ollama": await ollama.health(),
        "model": settings.model,
        "db": str(settings.db_path),
    }


@app.post("/v1/knowledge", status_code=204)
def upsert_knowledge(doc: KnowledgeUpsert):
    store.upsert_knowledge(doc)
    return None


@app.post("/v1/chat", response_model=ChatAnswer)
async def chat(request: ChatRequest):
    evidence = store.search(
        request.message,
        as_of=request.as_of,
        layers=request.layers,
        limit=settings.top_k,
    )
    prompt = f"""
AS_OF: {request.as_of.isoformat()}
COMPANY: {request.company or 'not_specified'}

USER QUESTION:
{request.message}

RETRIEVED EVIDENCE:
{_format_evidence(evidence)}

Keep LEGAL, COMPANY, STANDARD and OPERATIONAL findings separate.
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
    return answer


@app.post("/v1/feedback")
def feedback(payload: FeedbackRequest):
    try:
        candidate_id = store.record_feedback(payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return {"ok": True, "learning_candidate_id": candidate_id}


@app.get("/v1/learning/export")
def export_learning_dataset():
    from .learning_export_guard import build_gated_export, review_store

    try:
        return build_gated_export(review_store=review_store)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


from .model_promotion_gate import PromotionRecord  # noqa: E402
from .model_promotion_routes import (  # noqa: E402
    PromotionApiRequest,
    ProductionModelProofEnvelope,
    get_current_production_promotion as governed_get_current_production_promotion,
    issue_current_production_model_proof,
    promote_model as governed_promote_model,
)


@app.post("/v1/model-promotions", response_model=PromotionRecord, status_code=201)
def promote_model(
    payload: PromotionApiRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return governed_promote_model(payload, authorization=authorization)


@app.get(
    "/v1/model-promotions/{model_record_id}",
    response_model=PromotionRecord,
)
def get_current_production_promotion(model_record_id: str):
    return governed_get_current_production_promotion(model_record_id)


@app.get(
    "/v1/internal/model-production-proofs/{model_record_id}",
    response_model=ProductionModelProofEnvelope,
)
def get_internal_current_production_model_proof(
    model_record_id: str,
    challenge: str = Header(alias="X-EAY-Model-Proof-Challenge"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    return issue_current_production_model_proof(
        model_record_id,
        challenge=challenge,
        authorization=authorization,
    )


@app.get("/v1/learning/candidates")
def candidates(limit: int = Query(default=100, ge=1, le=500)):
    return store.list_candidates(limit)


@app.post(
    "/v1/learning/candidates/{candidate_id}/teacher-review",
    response_model=TeacherReviewResponse,
)
async def teacher_review(candidate_id: str):
    if not settings.teacher_model:
        raise HTTPException(
            status_code=409,
            detail=(
                "EAY_TEACHER_MODEL is not configured. Configure a larger local "
                "Ollama model to enable local teacher review."
            ),
        )
    row = store.candidate_context(candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    prompt = f"""
Review an EAY-Ops failed or uncertain interaction.

USER:
{row['user_message']}

MODEL ANSWER:
{row['model_answer']}

USER CORRECTION:
{row['corrected_answer'] or 'none'}

REASON:
{row['reason']}

EVIDENCE USED:
{row['evidence_json']}

Return a critique, improved answer and reusable reasoning principles.
Never invent legal sources or facts beyond supplied evidence.
""".strip()
    try:
        parsed, _ = await ollama.chat_json(
            system=(
                "You are the local EAY teacher model. Improve student behavior "
                "without inventing facts. Return JSON only."
            ),
            user=prompt,
            schema=TEACHER_SCHEMA,
            model=settings.teacher_model,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    review = TeacherReviewResponse(
        candidate_id=candidate_id,
        teacher_model=settings.teacher_model,
        **parsed,
    )
    store.save_teacher_review(candidate_id, review)
    return review


@app.post("/v1/learning/candidates/{candidate_id}/{decision}")
def decide(candidate_id: str, decision: str):
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Use approve or reject")
    try:
        store.set_candidate_status(
            candidate_id,
            "approved" if decision == "approve" else "rejected",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {
        "ok": True,
        "status": "approved" if decision == "approve" else "rejected",
    }
