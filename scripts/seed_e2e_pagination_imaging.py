"""Seed N confirmed, verified imaging studies with a caller-supplied token in
the body region — used only by frontend/e2e/timeline-pagination.spec.ts.

Mirrors scripts/seed_demo_imaging.py's direct Document/ImagingStudy/
ImagingReportSection writes. The token lets that spec scope the Timeline's
own search filter to exactly the rows it seeded, since the e2e scratch DB is
shared cumulatively across every spec file in one `npm run test:e2e` run —
looping through the real "Add imaging study" UI N times per test was both
slow and, in practice, flaky, so this seeds directly like the demo script
does.

Rows are owned by the account in MEDIGUIDE_SEED_OWNER_ID (a user id). Without
it they are written unowned, and unowned rows are visible to no account.
"""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from src.database.models import Document, ImagingReportSection, ImagingStudy
from src.database.session import init_db, session_scope


def _seed_owner_id() -> str | None:
    owner_id = os.getenv("MEDIGUIDE_SEED_OWNER_ID", "").strip() or None
    if owner_id is None:
        print("warning: MEDIGUIDE_SEED_OWNER_ID is not set; seeded rows will be visible to no account")
    return owner_id


PROCESSOR_VERSION = "e2e-pagination-seed-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True)
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()

    init_db()
    owner_id = _seed_owner_id()
    with session_scope() as session:
        for i in range(args.count):
            study_date = date(2026, 1, 1) + timedelta(days=i)
            body_region = f"{args.token} Region {i}"
            document = Document(
                owner_id=owner_id,
                filename=f"{args.token}_{i}.pdf",
                page_count=1,
                status="confirmed",
                confirmed=True,
                report_date=study_date,
            )
            session.add(document)
            session.flush()

            study = ImagingStudy(
                owner_id=owner_id,
                modality="xray",
                body_region=body_region,
                study_description=f"X-Ray {body_region}",
                study_date=study_date,
                institution="MediGuide E2E Seed",
                report_document_id=document.id,
                verification_status="verified",
            )
            session.add(study)
            session.flush()

            sections = {
                "exam": f"X-Ray {body_region}.",
                "findings": "No acute abnormality.",
                "impression": "No acute abnormality.",
            }
            for section_type, text in sections.items():
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

    print(f"Seeded {args.count} imaging studies with token {args.token}")


if __name__ == "__main__":
    main()
