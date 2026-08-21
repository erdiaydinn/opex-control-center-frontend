"""Grant least-privilege access to the runtime database role.

Revision ID: 0002_runtime_role_grants
Revises: 0001_tenant_security
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_runtime_role_grants"
down_revision: str | None = "0001_tenant_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLE = "opex_runtime"
MUTABLE_TABLES = (
    "tenants",
    "tenant_domains",
    "memberships",
    "roles",
    "role_permissions",
    "membership_roles",
    "tenant_entitlements",
)


def upgrade() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
        + ", ".join(MUTABLE_TABLES)
        + f" TO {RUNTIME_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT ON TABLE audit_events TO {RUNTIME_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"REVOKE ALL PRIVILEGES ON TABLE audit_events FROM {RUNTIME_ROLE}"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE "
        + ", ".join(MUTABLE_TABLES)
        + f" FROM {RUNTIME_ROLE}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {RUNTIME_ROLE}")
