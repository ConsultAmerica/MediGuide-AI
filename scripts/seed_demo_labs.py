"""Seed synthetic verified lab observations for portfolio demos.

Rows are owned by the account in MEDIGUIDE_SEED_OWNER_ID (a user id). Without
it they are written unowned, and unowned rows are visible to no account.
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

from src.database.models import Document, DocumentPage, ExtractedField, LabObservation
from src.database.session import init_db, session_scope


SAMPLES = [
    ("hemoglobin", "Hemoglobin", "13.2", 13.2, "g/dL", "12.0-15.5", date(2026, 5, 14), 2),
    ("hemoglobin", "Hemoglobin", "12.8", 12.8, "g/dL", "12.0-15.5", date(2026, 6, 18), 1),
    ("hemoglobin", "Hemoglobin", "13.5", 13.5, "g/dL", "12.0-15.5", date(2026, 7, 22), 1),
    ("glucose", "Glucose", "98", 98.0, "mg/dL", "70-99", date(2026, 5, 14), 2),
    ("glucose", "Glucose", "104", 104.0, "mg/dL", "70-99", date(2026, 6, 18), 1),
    ("glucose", "Glucose", "101", 101.0, "mg/dL", "70-99", date(2026, 7, 22), 1),
    ("hemoglobin_a1c", "Hemoglobin A1C", "5.6", 5.6, "%", "4.0-5.6", date(2026, 5, 14), 2),
    ("hemoglobin_a1c", "Hemoglobin A1C", "5.7", 5.7, "%", "4.0-5.6", date(2026, 7, 22), 1),
    ("ldl_cholesterol", "LDL Cholesterol", "118", 118.0, "mg/dL", "<100", date(2026, 6, 18), 1),
    ("hdl_cholesterol", "HDL Cholesterol", "52", 52.0, "mg/dL", ">40", date(2026, 6, 18), 1),
    ("total_cholesterol", "Cholesterol", "188", 188.0, "mg/dL", "<200", date(2026, 6, 18), 1),
    ("creatinine", "Creatinine", "0.9", 0.9, "mg/dL", "0.6-1.2", date(2026, 7, 22), 1),
    ("wbc", "WBC", "6.4", 6.4, "10^3/uL", "4.0-11.0", date(2026, 7, 22), 1),
    ("platelets", "Platelets", "242", 242.0, "10^3/uL", "150-400", date(2026, 7, 22), 1),
]


def main() -> None:
    init_db()
    owner_id = os.getenv("MEDIGUIDE_SEED_OWNER_ID", "").strip() or None
    if owner_id is None:
        print("warning: MEDIGUIDE_SEED_OWNER_ID is not set; seeded rows will be visible to no account")
    with session_scope() as session:
        for index, (
            code,
            label,
            value_text,
            value,
            unit,
            reference,
            report_date,
            page_number,
        ) in enumerate(SAMPLES, start=1):
            document_id = str(uuid4())
            field_pk = str(uuid4())
            filename = f"Sample_Lab_Report_{report_date.isoformat()}.pdf"
            document = Document(
                id=document_id,
                owner_id=owner_id,
                filename=filename,
                page_count=max(page_number, 1),
                status="confirmed",
                confirmed=True,
                report_date=report_date,
            )
            page = DocumentPage(
                document_id=document_id,
                page_number=page_number,
                text_available=True,
            )
            field = ExtractedField(
                id=field_pk,
                document_id=document_id,
                field_id=f"demo-{code}-{index}",
                label=label,
                value=value_text,
                unit=unit,
                reference_range=reference,
                status="unknown",
                confidence="clearly_visible",
                page_number=page_number,
                user_confirmed=True,
                user_edited=False,
            )
            observation = LabObservation(
                document_id=document_id,
                field_id=field_pk,
                page_number=page_number,
                test_code=code,
                test_name=label,
                value_numeric=value,
                value_text=value_text,
                unit=unit,
                reference_text=reference,
                report_date=report_date,
                verification_state="human_verified",
                document_name=filename,
            )
            session.add_all([document, page, field, observation])
    print(f"Seeded {len(SAMPLES)} synthetic lab observations.")


if __name__ == "__main__":
    main()
