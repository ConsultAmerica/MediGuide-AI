from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.database.models import (
    Document,
    DocumentPage,
    ExtractedField,
    LabObservation,
    ProcessingJob,
)
from src.labs.normalization import (
    LAB_CATALOG,
    TRACKED_LAB_CODES,
    display_name_for,
    normalize_test_name,
    normalize_unit,
    parse_reference_range,
    parse_value,
    unit_key,
)

UNREAD_LINE_LABEL = "Unread line"


def _utcnow() -> datetime:
    """Naive UTC now — datetime.utcnow() is deprecated, but SQLite (via
    SQLAlchemy's DateTime(timezone=True)) round-trips datetimes as naive,
    so comparing a stored value against an aware "now" would silently
    apply the local UTC offset. Naive-UTC-vs-naive-UTC keeps job-timing
    comparisons (see start_job_attempt, stuck_job_count) correct."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_report_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def _bbox_columns(bbox: Any) -> dict[str, float | None]:
    """(x0, y0, x1, y1) -> the bbox_* columns; empty when no real region."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return {}
    x0, y0, x1, y1 = (float(v) for v in bbox)
    return {"bbox_x": x0, "bbox_y": y0, "bbox_width": x1 - x0, "bbox_height": y1 - y0}


def is_result_date_label(label: str) -> bool:
    """A confirmed date field that dates results (not a date of birth)."""
    text = (label or "").strip().lower()
    return "date" in text and "birth" not in text and "dob" not in text


def _page_dates_from_fields(fields: list[dict[str, Any]]) -> dict[int, tuple[date, str]]:
    """Map page number -> (date, source) from confirmed date fields, where
    source is "collection" (when the sample was taken) or "report". A
    collection date always wins over a report date on the same page."""
    dates: dict[int, tuple[date, str]] = {}
    for raw_field in fields:
        label = str(raw_field.get("label") or "")
        if not is_result_date_label(label):
            continue
        parsed = _parse_report_date(str(raw_field.get("value") or ""))
        if not parsed:
            continue
        page_number = int(raw_field.get("page_number") or 1)
        source = "collection" if "collect" in label.lower() else "report"
        current = dates.get(page_number)
        if current and current[1] == "collection" and source != "collection":
            continue
        dates[page_number] = (parsed, source)
    return dates


def _document_date(page_dates: dict[int, tuple[date, str]]) -> tuple[date | None, str]:
    """The date for pages that print none: a collection date if any page
    has one, otherwise a report date, otherwise none (never invented)."""
    collection = [value for value, source in page_dates.values() if source == "collection"]
    if collection:
        return max(collection), "collection"
    reported = [value for value, source in page_dates.values() if source == "report"]
    if reported:
        return max(reported), "report"
    return None, ""


def _is_measurement(raw_field: dict[str, Any], code: str) -> bool:
    """A confirmed field that is a lab result: a known test, or a value that
    is a number (or a printed bound like <0.5). Dates, unread lines and
    free-text fields stay as confirmed fields only."""
    label = str(raw_field.get("label") or "").strip()
    value = str(raw_field.get("value") or "").strip()
    if not label or not value or label == UNREAD_LINE_LABEL:
        return False
    if raw_field.get("status") == "not_applicable" or is_result_date_label(label):
        return False
    if code in LAB_CATALOG:
        return True
    parsed = parse_value(value)
    return parsed.numeric is not None or bool(parsed.qualifier)


def _snapshot(field: ExtractedField | None) -> dict[str, Any] | None:
    if field is None or not field.extracted_snapshot:
        return None
    try:
        data = json.loads(field.extracted_snapshot)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _serialize_observation(item: LabObservation) -> dict[str, Any]:
    field = item.field
    logical_field_id = field.field_id if field else item.field_id
    confidence = item.confidence or (field.confidence if field else "")
    extraction_method = item.extraction_method or (field.extraction_method if field else "")
    range_status = item.range_status or (field.status if field else "unknown")
    date_value = item.report_date.isoformat() if item.report_date else None
    date_source = item.date_source or ("unknown" if date_value else "")
    printed_flag = (field.flag if field and field.flag else "") or (
        "H" if range_status == "flagged_high_on_report" else "L" if range_status == "flagged_low_on_report" else ""
    )
    parsed = parse_value(item.value_text)
    snapshot = _snapshot(field)
    bbox = None
    if field is not None and field.bbox_x is not None and field.bbox_width is not None:
        bbox = [field.bbox_x, field.bbox_y, field.bbox_x + field.bbox_width, field.bbox_y + (field.bbox_height or 0)]
    return {
        "observation_id": item.id,
        "test_code": item.test_code,
        "test_name": item.test_name,
        "normalized_name": item.test_code,
        # The name exactly as printed and confirmed, kept beside the
        # normalized one.
        "original_name": field.label if field else item.test_name,
        "value": item.value_numeric,
        "value_text": item.value_text,
        "value_qualifier": parsed.qualifier,
        # What extraction read before review, and what the reviewer kept.
        "extracted_value": (snapshot or {}).get("value") if snapshot else None,
        "confirmed_value": item.value_text,
        "unit": item.unit,
        "unit_key": unit_key(item.unit),
        "reference_low": item.reference_low,
        "reference_high": item.reference_high,
        "reference_range": item.reference_text,
        "reference_text": item.reference_text,
        "source_flag": printed_flag,
        "date": date_value,
        # collection | report | unknown (recorded before date sources were kept) | "" (no date)
        "date_source": date_source,
        "collection_date": date_value if date_source == "collection" else None,
        "report_date": date_value if date_source != "collection" else None,
        "verification_status": item.verification_state,
        "verification_state": item.verification_state,
        "review_status": (field.review_status if field else "") or "confirmed",
        # Stored as UTC; SQLite hands it back without a zone, so say so.
        "reviewed_at": (
            (field.reviewed_at if field.reviewed_at.tzinfo else field.reviewed_at.replace(tzinfo=timezone.utc)).isoformat()
            if field and field.reviewed_at else None
        ),
        # Extraction confidence only (clearly_visible | needs_review | could_not_read).
        # Not a medical-correctness score.
        "confidence": confidence,
        "range_status": range_status,
        "document_id": item.document_id,
        "document_name": item.document_name
        or (item.document.filename if item.document else ""),
        "source_page": item.page_number,
        "page_number": item.page_number,
        "source_text": field.source_text if field else "",
        "source_bbox": bbox,
        "field_id": logical_field_id,
        "extraction_method": extraction_method or "",
        "preview_path": (
            f"/api/documents/v2/{item.document_id}/pages/{item.page_number}/preview"
        ),
    }


def create_uploaded_document(
    session: Session,
    *,
    document_id: str,
    filename: str,
    content_type: str = "",
    storage_path: str = "",
    owner_id: str | None = None,
) -> Document:
    """Persists a Document row immediately on upload, before any extraction
    has run, so a processing job always has a stable row to attach to."""
    document = session.get(Document, document_id)
    if document is None:
        document = Document(id=document_id, filename=filename, owner_id=owner_id)
        session.add(document)
    document.filename = filename
    document.content_type = content_type
    document.storage_path = storage_path
    document.status = "uploaded"
    session.flush()
    return document


def get_owned_document(session: Session, document_id: str, owner_id: str) -> Document | None:
    document = session.get(Document, document_id)
    if document is None or document.owner_id != owner_id:
        return None
    return document


def owned_document_ids(session: Session, owner_id: str) -> set[str]:
    return set(
        session.execute(select(Document.id).where(Document.owner_id == owner_id)).scalars().all()
    )


def document_exists(session: Session, document_id: str) -> bool:
    return session.get(Document, document_id) is not None


def set_document_status(session: Session, document_id: str, status: str) -> None:
    document = session.get(Document, document_id)
    if document is not None:
        document.status = status
        session.flush()


def add_document_page(
    session: Session,
    *,
    document_id: str,
    page_number: int,
    preview_path: str = "",
    text_available: bool = False,
) -> DocumentPage:
    page = session.execute(
        select(DocumentPage).where(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()
    if page is None:
        page = DocumentPage(document_id=document_id, page_number=page_number)
        session.add(page)
    page.preview_path = preview_path
    page.text_available = text_available
    session.flush()
    return page


def set_document_page_count(session: Session, document_id: str, page_count: int) -> None:
    document = session.get(Document, document_id)
    if document is not None:
        document.page_count = page_count
        session.flush()


def get_or_create_job(session: Session, *, document_id: str, job_type: str) -> ProcessingJob:
    job = session.execute(
        select(ProcessingJob).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.job_type == job_type,
        )
    ).scalar_one_or_none()
    if job is None:
        job = ProcessingJob(document_id=document_id, job_type=job_type)
        session.add(job)
        session.flush()
    return job


def start_job_attempt(session: Session, job: ProcessingJob, *, processor_version: str) -> None:
    """Begins (or retries) an attempt on an existing job row in place —
    never inserts a second row for the same (document_id, job_type)."""
    job.attempt_count += 1
    job.status = "running"
    job.stage = "validating"
    job.started_at = _utcnow()
    job.completed_at = None
    job.error_code = ""
    job.safe_error_message = ""
    job.technical_error = ""
    job.retryable = False
    job.retry_attempt = 0
    job.retry_max = 0
    job.processor_version = processor_version
    session.flush()


def update_job_stage(session: Session, job: ProcessingJob, stage: str) -> None:
    job.stage = stage
    if stage != "waiting_for_service":
        # Leaving the waiting state (a page moved past its stuck Ollama
        # call, or a fresh attempt began) — the in-flight retry counter no
        # longer describes the current stage, so clear it rather than show
        # a stale "Attempt 2 of 3" once things are moving again.
        job.retry_attempt = 0
        job.retry_max = 0
    session.flush()


def record_retry_progress(
    session: Session, job: ProcessingJob, *, attempt: int, max_attempts: int
) -> None:
    """Records live automatic-retry progress for the current attempt —
    distinct from ``attempt_count``, which only increments across manual
    retries. Reset whenever the job leaves the "waiting_for_service" stage
    (see ``update_job_stage``)."""
    job.stage = "waiting_for_service"
    job.retry_attempt = attempt
    job.retry_max = max_attempts
    session.flush()


def complete_job(session: Session, job: ProcessingJob) -> None:
    job.status = "completed"
    job.stage = "review_required"
    job.retry_attempt = 0
    job.retry_max = 0
    job.completed_at = _utcnow()
    session.flush()


def fail_job(
    session: Session,
    job: ProcessingJob,
    *,
    error_code: str,
    safe_message: str,
    technical_detail: str,
    retryable: bool,
) -> None:
    job.status = "failed"
    job.completed_at = _utcnow()
    job.error_code = error_code
    job.safe_error_message = safe_message
    job.technical_error = technical_detail
    job.retryable = retryable
    session.flush()


def stuck_job_count(session: Session, *, stale_after_seconds: int) -> int:
    """Jobs left in 'running' past a staleness threshold — usually a sign
    the process was killed mid-extraction rather than failing cleanly."""
    now = _utcnow()
    rows = session.execute(
        select(ProcessingJob).where(ProcessingJob.status == "running")
    ).scalars().all()
    return sum(
        1
        for job in rows
        if job.started_at and (now - job.started_at).total_seconds() > stale_after_seconds
    )


def upsert_confirmed_document(
    session: Session,
    *,
    document_id: str,
    filename: str,
    page_count: int,
    pages: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    report_date: str | None = None,
    storage_path: str = "",
    owner_id: str | None = None,
) -> Document:
    """Persist a human-confirmed document and promote tracked labs.

    ``owner_id`` only applies when this call creates the row; an existing
    document's owner is never reassigned here."""
    document = session.get(Document, document_id)
    if document is None:
        document = Document(id=document_id, filename=filename, owner_id=owner_id)
        session.add(document)

    document.filename = filename
    document.page_count = page_count
    document.status = "confirmed"
    document.confirmed = True
    document.storage_path = storage_path or document.storage_path
    parsed_date = _parse_report_date(report_date)
    if parsed_date:
        document.report_date = parsed_date

    # Replace pages / fields / observations for this confirmation pass.
    for observation in list(document.lab_observations):
        session.delete(observation)
    for field in list(document.fields):
        session.delete(field)
    for page in list(document.pages):
        session.delete(page)
    session.flush()

    page_by_number: dict[int, DocumentPage] = {}
    for page_info in pages:
        page_number = int(page_info.get("page_number") or 1)
        page = DocumentPage(
            document_id=document.id,
            page_number=page_number,
            preview_path=str(page_info.get("preview_url") or ""),
            text_available=bool(page_info.get("text_available")),
        )
        session.add(page)
        page_by_number[page_number] = page

    session.flush()

    page_dates = _page_dates_from_fields(fields)
    fallback_date, fallback_source = _document_date(page_dates)
    if fallback_date:
        document.report_date = fallback_date

    for raw_field in fields:
        page_number = int(raw_field.get("page_number") or 1)
        page = page_by_number.get(page_number)
        if page is None:
            page = DocumentPage(
                document_id=document.id,
                page_number=page_number,
                text_available=False,
            )
            session.add(page)
            session.flush()
            page_by_number[page_number] = page

        field = ExtractedField(
            document_id=document.id,
            page_id=page.id,
            field_id=str(raw_field.get("field_id") or ""),
            label=str(raw_field.get("label") or ""),
            value=str(raw_field.get("value") or ""),
            unit=normalize_unit(str(raw_field.get("unit") or "")),
            reference_range=str(raw_field.get("reference_range") or ""),
            status=str(raw_field.get("status") or "unknown"),
            confidence=str(raw_field.get("confidence") or "needs_review"),
            page_number=page_number,
            source_text=str(raw_field.get("source_text") or ""),
            extraction_method=str(raw_field.get("extraction_method") or ""),
            user_edited=bool(raw_field.get("user_edited")),
            user_confirmed=True,
            # Audit trail: printed flag, source region, what extraction
            # originally read (kept even after a correction) and the decision.
            flag=str(raw_field.get("flag") or "")[:8],
            extracted_snapshot=json.dumps(raw_field["extracted"]) if raw_field.get("extracted") else None,
            review_status="corrected" if raw_field.get("user_edited") else "confirmed",
            reviewed_at=datetime.now(timezone.utc),
            **_bbox_columns(raw_field.get("source_bbox")),
        )
        session.add(field)
        session.flush()

        code = normalize_test_name(field.label)
        # Every confirmed result becomes an observation, not only a fixed
        # list of tests. Dates, unread lines and free text stay fields only.
        if not code or not _is_measurement(raw_field, code):
            continue

        low, high = parse_reference_range(field.reference_range)
        observation_date, date_source = page_dates.get(page_number) or (fallback_date, fallback_source)
        observation = LabObservation(
            document_id=document.id,
            field_id=field.id,
            page_number=page_number,
            test_code=code,
            test_name=display_name_for(code, field.label),
            # Only a plain number is plottable; "<0.5" stays text.
            value_numeric=parse_value(field.value).numeric,
            value_text=field.value,
            unit=field.unit,
            reference_low=low,
            reference_high=high,
            reference_text=field.reference_range,
            report_date=observation_date,
            date_source=date_source if observation_date else "",
            verification_state="confirmed",
            confidence=field.confidence,
            extraction_method=field.extraction_method,
            range_status=field.status,
            document_name=document.filename,
        )
        session.add(observation)

    session.flush()
    document._tracked_test_codes = sorted(
        {obs.test_code for obs in document.lab_observations}
    )
    return document


def _owned_observations(owner_id: str):
    """WHERE clause limiting LabObservation rows to one owner's documents."""
    return LabObservation.document_id.in_(
        select(Document.id).where(Document.owner_id == owner_id)
    )


def list_tracked_tests(session: Session, owner_id: str) -> list[dict[str, Any]]:
    """Every test the owner has confirmed results for (most first by name),
    then the core tests with no results yet, so the selector is never empty."""
    rows = session.execute(
        select(LabObservation.test_code, LabObservation.test_name, func.count(LabObservation.id))
        .where(_owned_observations(owner_id))
        .group_by(LabObservation.test_code, LabObservation.test_name)
    ).all()
    counts: dict[str, int] = {}
    names: dict[str, str] = {}
    for code, name, count in rows:
        counts[code] = counts.get(code, 0) + int(count)
        names.setdefault(code, display_name_for(code, name))
    present = sorted(counts, key=lambda code: names[code].lower())
    results = [
        {"test_code": code, "display_name": names[code], "observation_count": counts[code], "has_data": True}
        for code in present
    ]
    results.extend(
        {"test_code": code, "display_name": display, "observation_count": 0, "has_data": False}
        for code, display in TRACKED_LAB_CODES.items()
        if code not in counts
    )
    return results


def _value_key(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").replace(",", "")).lower()


def annotate_timeline(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Orders results by their date and marks what the chart may draw.

    A point is plotted only when it has a date, a plain numeric value, the
    same unit as the series and is not a repeat of another report's result.
    Everything else stays in the list with the reason it isn't drawn: no
    interpolation, no unit conversion, no guessing.
    """
    ordered = sorted(points, key=lambda point: (point["date"] is None, point["date"] or ""))
    # Same date, same unit, same value: the same result reported twice.
    first_seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    by_date_unit: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for point in ordered:
        point["duplicate_of"] = None
        point["duplicate_document_name"] = None
        point["conflicting_values"] = []
        if point["date"] is None:
            continue
        key = (point["date"], point["unit_key"], _value_key(point["value_text"]))
        original = first_seen.get(key)
        if original is not None:
            point["duplicate_of"] = original["observation_id"]
            point["duplicate_document_name"] = original["document_name"]
        else:
            first_seen[key] = point
            by_date_unit.setdefault((point["date"], point["unit_key"]), []).append(point)
    # Same date and unit but different values: shown, and called out.
    for group in by_date_unit.values():
        if len(group) > 1:
            for point in group:
                point["conflicting_values"] = [other["value_text"] for other in group if other is not point]

    numeric_dated = [p for p in ordered if p["value"] is not None and p["date"] and not p["duplicate_of"]]
    series_unit = numeric_dated[-1]["unit_key"] if numeric_dated else ""
    previous: dict[str, Any] | None = None
    for point in ordered:
        if point["duplicate_of"]:
            reason = "duplicate"
        elif point["value"] is None:
            reason = "qualified_value" if point["value_qualifier"] else "not_numeric"
        elif not point["date"]:
            reason = "no_date"
        elif point["unit_key"] != series_unit:
            reason = "different_unit"
        else:
            reason = ""
        point["plotted"] = not reason
        point["not_plotted_reason"] = reason or None
        point["change_from_previous"] = None
        point["change_direction"] = None
        if point["plotted"]:
            if previous is not None:
                delta = round(float(point["value"]) - float(previous["value"]), 3)
                point["change_from_previous"] = delta
                point["change_direction"] = "up" if delta > 0 else "down" if delta < 0 else "unchanged"
            previous = point
    return ordered


def get_timeline(session: Session, test_code: str, owner_id: str) -> list[dict[str, Any]]:
    code = normalize_test_name(test_code) if test_code not in LAB_CATALOG else test_code
    observations = session.execute(
        select(LabObservation)
        .where(LabObservation.test_code.in_({code, test_code}), _owned_observations(owner_id))
        .options(
            selectinload(LabObservation.document),
            selectinload(LabObservation.field),
        )
        .order_by(LabObservation.report_date.asc(), LabObservation.created_at.asc())
    ).scalars().all()
    return annotate_timeline([_serialize_observation(item) for item in observations])


def get_latest_lab_summary(session: Session, owner_id: str) -> list[dict[str, Any]]:
    """The latest dated, non-repeated result of each test with results."""
    summary: list[dict[str, Any]] = []
    for test in list_tracked_tests(session, owner_id):
        if not test["has_data"]:
            continue
        points = get_timeline(session, test["test_code"], owner_id)
        candidates = [p for p in points if p["date"] and not p["duplicate_of"]] or points
        if candidates:
            summary.append(candidates[-1])
    return summary


def _get_owned_observation(
    session: Session, observation_id: str, owner_id: str
) -> LabObservation | None:
    item = session.get(LabObservation, observation_id)
    if item is None or get_owned_document(session, item.document_id, owner_id) is None:
        return None
    return item


def get_observation(
    session: Session, observation_id: str, owner_id: str
) -> Optional[dict[str, Any]]:
    item = _get_owned_observation(session, observation_id, owner_id)
    if item is None:
        return None
    if item.field is None:
        session.refresh(item, attribute_names=["field", "document"])
    return _serialize_observation(item)


def delete_observation(session: Session, observation_id: str, owner_id: str) -> bool:
    item = _get_owned_observation(session, observation_id, owner_id)
    if item is None:
        return False
    session.delete(item)
    session.flush()
    return True


def delete_document_observations(session: Session, document_id: str, owner_id: str) -> int:
    """Deletes one owned document and its observations; 0 for anything
    the owner doesn't hold (callers report that as not-found)."""
    if get_owned_document(session, document_id, owner_id) is None:
        return 0
    observations = session.execute(
        select(LabObservation).where(LabObservation.document_id == document_id)
    ).scalars().all()
    count = len(observations)
    for item in observations:
        session.delete(item)
    document = session.get(Document, document_id)
    if document is not None:
        session.delete(document)
    session.flush()
    return count
