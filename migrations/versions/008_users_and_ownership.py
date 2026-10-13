"""Add users, auth sessions, and per-record ownership.

Revision ID: 008_users_and_ownership
Revises: 007_imaging_findings
Create Date: 2026-10-13

owner_id is nullable so existing rows survive the upgrade. Unowned rows are
invisible to every user until assigned with scripts/claim_legacy_records.py.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_users_and_ownership"
down_revision: Union[str, None] = "007_imaging_findings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OWNED_TABLES = ("documents", "imaging_studies", "medication_records")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(length=256), server_default="", nullable=False),
        sa.Column("display_name", sa.String(length=128), server_default="", nullable=False),
        sa.Column("is_guest", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    # Batch mode: SQLite can't ADD COLUMN with a foreign key directly.
    for table in _OWNED_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.String(length=36), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table}_owner_id",
                "users",
                ["owner_id"],
                ["id"],
                ondelete="CASCADE",
            )
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])


def downgrade() -> None:
    for table in reversed(_OWNED_TABLES):
        op.drop_index(f"ix_{table}_owner_id", table_name=table)
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"fk_{table}_owner_id", type_="foreignkey")
            batch_op.drop_column("owner_id")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
