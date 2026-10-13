"""Cross-domain read for the Unified Health Timeline.

This module deliberately lives outside every single-domain repository
(repository.py, imaging_repository.py, medication_repository.py): it reads
across Document/LabObservation/ImagingStudy/MedicationRecord but owns none
of them, and writes nothing. Every entry it returns is already
verified/confirmed by construction of the tables it reads — see the
per-category comments below — so this module adds no new verification
gate of its own to get wrong.

`get_timeline_entries()` is the full, unfiltered projection (kept exactly as
it always has been — the dedup logic here is what Phase 2 builds on, not
what it changes). `list_timeline_entries()` wraps it with type/date/search
filtering and keyset pagination for the `/api/timeline` route and for
`src/search.py`, which reuses this same dedup-correct projection rather than
re-querying the source tables itself.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.database.models import Document, ImagingStudy, LabObservation, MedicationRecord

# Reuses the existing modality label mapping rather than duplicating it.
from src.imaging import MODALITY_LABELS

HEADLINE_TEST_CODES = ["hemoglobin_a1c", "glucose"]


def _lab_subtitle(observations: list[LabObservation]) -> str:
    by_code = {obs.test_code: obs for obs in observations}
    chosen = [by_code[code] for code in HEADLINE_TEST_CODES if code in by_code]
    if len(chosen) < 2:
        remaining = [obs for obs in observations if obs.test_code not in HEADLINE_TEST_CODES]
        remaining.sort(key=lambda o: o.test_code)
        chosen.extend(remaining[: 2 - len(chosen)])

    parts = []
    for obs in chosen[:2]:
        value = obs.value_text or (
            f"{obs.value_numeric:g}" if obs.value_numeric is not None else ""
        )
        unit = f" {obs.unit}" if obs.unit else ""
        parts.append(f"{obs.test_name} {value}{unit}".strip())
    return " · ".join(parts)


def _imaging_title(study: ImagingStudy) -> str:
    modality_label = MODALITY_LABELS.get(study.modality, study.modality.upper())
    return f"{modality_label} — {study.body_region}" if study.body_region else modality_label


def _measurements(observations: list[LabObservation]) -> list[dict[str, Any]]:
    return [
        {
            "test_code": obs.test_code,
            "test_name": obs.test_name,
            "value_text": obs.value_text,
            "value_numeric": obs.value_numeric,
            "unit": obs.unit,
            "range_status": obs.range_status,
            "page_number": obs.page_number,
            # `field` may be missing if the owning ExtractedField was ever
            # deleted independently — fall back to the raw FK value so a
            # stale LabObservation never breaks the timeline outright.
            "field_id": obs.field.field_id if obs.field else obs.field_id,
        }
        for obs in sorted(observations, key=lambda o: o.test_code)
    ]


def get_timeline_entries(session: Session, *, owner_id: str | None) -> list[dict[str, Any]]:
    """Every verified entry belonging to ``owner_id``. Required on purpose:
    None selects only unowned legacy rows, never everyone's."""
    entries: list[dict[str, Any]] = []

    # Imaging: verification_status == "verified" is the same gate Imaging
    # Detail itself uses before treating a report as usable.
    imaging_studies = list(
        session.execute(
            select(ImagingStudy).where(
                ImagingStudy.owner_id == owner_id,
                ImagingStudy.verification_status == "verified",
                ImagingStudy.report_document_id.isnot(None),
            )
        ).scalars().all()
    )
    imaging_document_ids = {study.report_document_id for study in imaging_studies}

    for study in imaging_studies:
        entries.append({
            "entry_id": f"imaging:{study.id}",
            "date": study.study_date.isoformat() if study.study_date else None,
            "category": "imaging",
            "title": _imaging_title(study),
            "subtitle": "",
            "verification_label": "Verified report",
            "verified": True,
            "link": {"type": "imaging_study", "id": study.id},
            "event_type": "imaging",
            "source_type": "imaging_study",
            "source_id": study.id,
            "document_id": study.report_document_id,
            # A study has no single page of its own — page-level linkage
            # lives on ImagingReportSection, which the timeline doesn't
            # surface (see src/search.py for where it does get searched).
            "page_number": None,
            "route": f"/workspace/imaging/{study.id}",
            "is_demo": False,
            "measurements": None,
        })

    # Labs + generic documents: every confirmed Document not already shown
    # as an Imaging entry. LabObservation rows are only ever written with
    # verification_state="confirmed" (upsert_confirmed_document), so their
    # mere presence already means confirmed — no extra filter needed.
    documents = list(
        session.execute(select(Document).where(Document.owner_id == owner_id, Document.confirmed.is_(True))).scalars().all()
    )

    for document in documents:
        if document.id in imaging_document_ids:
            continue

        observations = list(
            session.execute(
                select(LabObservation)
                .where(LabObservation.document_id == document.id)
                .options(selectinload(LabObservation.field))
            ).scalars().all()
        )
        date_value = document.report_date.isoformat() if document.report_date else None

        if observations:
            count = len(observations)
            page_numbers = {obs.page_number for obs in observations}
            shared_page = observations[0].page_number if len(page_numbers) == 1 else None
            entries.append({
                "entry_id": f"lab:{document.id}",
                "date": date_value,
                "category": "laboratory",
                "title": "Lab Report",
                "subtitle": _lab_subtitle(observations),
                "verification_label": f"{count} verified measurement{'s' if count != 1 else ''}",
                "verified": True,
                "link": {"type": "document", "id": document.id},
                "event_type": "laboratory",
                "source_type": "document",
                "source_id": document.id,
                "document_id": document.id,
                "page_number": shared_page,
                "route": (
                    f"/workspace/documents/{document.id}"
                    + (f"?page={shared_page}" if shared_page else "")
                ),
                "is_demo": False,
                "measurements": _measurements(observations),
            })
        else:
            entries.append({
                "entry_id": f"document:{document.id}",
                "date": date_value,
                "category": "document",
                "title": document.filename or "Document",
                "subtitle": "",
                "verification_label": "Confirmed",
                "verified": True,
                "link": {"type": "document", "id": document.id},
                "event_type": "document",
                "source_type": "document",
                "source_id": document.id,
                "document_id": document.id,
                "page_number": 1,
                "route": f"/workspace/documents/{document.id}",
                "is_demo": False,
                "measurements": None,
            })

    # Medications: a row only ever exists once confirmed (see
    # medication_workspace.py's confirm()), so presence alone means verified.
    medications = list(session.execute(
        select(MedicationRecord).where(MedicationRecord.owner_id == owner_id)
    ).scalars().all())
    for record in medications:
        entries.append({
            "entry_id": f"medication:{record.id}",
            "date": record.confirmed_at.date().isoformat() if record.confirmed_at else None,
            "category": "medication",
            "title": "Medication label added" if record.source == "upload" else "Medication added",
            "subtitle": record.medication_name,
            "verification_label": "User verified",
            "verified": True,
            "link": {"type": "medication", "id": record.id},
            "event_type": "medication",
            "source_type": "medication",
            "source_id": record.id,
            # MedicationRecord deliberately has no FK to any document (see
            # its own model docstring) — nothing to link to.
            "document_id": None,
            "page_number": None,
            # No dedicated medication detail route exists; the UI opens a
            # drawer in place rather than navigating away.
            "route": "/workspace/timeline",
            "is_demo": False,
            "measurements": None,
        })

    # Descending by (date, entry_id): undated entries last ("" sorts before
    # any real ISO date string, so it naturally falls to the end under
    # reverse=True), entry_id as a tiebreaker so two same-date entries have
    # a stable, deterministic order — required for keyset pagination below
    # to never skip or duplicate a row across pages.
    entries.sort(key=lambda entry: (entry["date"] or "", entry["entry_id"]), reverse=True)
    return entries


def _make_cursor(entry: dict[str, Any]) -> str:
    payload = json.dumps({"date": entry["date"], "entry_id": entry["entry_id"]})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _entries_after_cursor(entries: list[dict[str, Any]], cursor: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        cursor_key = (payload["date"] or "", payload["entry_id"])
    except Exception as error:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor.") from error

    for index, entry in enumerate(entries):
        if (entry["date"] or "", entry["entry_id"]) == cursor_key:
            return entries[index + 1 :]
    # Cursor no longer matches anything (underlying data changed between
    # requests) — an empty next page is the safe behavior, not an error.
    return []


def list_timeline_entries(
    session: Session,
    *,
    owner_id: str | None,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Filtered, paginated view over `get_timeline_entries()`.

    Filtering happens in Python over the already-merged, already-deduped
    list rather than pushing each filter down into its own per-type SQL
    query — correct and simple at this app's single-tenant, demo-app scale
    (see module docstring); revisit only if that stops being true.
    """
    entries = get_timeline_entries(session, owner_id=owner_id)

    if event_type:
        entries = [entry for entry in entries if entry["event_type"] == event_type]
    if date_from:
        # A date filter implies "has a date" — undated entries can't satisfy
        # either bound, so they're correctly excluded once either is set.
        entries = [entry for entry in entries if entry["date"] and entry["date"] >= date_from]
    if date_to:
        entries = [entry for entry in entries if entry["date"] and entry["date"] <= date_to]
    if search:
        # Shallow substring match on what's already on screen — deliberately
        # not alias-aware (e.g. "a1c" won't match "Hemoglobin A1C" here).
        # Alias-aware matching belongs to GET /api/search (src/search.py);
        # conflating the two would make this filter's behavior surprising
        # (typing a lab alias would silently pull in unrelated entries).
        needle = search.strip().lower()
        entries = [
            entry
            for entry in entries
            if needle in entry["title"].lower()
            or needle in entry["subtitle"].lower()
            or any(needle in m["test_name"].lower() for m in (entry["measurements"] or []))
        ]

    total_matched = len(entries)

    if cursor:
        entries = _entries_after_cursor(entries, cursor)

    page = entries[: limit + 1]
    has_more = len(page) > limit
    page = page[:limit]
    next_cursor = _make_cursor(page[-1]) if has_more and page else None

    return {"entries": page, "next_cursor": next_cursor, "total_matched": total_matched}
