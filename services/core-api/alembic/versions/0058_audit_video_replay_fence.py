"""Fence duplicate Audit video verification events.

Revision ID: 0058_audit_video_replay_fence
Revises: 0057_audit_video_authority
Create Date: 2026-08-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0058_audit_video_replay_fence"
down_revision: str = "0057_audit_video_authority"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_audit_video_verification_fingerprint",
        "audit_video_verification_events",
        ["tenant_id", "verification_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_audit_video_verification_fingerprint",
        "audit_video_verification_events",
        type_="unique",
    )
