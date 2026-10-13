"""Assign records created before accounts existed to one account.

Migration 008 adds owner_id to documents, imaging studies and medication
records but leaves existing rows unowned, and unowned rows are visible to
nobody. Run this once per deployment to hand them to their real owner:

    python scripts/claim_legacy_records.py --email you@example.com          # dry run
    python scripts/claim_legacy_records.py --email you@example.com --apply

The account must already exist (register it in the app first).
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import update

from src.auth.service import get_user_by_email
from src.database.models import Document, ImagingStudy, MedicationRecord
from src.database.session import init_db, session_scope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    args = parser.parse_args()

    init_db()
    with session_scope() as session:
        user = get_user_by_email(session, args.email)
        if user is None or user.is_guest:
            print(f"No registered account for {args.email}. Register it in the app first.")
            return 1
        for model in (Document, ImagingStudy, MedicationRecord):
            statement = update(model).where(model.owner_id.is_(None)).values(owner_id=user.id)
            if args.apply:
                count = session.execute(statement).rowcount
            else:
                count = session.query(model).filter(model.owner_id.is_(None)).count()
            print(f"{model.__tablename__}: {count} unowned row(s){' claimed' if args.apply else ''}")
        if not args.apply:
            session.rollback()
            print("Dry run only. Re-run with --apply to assign these rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
