"""Audit trail for reviewed lab fields.

Revision ID: 009_extracted_field_audit
Revises: 008_users_and_ownership
Create Date: 2026-10-14

Confirmed fields now keep, alongside the value the reviewer accepted:
the H/L flag exactly as printed, what extraction originally produced
(JSON: label/value/unit/reference_range) so corrections stay auditable,
the reviewer's decision (confirmed / corrected) and when it was made.
The source region uses the existing bbox_* columns. All new columns are
nullable or defaulted, so existing rows survive the upgrade unchanged.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_extracted_field_audit"
down_revision: Union[str, None] = "008_users_and_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("extracted_fields") as batch_op:
        batch_op.add_column(sa.Column("flag", sa.String(length=8), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("extracted_snapshot", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("review_status", sa.String(length=16), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("extracted_fields") as batch_op:
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_status")
        batch_op.drop_column("extracted_snapshot")
        batch_op.drop_column("flag")
