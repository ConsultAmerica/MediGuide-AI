"""Global search over the user's own MediGuide records — Documents,
verified lab observations, verified imaging studies, confirmed imaging
report sections, and confirmed medications.

This is deliberately not the RAG/vector-store educational-content search
(src/retriever.py, src/vector_store.py) — that indexes the approved
knowledge base, not the user's own records. Everything this module returns
is already verified/confirmed by construction: it reuses
src/database/timeline_repository.py's dedup-correct projection for four of
the five source types (so a search hit can never double-count a document
that's also an imaging report, the same guarantee the timeline gives), and
hand-queries ImagingReportSection directly for the one source type the
timeline never surfaces.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth.dependencies import require_user
from src.database.models import ImagingReportSection, ImagingStudy, User
from src.database.session import session_scope
from src.database.timeline_repository import get_timeline_entries
from src.imaging import MODALITY_LABELS
from src.labs.normalization import normalize_test_name

router = APIRouter(prefix="/api/search", tags=["Search"])

MIN_QUERY_LENGTH = 2
# No pagination/result-cap precedent exists anywhere else in this codebase —
# sized for a Cmd+K dropdown (this many rows per type is already more than
# should render un-scrolled), not derived from a query-cost measurement.
PER_TYPE_CAP = 8


@router.get("")
async def search_endpoint(q: str = "", user: User = Depends(require_user)) -> dict[str, Any]:
    query = q.strip()
    if len(query) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Search needs at least {MIN_QUERY_LENGTH} characters.",
        )
    with session_scope() as session:
        results = run_search(session, query, owner_id=user.id)
    return {"query": query, "results": results, "total": len(results)}


def _entry_to_result(
    entry: dict[str, Any], measurement: dict[str, Any] | None = None
) -> dict[str, Any]:
    """``measurement`` is the lab value the query matched, if any: the hit
    then opens on that value's own page with that field highlighted,
    rather than on the report's first page."""
    return {
        "result_id": entry["entry_id"],
        "type": entry["event_type"],
        "title": entry["title"],
        "subtitle": entry["subtitle"],
        "date": entry["date"],
        "document_id": entry["document_id"],
        "page_number": measurement["page_number"] if measurement else entry["page_number"],
        "field_id": measurement["field_id"] if measurement else None,
        "verification_status": "verified",
        "route": entry["route"],
    }


def _section_to_result(section: ImagingReportSection, study: ImagingStudy) -> dict[str, Any]:
    modality_label = MODALITY_LABELS.get(study.modality, study.modality.upper())
    title = f"{modality_label} — {study.body_region}" if study.body_region else modality_label
    return {
        "result_id": f"imaging_section:{section.id}",
        "type": "imaging_section",
        "title": f"{title} · {section.section_type.title()}",
        "subtitle": section.section_text[:120],
        "date": study.study_date.isoformat() if study.study_date else None,
        "document_id": section.document_id,
        "page_number": section.page_number,
        "field_id": None,
        "verification_status": "verified",
        "route": f"/workspace/imaging/{study.id}",
    }


def _search_imaging_report_sections(
    session: Session, query: str, *, owner_id: str | None, limit: int
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(ImagingReportSection, ImagingStudy)
        .join(ImagingStudy, ImagingReportSection.study_id == ImagingStudy.id)
        .where(
            ImagingStudy.owner_id == owner_id,
            ImagingReportSection.verification_status == "confirmed",
            ImagingReportSection.section_text.ilike(f"%{query}%"),
        )
        .limit(limit)
    ).all()
    return [_section_to_result(section, study) for section, study in rows]


def run_search(session: Session, query: str, *, owner_id: str | None) -> list[dict[str, Any]]:
    needle = query.lower()
    # Lab-name alias matching (e.g. "a1c"/"hba1c" -> "hemoglobin_a1c") reuses
    # the same normalization dictionary the extraction pipeline already
    # uses to name-match a raw test_code, rather than a new one.
    alias_code = normalize_test_name(query)

    entries = get_timeline_entries(session, owner_id=owner_id)
    per_type_counts: dict[str, int] = {}
    hits: list[dict[str, Any]] = []
    for entry in entries:
        result_type = entry["event_type"]
        if per_type_counts.get(result_type, 0) >= PER_TYPE_CAP:
            continue
        matched_measurement = next(
            (
                measurement
                for measurement in (entry["measurements"] or [])
                if needle in measurement["test_name"].lower()
                or measurement["test_code"] == alias_code
            ),
            None,
        )
        matched = (
            matched_measurement is not None
            or needle in entry["title"].lower()
            or needle in entry["subtitle"].lower()
        )
        if matched:
            hits.append(_entry_to_result(entry, matched_measurement))
            per_type_counts[result_type] = per_type_counts.get(result_type, 0) + 1

    hits.extend(_search_imaging_report_sections(
        session, query, owner_id=owner_id, limit=PER_TYPE_CAP
    ))

    return hits
