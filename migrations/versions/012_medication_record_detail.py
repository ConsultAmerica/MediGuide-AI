"""Separate medication details, review audit and source for confirmed records.

Revision ID: 012_medication_record_detail
Revises: 011_imaging_report_traceability
Create Date: 2026-10-14

A confirmed medication now keeps each label detail separately instead of
combined fields: brand and generic names (only when the label says which is
which), route, dose (amount per use, as printed in the directions),
frequency, refills, prescriber, pharmacy and prescription date. Strength
stays its own column and is never combined with the directions.

Audit and source:
* extracted_snapshot: JSON of what was read before review, so corrections
  stay visible;
* review_flags: JSON list of what was flagged for review (ambiguous or
  missing directions, dose ranges, risky abbreviations...);
* acknowledged_records: JSON list of existing records the reviewer compared
  this one with (possible duplicates / conflicting directions) before
  confirming. Nothing is merged;
* source_session_id, entry_index, source_page, text_source: which upload
  (and which medication in it) the record came from, and how it was read.

The old combined columns (form, instructions, quantity,
prescriber_or_pharmacy) stay and are still written, so existing rows and
readers are unaffected. All new columns are nullable or defaulted.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_medication_record_detail"
down_revision: Union[str, None] = "011_imaging_report_traceability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STRINGS = [
    ("brand_name", 256),
    ("generic_name", 256),
    ("route", 128),
    ("dose", 128),
    ("frequency", 256),
    ("refills", 64),
    ("prescriber", 256),
    ("pharmacy", 256),
    ("prescription_date", 64),
    ("source_session_id", 64),
    ("text_source", 16),
]


def upgrade() -> None:
    with op.batch_alter_table("medication_records") as batch_op:
        for name, length in _STRINGS:
            batch_op.add_column(sa.Column(name, sa.String(length=length), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("entry_index", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("source_page", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("extracted_snapshot", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("review_flags", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("acknowledged_records", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("medication_records") as batch_op:
        for name in ("acknowledged_records", "review_flags", "extracted_snapshot", "source_page", "entry_index"):
            batch_op.drop_column(name)
        for name, _ in reversed(_STRINGS):
            batch_op.drop_column(name)
