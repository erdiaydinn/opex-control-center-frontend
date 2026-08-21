from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
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

    @staticmethod
    def _assert_existing_identity_is_safe(
        existing: sqlite3.Row | None,
        *,
        document_id: str,
        layer: KnowledgeLayer,
        tenant_value: str | None,
    ) -> None:
        if existing is None:
            return

        existing_layer = str(existing["layer"])
        existing_tenant = existing["tenant_id"]
        requested_scoped = layer in _TENANT_SCOPED_LAYERS
        existing_scoped = existing_layer in _TENANT_SCOPED_LAYERS

        if requested_scoped:
            # Document IDs are still a global primary key in the inherited store.
            # Never let a second tenant silently overwrite/re-home an existing row.
            # Legacy tenant-scoped rows with no tenant_id are deliberately
            # unclaimable because ownership cannot be reconstructed safely.
            if (
                not existing_scoped
                or existing_tenant is None
                or existing_tenant != tenant_value
            ):
                raise ValueError(
                    f"tenant_scoped_document_identity_collision:{document_id}"
                )
            return

        # Shared legal/standard knowledge must never take over an ID already used
        # by tenant-scoped knowledge, even when a legacy scoped row has no tenant.
        if existing_scoped or existing_tenant is not None:
            raise ValueError(f"global_document_identity_collision:{document_id}")

    def upsert(self, doc: KnowledgeUpsert, *, tenant_id: UUID | None = None) -> None:
        requested_scoped = doc.layer in _TENANT_SCOPED_LAYERS
        if requested_scoped and tenant_id is None:
            raise ValueError("tenant_id_required_for_tenant_scoped_knowledge")
        if not requested_scoped and tenant_id is not None:
            raise ValueError("global_knowledge_must_not_be_tenant_scoped")

        tenant_value = self._tenant_value(tenant_id) if tenant_id is not None else None
        payload = doc.model_dump()
        payload["source_url"] = str(doc.source_url) if doc.source_url else None
        payload["effective_from"] = (
            doc.effective_from.isoformat() if doc.effective_from else None
        )
        payload["effective_to"] = (
            doc.effective_to.isoformat() if doc.effective_to else None
        )
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        payload["tenant_id"] = tenant_value

        # Keep the collision check, document mutation and FTS mutation in one
        # SQLite transaction so a failed tenant-bound write cannot leave a row
        # temporarily unscoped or partially indexed.
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT layer, tenant_id FROM knowledge_documents WHERE id = ?",
                (doc.id,),
            ).fetchone()
            self._assert_existing_identity_is_safe(
                existing,
                document_id=doc.id,
                layer=doc.layer,
                tenant_value=tenant_value,
            )
            conn.execute(
                """
                INSERT INTO knowledge_documents (
                    id, layer, title, content, source_name, source_url,
                    jurisdiction, authority_level, effective_from, effective_to,
                    version, updated_at, tenant_id
                ) VALUES (
                    :id, :layer, :title, :content, :source_name, :source_url,
                    :jurisdiction, :authority_level, :effective_from, :effective_to,
                    :version, :updated_at, :tenant_id
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
                    updated_at=excluded.updated_at,
                    tenant_id=excluded.tenant_id
                """,
                payload,
            )
            conn.execute("DELETE FROM knowledge_fts WHERE doc_id = ?", (doc.id,))
            conn.execute(
                "INSERT INTO knowledge_fts (doc_id, title, content) VALUES (?, ?, ?)",
                (doc.id, doc.title, doc.content),
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
