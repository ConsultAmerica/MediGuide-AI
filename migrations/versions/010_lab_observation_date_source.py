"""Record where a lab observation's date came from.

Revision ID: 010_lab_observation_date_source
Revises: 009_extracted_field_audit
Create Date: 2026-10-14

``date_source`` says which confirmed date a result is filed under:
"collection" (when the sample was taken) or "report" (a report/result date
printed on the document). Empty means the date's origin wasn't recorded
(rows created before this migration) or the result has no date. The UI
labels the date accordingly instead of presenting every date as a
collection date.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_lab_observation_date_source"
down_revision: Union[str, None] = "009_extracted_field_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lab_observations") as batch_op:
        batch_op.add_column(sa.Column("date_source", sa.String(length=16), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("lab_observations") as batch_op:
        batch_op.drop_column("date_source")
