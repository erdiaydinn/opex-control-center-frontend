"""Add tenant-scoped Jarvis query discriminator authority.

Revision ID: 0010_ai_tenant_query_context
Revises: 0009_ai_tool_permissions
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010_ai_tenant_query_context"
down_revision: str | None = "0009_ai_tool_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ai_tenant_query_contexts (
            tenant_id UUID PRIMARY KEY
                REFERENCES tenants(id) ON DELETE RESTRICT,
            context_version INTEGER NOT NULL DEFAULT 1,
            entity_ids JSONB NOT NULL,
            source_reference TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ai_tenant_query_context_version
                CHECK (context_version = 1),
            CONSTRAINT ck_ai_tenant_query_context_entity_ids_array
                CHECK (jsonb_typeof(entity_ids) = 'array'),
            CONSTRAINT ck_ai_tenant_query_context_entity_ids_count
                CHECK (
                    jsonb_array_length(entity_ids)
                    BETWEEN 1 AND 16
                ),
            CONSTRAINT ck_ai_tenant_query_context_source_reference
                CHECK (
                    char_length(source_reference)
                    BETWEEN 3 AND 512
                ),
            CONSTRAINT ck_ai_tenant_query_context_updated_by
                CHECK (
                    char_length(updated_by)
                    BETWEEN 1 AND 512
                )
        )
        """
    )

    op.execute(
        "ALTER TABLE ai_tenant_query_contexts ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE ai_tenant_query_contexts FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        """
        CREATE POLICY ai_tenant_query_context_isolation
        ON ai_tenant_query_contexts
        USING (
            tenant_id = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )::uuid
        )
        WITH CHECK (
            tenant_id = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )::uuid
        )
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON TABLE "
        f"ai_tenant_query_contexts TO {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE "
        f"ai_tenant_query_contexts FROM {RUNTIME_ROLE}"
    )
    op.execute(
        "DROP TABLE IF EXISTS ai_tenant_query_contexts"
    )
