"""Source traceability and review history for imaging report sections.

Revision ID: 011_imaging_report_traceability
Revises: 010_lab_observation_date_source
Create Date: 2026-10-14

Report sections now record:

* page_end: the last page the section's wording runs onto (page_number
  stays the page it starts on), so a multi-page Findings section links to
  every page it came from;
* extraction_method: how the wording was read (native_text,
  tesseract_ocr, vision_ocr), so text read by the AI fallback is flagged;
* source_map: JSON with the section's line range in the report and its
  regions on each page, which is what boundary corrections and the source
  highlight use;
* reviewed_at: when the reviewer last confirmed or rejected the section.

Studies keep report_details: JSON with what the report itself says about
the study (report category, modality named, labelled exam date, ordering
clinician, facility, description, body region) and which of those the user
chose to apply, so the original prediction stays auditable.

All columns are nullable or defaulted; existing rows survive unchanged.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_imaging_report_traceability"
down_revision: Union[str, None] = "010_lab_observation_date_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("imaging_report_sections") as batch_op:
        batch_op.add_column(sa.Column("page_end", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("extraction_method", sa.String(length=32), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("source_map", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("imaging_studies") as batch_op:
        batch_op.add_column(sa.Column("report_details", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("imaging_studies") as batch_op:
        batch_op.drop_column("report_details")
    with op.batch_alter_table("imaging_report_sections") as batch_op:
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("source_map")
        batch_op.drop_column("extraction_method")
        batch_op.drop_column("page_end")
