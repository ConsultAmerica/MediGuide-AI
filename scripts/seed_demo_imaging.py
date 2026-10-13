"""Seed synthetic, confirmed imaging studies for portfolio demos.

Mirrors scripts/seed_demo_labs.py: writes Document/ImagingStudy/
ImagingReportSection rows directly, clearly labeled as synthetic. Like the
lab seed script, no real page-preview image files are written — only
metadata — so "View original report" on a seeded study will not have a
preview image, matching the lab seed's own limitation.

Rows are owned by the account in MEDIGUIDE_SEED_OWNER_ID (a user id). Without
it they are written unowned, and unowned rows are visible to no account.
"""

from __future__ import annotations

import os
from datetime import date

from src.database.models import Document, ImagingReportSection, ImagingStudy
from src.database.session import init_db, session_scope


def _seed_owner_id() -> str | None:
    owner_id = os.getenv("MEDIGUIDE_SEED_OWNER_ID", "").strip() or None
    if owner_id is None:
        print("warning: MEDIGUIDE_SEED_OWNER_ID is not set; seeded rows will be visible to no account")
    return owner_id


PROCESSOR_VERSION = "demo-seed-v1"

STUDIES = [
    {
        "modality": "xray",
        "body_region": "Right knee",
        "study_description": "X-Ray Right Knee",
        "study_date": date(2024, 3, 10),
        "institution": "MediGuide Demo Imaging Center",
        "sections": {
            "exam": "X-Ray Right Knee, two views.",
            "clinical_history": "Right knee pain after a fall.",
            "findings": "No acute fracture or dislocation. Joint spaces are preserved. No effusion.",
            "impression": "No acute fracture.",
        },
    },
    {
        "modality": "mri",
        "body_region": "Right knee",
        "study_description": "MRI Right Knee",
        "study_date": date(2025, 5, 14),
        "institution": "MediGuide Demo Imaging Center",
        "sections": {
            "exam": "MRI Right Knee without contrast.",
            "clinical_history": "Persistent right knee pain.",
            "technique": "Standard MRI knee protocol.",
            "findings": "No acute fracture. Mild joint effusion. Menisci and ligaments appear intact.",
            "impression": "Mild joint effusion. No acute fracture.",
        },
    },
    {
        "modality": "mri",
        "body_region": "Right knee",
        "study_description": "MRI Right Knee",
        "study_date": date(2026, 9, 2),
        "institution": "MediGuide Demo Imaging Center",
        "sections": {
            "exam": "MRI Right Knee without contrast.",
            "clinical_history": "Follow-up right knee pain, new instability.",
            "technique": "Standard MRI knee protocol.",
            "findings": "No acute fracture. Small joint effusion. Partial tear of the ACL is noted.",
            "impression": "Small joint effusion. Partial ACL tear.",
        },
    },
]


def main() -> None:
    init_db()
    owner_id = _seed_owner_id()
    created = 0
    with session_scope() as session:
        for entry in STUDIES:
            document = Document(
                owner_id=owner_id,
                filename=f"Demo_{entry['modality'].upper()}_Report_{entry['study_date'].isoformat()}.pdf",
                page_count=1,
                status="confirmed",
                confirmed=True,
                report_date=entry["study_date"],
            )
            session.add(document)
            session.flush()

            study = ImagingStudy(
                owner_id=owner_id,
                modality=entry["modality"],
                body_region=entry["body_region"],
                study_description=entry["study_description"],
                study_date=entry["study_date"],
                institution=entry["institution"],
                report_document_id=document.id,
                verification_status="verified",
            )
            session.add(study)
            session.flush()

            for section_type, text in entry["sections"].items():
                session.add(
                    ImagingReportSection(
                        study_id=study.id,
                        document_id=document.id,
                        section_type=section_type,
                        section_text=text,
                        original_text=text,
                        page_number=1,
                        source_text=text,
                        verification_status="confirmed",
                        extractor_version=PROCESSOR_VERSION,
                    )
                )
            created += 1

    print(f"Seeded {created} synthetic imaging studies.")


if __name__ == "__main__":
    main()
