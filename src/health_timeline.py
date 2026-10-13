"""Unified Health Timeline: a read-only, cross-domain index over already
verified/confirmed data (Labs, Imaging, Documents, Medications). It builds
nothing new to look at — every entry links back to its existing detail
view. See src/database/timeline_repository.py for the aggregation query
and the classification rules (why an entry becomes Imaging vs Laboratory
vs Document vs Medication).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.auth.dependencies import require_user
from src.database.models import User

from src.database.session import probe_database, session_scope
from src.database.timeline_repository import get_timeline_entries, list_timeline_entries

router = APIRouter(prefix="/api/timeline", tags=["Health Timeline"])


@router.get("")
async def list_timeline_entries_endpoint(
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    with session_scope() as session:
        return list_timeline_entries(
            session,
            owner_id=user.id,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=limit,
            cursor=cursor,
        )


def probe_timeline() -> tuple[bool, str]:
    db_ok, db_detail = probe_database()
    if not db_ok:
        return False, db_detail
    try:
        with session_scope() as session:
            get_timeline_entries(session, owner_id=None)
        return True, "Timeline reachable"
    except Exception as error:
        return False, f"Unreadable ({type(error).__name__})"
