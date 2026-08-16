from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from uuid import UUID

from .main import Evidence, KnowledgeLayer, KnowledgeUpsert, Store

_TENANT_SCOPED_LAYERS = frozenset({"company", "operational"})


class TenantScopedKnowledgeStore:
    """Tenant-aware persistence/query primitive for grounded retrieval.

    This is intentionally separate from the public grounded-chat route. Production
    company/operational retrieval must remain fail-closed until canonical Core
    authentication passes its verified tenant UUID into this primitive.

    Legacy rows with no tenant_id never match tenant-scoped queries. Global legal
    and standard knowledge remains shared because those layers are not company
    authority.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.store = Store(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(knowledge_documents)")
            }
            if "tenant_id" not in columns:
                conn.execute("ALTER TABLE knowledge_documents ADD COLUMN tenant_id TEXT")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_tenant_layer
                ON knowledge_documents (tenant_id, layer)
                """
            )

    @staticmethod
    def _tenant_value(tenant_id: UUID) -> str:
        return str(tenant_id)

    def upsert(self, doc: KnowledgeUpsert, *, tenant_id: UUID | None = None) -> None:
        if doc.layer in _TENANT_SCOPED_LAYERS and tenant_id is None:
            raise ValueError("tenant_id_required_for_tenant_scoped_knowledge")
        if doc.layer not in _TENANT_SCOPED_LAYERS and tenant_id is not None:
            raise ValueError("global_knowledge_must_not_be_tenant_scoped")

        self.store.upsert_knowledge(doc)
        with self._connect() as conn:
            conn.execute(
                "UPDATE knowledge_documents SET tenant_id = ? WHERE id = ?",
                (
                    self._tenant_value(tenant_id) if tenant_id is not None else None,
                    doc.id,
                ),
            )

    def search(
        self,
        query: str,
        as_of: date,
        layers: list[KnowledgeLayer],
        limit: int,
        *,
        tenant_id: UUID | None = None,
    ) -> list[Evidence]:
        if not layers:
            return []

        requested_scoped = _TENANT_SCOPED_LAYERS.intersection(layers)
        if requested_scoped and tenant_id is None:
            raise ValueError("tenant_id_required_for_tenant_scoped_retrieval")

        placeholders = ",".join("?" for _ in layers)
        tenant_value = self._tenant_value(tenant_id) if tenant_id is not None else None
        params = [
            self.store._fts_query(query),
            *layers,
            as_of.isoformat(),
            as_of.isoformat(),
            tenant_value,
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
              AND (
                    d.layer NOT IN ('company', 'operational')
                    OR d.tenant_id = ?
              )
            ORDER BY raw_score ASC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        result: list[Evidence] = []
        for row in rows:
            content = row["content"].strip()
            result.append(
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
        return result
