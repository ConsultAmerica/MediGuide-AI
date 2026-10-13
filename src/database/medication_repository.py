from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.database.models import MedicationRecord


def serialize_medication_record(record: MedicationRecord) -> dict[str, Any]:
    return {
        "medication_id": record.id,
        "medication_name": record.medication_name,
        "strength": record.strength,
        "form": record.form,
        "instructions": record.instructions,
        "quantity": record.quantity,
        "prescriber_or_pharmacy": record.prescriber_or_pharmacy,
        "source": record.source,
        "filename": record.filename,
        "other_visible_text": record.other_visible_text,
        "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
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
) -> MedicationRecord:
    """Idempotent on medication_id — a re-confirm updates the same row
    rather than accumulating duplicates, matching every other confirm-time
    upsert in this app (ExtractedField, ImagingReportSection)."""
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
    session.flush()
    return record


def get_medication_record(
    session: Session, medication_id: str, owner_id: str
) -> MedicationRecord | None:
    record = session.get(MedicationRecord, medication_id)
    if record is None or record.owner_id != owner_id:
        return None
    return record
