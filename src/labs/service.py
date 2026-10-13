from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.database.repository import (
    delete_document_observations,
    delete_observation,
    get_latest_lab_summary,
    get_observation,
    get_timeline,
    list_tracked_tests,
    upsert_confirmed_document,
)
from src.database.session import init_db, session_scope


def ensure_db() -> None:
    init_db()


def create_observations_from_document(
    session: Session,
    *,
    document_id: str,
    filename: str,
    page_count: int,
    pages: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    report_date: str | None = None,
    storage_path: str = "",
) -> dict[str, Any]:
    """Persists a confirmation inside the caller's transaction, so a failure
    anywhere in it leaves nothing half-written."""
    document = upsert_confirmed_document(
        session,
        document_id=document_id,
        filename=filename,
        page_count=page_count,
        pages=pages,
        fields=fields,
        report_date=report_date,
        storage_path=storage_path,
    )
    return {
        "document_id": document.id,
        "lab_observation_count": len(document.lab_observations),
        "tracked_test_codes": getattr(document, "_tracked_test_codes", []),
        "confirmed": True,
    }


def list_tests(owner_id: str) -> list[dict[str, Any]]:
    ensure_db()
    with session_scope() as session:
        return list_tracked_tests(session, owner_id)


def timeline_for_test(test_code: str, owner_id: str) -> list[dict[str, Any]]:
    ensure_db()
    with session_scope() as session:
        return get_timeline(session, test_code, owner_id)


def get_observation_detail(observation_id: str, owner_id: str) -> dict[str, Any] | None:
    ensure_db()
    with session_scope() as session:
        return get_observation(session, observation_id, owner_id)


def latest_summary(owner_id: str) -> list[dict[str, Any]]:
    ensure_db()
    with session_scope() as session:
        return get_latest_lab_summary(session, owner_id)


def delete_lab_observation(observation_id: str, owner_id: str) -> bool:
    ensure_db()
    with session_scope() as session:
        return delete_observation(session, observation_id, owner_id)


def delete_document_labs(document_id: str, owner_id: str) -> int:
    ensure_db()
    with session_scope() as session:
        return delete_document_observations(session, document_id, owner_id)
