from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import MedicationRecord

# Label details kept as separate columns (strength never combined with
# dose or directions).
DETAIL_COLUMNS = (
    "medication_name", "brand_name", "generic_name", "strength", "form", "route", "dose",
    "frequency", "instructions", "quantity", "refills", "prescriber", "pharmacy",
    "prescription_date", "prescriber_or_pharmacy",
)


def _json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def utc_iso(value: datetime | None) -> str | None:
    """Stored as UTC; SQLite hands it back without a zone, so say so."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def serialize_medication_record(record: MedicationRecord) -> dict[str, Any]:
    return {
        "medication_id": record.id,
        "medication_name": record.medication_name,
        "brand_name": record.brand_name or "",
        "generic_name": record.generic_name or "",
        "strength": record.strength,
        "form": record.form,
        "dosage_form": record.form,
        "route": record.route or "",
        "dose": record.dose or "",
        "frequency": record.frequency or "",
        "instructions": record.instructions,
        "directions": record.instructions,
        "quantity": record.quantity,
        "refills": record.refills or "",
        "prescriber": record.prescriber or "",
        "pharmacy": record.pharmacy or "",
        "prescriber_or_pharmacy": record.prescriber_or_pharmacy,
        "prescription_date": record.prescription_date or "",
        "source": record.source,
        "filename": record.filename,
        "other_visible_text": record.other_visible_text,
        "source_session_id": record.source_session_id or "",
        "entry_index": record.entry_index or 0,
        "source_page": record.source_page,
        "text_source": record.text_source or "",
        # What was read before review, so corrections stay visible.
        "extracted": _json(record.extracted_snapshot, None),
        "review_flags": _json(record.review_flags, []),
        "acknowledged_records": _json(record.acknowledged_records, []),
        "confirmed_at": utc_iso(record.confirmed_at),
    }


def create_medication_record(
    session: Session,
    *,
    medication_id: str,
    medication_name: str = "",
    strength: str = "",
    form: str = "",
    instructions: str = "",
    quantity: str = "",
    prescriber_or_pharmacy: str = "",
    source: str = "upload",
    filename: str = "",
    other_visible_text: str = "",
    owner_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> MedicationRecord:
    """Idempotent on medication_id — a re-confirm updates the same row
    rather than accumulating duplicates, matching every other confirm-time
    upsert in this app (ExtractedField, ImagingReportSection).

    ``details`` carries the separate label details and audit columns
    (brand_name, dose, frequency, extracted_snapshot, review_flags...)."""
    record = session.get(MedicationRecord, medication_id)
    if record is None:
        record = MedicationRecord(id=medication_id, owner_id=owner_id)
        session.add(record)
    record.medication_name = medication_name
    record.strength = strength
    record.form = form
    record.instructions = instructions
    record.quantity = quantity
    record.prescriber_or_pharmacy = prescriber_or_pharmacy
    record.source = source
    record.filename = filename
    record.other_visible_text = other_visible_text
    for key, value in (details or {}).items():
        if key in {"extracted_snapshot", "review_flags", "acknowledged_records"}:
            setattr(record, key, json.dumps(value) if value is not None else None)
        elif hasattr(MedicationRecord, key):
            setattr(record, key, value)
    session.flush()
    return record


def get_medication_record(
    session: Session, medication_id: str, owner_id: str
) -> MedicationRecord | None:
    record = session.get(MedicationRecord, medication_id)
    if record is None or record.owner_id != owner_id:
        return None
    return record


def list_medication_records(session: Session, owner_id: str) -> list[MedicationRecord]:
    return list(
        session.execute(
            select(MedicationRecord)
            .where(MedicationRecord.owner_id == owner_id)
            .order_by(MedicationRecord.confirmed_at.asc(), MedicationRecord.id.asc())
        ).scalars().all()
    )
