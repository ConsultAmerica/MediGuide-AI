from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from src.database.models import Document, ImagingFinding, ImagingReportSection, ImagingStudy
from src.imaging_findings import (
    FINDING_EXTRACTOR_VERSION,
    detect_report_gaps,
    extract_findings_from_sections,
    short_summary_label,
)


def _json(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def serialize_study(study: ImagingStudy) -> dict[str, Any]:
    page_count = None
    session = object_session(study)
    if session is not None and study.report_document_id:
        document = session.get(Document, study.report_document_id)
        page_count = document.page_count if document is not None else None
    return {
        "study_id": study.id,
        "modality": study.modality,
        "body_region": study.body_region,
        "study_description": study.study_description,
        "study_date": study.study_date.isoformat() if study.study_date else None,
        "institution": study.institution,
        "report_document_id": study.report_document_id,
        "report_page_count": page_count,
        # What the report itself says about the study, and what was applied.
        "report_details": _json(study.report_details),
        "verification_status": study.verification_status,
        "created_at": study.created_at.isoformat() if study.created_at else None,
    }


def serialize_section(section: ImagingReportSection) -> dict[str, Any]:
    source_map = _json(section.source_map) or {}
    return {
        "section_id": section.id,
        "study_id": section.study_id,
        "document_id": section.document_id,
        "section_type": section.section_type,
        "section_text": section.section_text,
        # The radiologist's wording exactly as extracted; never overwritten.
        "original_text": section.original_text,
        "page_number": section.page_number,
        "page_end": section.page_end or section.page_number,
        "source_text": section.source_text,
        "verification_status": section.verification_status,
        "extraction_method": section.extraction_method or "",
        "source_regions": source_map.get("regions", []),
        "line_start": source_map.get("line_start"),
        "line_end": source_map.get("line_end"),
        "boundary_adjusted": bool(source_map.get("boundary_adjusted")),
        "reviewed_at": _utc_iso(section.reviewed_at),
    }


def create_study(
    session: Session,
    *,
    modality: str,
    body_region: str = "",
    study_description: str = "",
    study_date: date | None = None,
    institution: str = "",
    accession_identifier: str = "",
    owner_id: str | None = None,
) -> ImagingStudy:
    study = ImagingStudy(
        owner_id=owner_id,
        modality=modality,
        body_region=body_region,
        study_description=study_description,
        study_date=study_date,
        institution=institution,
        accession_identifier=accession_identifier,
    )
    session.add(study)
    session.flush()
    return study


def get_study(session: Session, study_id: str) -> ImagingStudy | None:
    return session.get(ImagingStudy, study_id)


def get_owned_study(session: Session, study_id: str, owner_id: str) -> ImagingStudy | None:
    study = session.get(ImagingStudy, study_id)
    if study is None or study.owner_id != owner_id:
        return None
    return study


def list_studies(
    session: Session,
    *,
    owner_id: str,
    modality: str | None = None,
    body_region: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ImagingStudy]:
    stmt = select(ImagingStudy).where(ImagingStudy.owner_id == owner_id)
    if modality:
        stmt = stmt.where(ImagingStudy.modality == modality)
    if body_region:
        stmt = stmt.where(ImagingStudy.body_region.ilike(f"%{body_region}%"))
    if date_from:
        stmt = stmt.where(ImagingStudy.study_date >= date_from)
    if date_to:
        stmt = stmt.where(ImagingStudy.study_date <= date_to)
    stmt = stmt.order_by(ImagingStudy.study_date.desc().nulls_last())
    return list(session.execute(stmt).scalars().all())


def modality_summary(session: Session, owner_id: str | None) -> list[dict[str, Any]]:
    stmt = select(
        ImagingStudy.modality,
        func.count(ImagingStudy.id),
        func.max(ImagingStudy.study_date),
    )
    if owner_id is not None:
        stmt = stmt.where(ImagingStudy.owner_id == owner_id)
    rows = session.execute(stmt.group_by(ImagingStudy.modality)).all()
    return [
        {
            "modality": modality,
            "study_count": count,
            "latest_study_date": latest.isoformat() if latest else None,
        }
        for modality, count, latest in rows
    ]


def delete_study(session: Session, study_id: str) -> bool:
    """Deletes the study and its sections only — the underlying shared
    Document (the uploaded report file) is never deleted by this call."""
    study = session.get(ImagingStudy, study_id)
    if study is None:
        return False
    session.delete(study)
    session.flush()
    return True


def set_study_report_document(session: Session, study_id: str, document_id: str) -> None:
    study = session.get(ImagingStudy, study_id)
    if study is not None:
        study.report_document_id = document_id
        study.pending_report_document_id = None
        session.flush()


def set_pending_report_document(session: Session, study_id: str, document_id: str | None) -> None:
    """Marks (or clears) the in-flight report-upload attempt for a study —
    see ImagingStudy.pending_report_document_id's docstring."""
    study = session.get(ImagingStudy, study_id)
    if study is not None:
        study.pending_report_document_id = document_id
        session.flush()


def set_study_verification_status(session: Session, study_id: str, status: str) -> None:
    study = session.get(ImagingStudy, study_id)
    if study is not None:
        study.verification_status = status
        session.flush()


def upsert_report_sections(
    session: Session,
    *,
    study_id: str,
    document_id: str,
    sections: dict[str, str],
    page_number: int,
    extractor_version: str,
    source_text: str = "",
) -> list[ImagingReportSection]:
    """Replaces this document's extracted (unverified) sections in place —
    a retried/re-run extraction updates the same rows rather than
    accumulating duplicates, matching uq_imaging_report_section."""
    existing = {
        row.section_type: row
        for row in session.execute(
            select(ImagingReportSection).where(ImagingReportSection.document_id == document_id)
        ).scalars().all()
    }

    result: list[ImagingReportSection] = []
    for section_type, text in sections.items():
        row = existing.get(section_type)
        if row is None:
            row = ImagingReportSection(
                study_id=study_id,
                document_id=document_id,
                section_type=section_type,
            )
            session.add(row)
        row.section_text = text
        row.original_text = text
        row.page_number = page_number
        row.source_text = source_text or text
        row.verification_status = "unverified"
        row.extractor_version = extractor_version
        result.append(row)

    session.flush()
    return result


def replace_report_sections(
    session: Session,
    *,
    study_id: str,
    document_id: str,
    spans: list[dict[str, Any]],
    extractor_version: str,
    boundary_adjusted: bool = False,
) -> list[ImagingReportSection]:
    """Replaces this document's sections with ``spans`` (each: section_type,
    text, page_start, page_end, extraction_method, line_start, line_end,
    regions). Used for a fresh extraction and for a reviewer's boundary
    correction; either way every section starts unreviewed and its
    original_text is the report's own wording for that span."""
    for row in session.execute(
        select(ImagingReportSection).where(ImagingReportSection.document_id == document_id)
    ).scalars().all():
        session.delete(row)
    session.flush()
    result: list[ImagingReportSection] = []
    for span in spans:
        row = ImagingReportSection(
            study_id=study_id,
            document_id=document_id,
            section_type=span["section_type"],
            section_text=span["text"],
            original_text=span["text"],
            source_text=span["text"],
            page_number=int(span.get("page_start") or 1),
            page_end=int(span.get("page_end") or span.get("page_start") or 1),
            verification_status="unverified",
            extractor_version=extractor_version,
            extraction_method=span.get("extraction_method") or "",
            source_map=json.dumps({
                "line_start": span.get("line_start"),
                "line_end": span.get("line_end"),
                "regions": span.get("regions") or [],
                "boundary_adjusted": bool(span.get("boundary_adjusted", boundary_adjusted)),
            }),
        )
        session.add(row)
        result.append(row)
    session.flush()
    return result


SECTION_DECISIONS = {"confirmed", "rejected", "unverified"}


def decide_report_section(
    session: Session,
    *,
    document_id: str,
    section_type: str,
    decision: str,
    text: str | None = None,
) -> ImagingReportSection | None:
    """Records the reviewer's decision on one section, immediately, so a
    review can be left and resumed. A correction only replaces
    section_text; original_text keeps the radiologist's wording. Rejecting a
    section also rejects its not-yet-reviewed findings (so rejected wording
    never reaches the verified overview); undoing restores them."""
    row = session.execute(
        select(ImagingReportSection).where(
            ImagingReportSection.document_id == document_id,
            ImagingReportSection.section_type == section_type,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if text is not None and decision == "confirmed":
        row.section_text = text
    if decision == "unverified":
        row.section_text = row.original_text
    row.verification_status = decision
    row.reviewed_at = datetime.now(timezone.utc) if decision != "unverified" else None
    findings = session.execute(
        select(ImagingFinding).where(
            ImagingFinding.document_id == document_id,
            ImagingFinding.section_type == section_type,
        )
    ).scalars().all()
    for finding in findings:
        if decision == "rejected" and finding.verification_status == "unverified":
            finding.verification_status = "rejected"
        elif decision != "rejected" and finding.verification_status == "rejected":
            finding.verification_status = "unverified"
    session.flush()
    return row


def get_report_sections(session: Session, document_id: str) -> list[ImagingReportSection]:
    return list(
        session.execute(
            select(ImagingReportSection)
            .where(ImagingReportSection.document_id == document_id)
            .order_by(ImagingReportSection.section_type)
        ).scalars().all()
    )


def confirm_report_sections(
    session: Session,
    *,
    document_id: str,
    edits: dict[str, str],
    confirm_types: set[str] | None = None,
) -> list[ImagingReportSection]:
    """Applies user edits (if any) and marks the reviewed sections confirmed.
    The original extracted text (original_text) is never overwritten,
    mirroring the extracted_value/confirmed_value discipline used for lab
    fields. `confirm_types=None` confirms every section (the original
    all-or-nothing behavior); a given set confirms only those section types,
    leaving the rest at their current status so a report can be verified
    incrementally without ever auto-confirming sections the user hasn't
    actually reviewed."""
    rows = get_report_sections(session, document_id)
    for row in rows:
        if row.section_type in edits:
            row.section_text = edits[row.section_type]
        if confirm_types is None or row.section_type in confirm_types:
            row.verification_status = "confirmed"
            row.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    return rows


def derive_study_verification_status(rows: list[ImagingReportSection]) -> str:
    """Study-level status is a pure function of its sections' decisions:
    verified once every section is decided (confirmed or rejected) and at
    least one is confirmed, partially_verified once some are decided,
    unverified otherwise. Rejected sections never count as verified text."""
    if not rows:
        return "unverified"
    confirmed = sum(1 for row in rows if row.verification_status == "confirmed")
    decided = sum(1 for row in rows if row.verification_status in {"confirmed", "rejected"})
    if decided == len(rows) and confirmed > 0:
        return "verified"
    if decided > 0:
        return "partially_verified"
    return "unverified"


def serialize_finding(finding: ImagingFinding) -> dict[str, Any]:
    return {
        "finding_id": finding.id,
        "study_id": finding.study_id,
        "report_section_id": finding.report_section_id,
        "section": finding.section_type,
        "ordinal": finding.ordinal,
        "finding_text": finding.confirmed_text or finding.original_text,
        "original_text": finding.original_text,
        "confirmed_text": finding.confirmed_text,
        "normalized_concept": finding.normalized_concept,
        "anatomy": finding.anatomy,
        "laterality": finding.laterality,
        "source_document_id": finding.document_id,
        "source_page": finding.page_number,
        "summary_label": short_summary_label(
            finding.confirmed_text or finding.original_text,
            finding.normalized_concept,
        ),
        "verification_status": finding.verification_status,
        "bbox": (
            {
                "x": finding.bbox_x,
                "y": finding.bbox_y,
                "width": finding.bbox_width,
                "height": finding.bbox_height,
            }
            if finding.bbox_x is not None and finding.bbox_y is not None
            else None
        ),
    }


def upsert_findings_from_sections(
    session: Session,
    *,
    study_id: str,
    document_id: str,
    sections: list[ImagingReportSection],
    page_texts: dict[str, list[tuple[int, str]]] | None = None,
) -> list[ImagingFinding]:
    """Replace this document's extracted findings from section text.

    Original extracted wording is reset on re-extraction (same as sections).
    ``page_texts`` (section type -> [(page, text on that page)]) lets a
    finding in a section that spans pages point at the page its own wording
    is on, not just the page the section starts on.
    """
    section_map = {row.section_type: row.section_text for row in sections}
    page_map = {row.section_type: row.page_number for row in sections}
    section_ids = {row.section_type: row.id for row in sections}
    extracted = extract_findings_from_sections(section_map, page_by_section=page_map)

    existing = list(
        session.execute(
            select(ImagingFinding).where(ImagingFinding.document_id == document_id)
        ).scalars().all()
    )
    for row in existing:
        session.delete(row)
    session.flush()

    result: list[ImagingFinding] = []
    for item in extracted:
        located = _page_of(item["original_text"], (page_texts or {}).get(item["section_type"], []))
        if located:
            item["page_number"] = located
        finding = ImagingFinding(
            study_id=study_id,
            document_id=document_id,
            report_section_id=section_ids.get(item["section_type"]),
            section_type=item["section_type"],
            ordinal=item["ordinal"],
            original_text=item["original_text"],
            confirmed_text=item["confirmed_text"],
            source_text=item["source_text"],
            normalized_concept=item["normalized_concept"],
            anatomy=item["anatomy"],
            laterality=item["laterality"],
            page_number=item["page_number"],
            verification_status="unverified",
            extractor_version=FINDING_EXTRACTOR_VERSION,
        )
        session.add(finding)
        result.append(finding)
    session.flush()
    return result


def _squash(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _page_of(text: str, pages: list[tuple[int, str]]) -> int | None:
    """The page whose text contains the start of ``text`` (None if unsure)."""
    probe = _squash(text)[:40]
    if not probe:
        return None
    for page, page_text in pages:
        if probe in _squash(page_text):
            return page
    return None


def get_findings(session: Session, study_id: str) -> list[ImagingFinding]:
    """Findings from the study's current report only — never a mix of an
    earlier upload's rows with the current one's."""
    study = session.get(ImagingStudy, study_id)
    if study is None or not study.report_document_id:
        return []
    return list(
        session.execute(
            select(ImagingFinding)
            .where(
                ImagingFinding.study_id == study_id,
                ImagingFinding.document_id == study.report_document_id,
            )
            .order_by(ImagingFinding.ordinal, ImagingFinding.created_at)
        ).scalars().all()
    )


def get_finding(session: Session, finding_id: str) -> ImagingFinding | None:
    return session.get(ImagingFinding, finding_id)


def confirm_findings(
    session: Session,
    *,
    study_id: str,
    updates: list[dict[str, Any]],
) -> list[ImagingFinding]:
    """Apply per-finding confirm/edit/reject/could_not_read.

    original_text is never overwritten.
    """
    by_id = {row.id: row for row in get_findings(session, study_id)}
    allowed = {"confirmed", "rejected", "could_not_read", "unverified"}
    for item in updates:
        finding = by_id.get(item.get("finding_id", ""))
        if finding is None:
            continue
        status = item.get("verification_status") or "confirmed"
        if status not in allowed:
            continue
        if "confirmed_text" in item and item["confirmed_text"] is not None:
            finding.confirmed_text = str(item["confirmed_text"])
        finding.verification_status = status
    session.flush()
    return get_findings(session, study_id)


def report_gaps_for_study(session: Session, study_id: str) -> list[dict[str, str]]:
    study = get_study(session, study_id)
    if study is None or not study.report_document_id:
        return []
    sections = get_report_sections(session, study.report_document_id)
    findings = get_findings(session, study_id)
    blob = "\n".join(f"{s.section_type}\n{s.section_text}\n{s.original_text}" for s in sections)
    return detect_report_gaps(
        blob,
        [
            {
                "original_text": f.original_text,
                "confirmed_text": f.confirmed_text,
                "normalized_concept": f.normalized_concept,
            }
            for f in findings
        ],
    )
