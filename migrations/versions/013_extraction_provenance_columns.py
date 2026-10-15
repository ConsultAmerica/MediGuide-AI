"""Extraction provenance columns that no earlier migration created.

Revision ID: 013_extraction_provenance_columns
Revises: 012_medication_record_detail
Create Date: 2026-10-15

The models gained these columns, but only the SQLite start-up patch
(src/database/session.py, _ensure_sqlite_columns) ever added them, so a
database built by migrations alone (Postgres) was missing them and every
query touching lab observations or extracted fields failed:

* extracted_fields.extraction_method: how the value was read (text layer,
  table, OCR, AI);
* lab_observations.confidence, extraction_method, range_status: carried
  over from the confirmed field.

Columns that already exist (a migrated SQLite database the app has since
started) are left alone.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_extraction_provenance_columns"
down_revision: Union[str, None] = "012_medication_record_detail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "extracted_fields": [("extraction_method", 32, "")],
    "lab_observations": [
        ("confidence", 64, ""),
        ("extraction_method", 32, ""),
        ("range_status", 64, "unknown"),
    ],
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        missing = [column for column in columns if column[0] not in existing]
        if not missing:
            continue
        with op.batch_alter_table(table) as batch_op:
            for name, length, default in missing:
                batch_op.add_column(sa.Column(name, sa.String(length=length), nullable=False, server_default=default))


def downgrade() -> None:
    for table, columns in _COLUMNS.items():
        with op.batch_alter_table(table) as batch_op:
            for name, _, _ in reversed(columns):
                batch_op.drop_column(name)
