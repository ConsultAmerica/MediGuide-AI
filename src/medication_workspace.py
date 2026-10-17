from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

from src.config import (
    BASE_DIR,
    MAX_IMAGE_MB,
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT_SECONDS,
    PROCESSING_RETRY_ATTEMPTS,
    PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS,
    VISION_MODEL_NAME,
)
from src.database.medication_repository import (
    create_medication_record,
    get_medication_record,
    list_medication_records,
    serialize_medication_record,
    utc_iso,
)
from src.medications.label_parser import (
    FIELD_LABELS,
    FIELD_ORDER,
    LabelLine,
    comparable,
    compact,
    lines_from_text,
    name_key,
    parse_label,
)
from src.ocr import client_ocr, ocr_available, ocr_image, save_client_ocr
from src.auth.dependencies import not_found, require_user
from src.database.models import User
from src.database.session import session_scope
from src.document_intelligence import EvidenceSource, retrieve_approved_evidence
from src.image_validator import prepare_vision_image, validate_image_file
from src.observability.logging import get_logger
from src.shared import file_store
from src.safety import check_for_emergency
from src.shared.errors import MediGuideError
from src.shared.resilience import (
    PermanentProcessingError,
    TransientProcessingError,
    call_with_retry,
)

logger = get_logger(__name__)


def _ollama_client():
    try:
        from ollama import Client
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="The AI text/vision service is not installed on this deployment.",
        ) from error
    return Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)


router = APIRouter(prefix="/api/medications/v2", tags=["Medication Workspace V2"])

TEMP_DIR = Path(
    os.getenv("MED_WORKSPACE_TEMP_DIR", str(BASE_DIR / "outputs" / "medication_workspace"))
)
VISION_MODEL = VISION_MODEL_NAME
TEXT_MODEL = MODEL_NAME
MAX_MB = int(os.getenv("MED_WORKSPACE_MAX_MB", "20"))
RENDER_DPI = int(os.getenv("MED_WORKSPACE_RENDER_DPI", "140"))
RETENTION_MINUTES = int(os.getenv("MED_WORKSPACE_RETENTION_MINUTES", "120"))

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

Confidence = Literal["clearly_visible", "needs_review", "could_not_read", "not_found"]
Source = Literal["upload", "typed"]
Decision = Literal["unverified", "confirmed", "rejected"]

# Separate label details (see src/medications/label_parser.py).
MED_FIELD_LABELS: dict[str, str] = dict(FIELD_LABELS)
MED_FIELD_ORDER = list(FIELD_ORDER)
# Keys used before the label details were separated, mapped to today's.
LEGACY_KEYS = {"instructions": "directions", "form": "dosage_form", "prescriber_or_pharmacy": "pharmacy"}
OCR_TRUSTED_CONFIDENCE = 85.0

REVIEW_NOTES = {
    "missing_directions": "No directions were found on this label. Nothing has been filled in for how to take it.",
    "ambiguous_directions": "The directions are unclear (for example \"as directed\"). Check them with your pharmacist or prescriber.",
    "risky_abbreviation": "The directions use an abbreviation that is easy to misread (such as QD or QOD). Check what it means with your pharmacist.",
    "dose_range": "The directions give a range (for example 1-2 tablets), not a single amount.",
    "frequency_not_stated": "The directions don't say how often to take it.",
    "several_strengths": "More than one strength is printed on the medication line. Check which one applies.",
    "ai_read": "This label was read by the AI fallback because its text couldn't be read directly. Check every detail against the label.",
    "low_confidence_text": "Some of this label was hard to read. Check every detail against the label.",
}


class MedicationField(BaseModel):
    key: str
    label: str
    value: str = ""
    confidence: Confidence = "needs_review"
    source_text: str = ""
    user_edited: bool = False
    # e.g. "from_directions", "ambiguous_directions", "dose_range", "shared_detail"
    flags: list[str] = Field(default_factory=list)
    # What was read before review (None for fields added by hand).
    extracted: str | None = None
    page: int = 1


class MedicationEntry(BaseModel):
    """One medication found in the upload (a label has one; a list may have several)."""
    entry_id: str
    index: int = 0
    fields: list[MedicationField]
    review_notes: list[str] = Field(default_factory=list)
    decision: Decision = "unverified"
    record_id: str | None = None
    # Confirmed records with the same medication name: possible duplicates
    # or conflicting details, shown for review. Never merged.
    matches: list[dict[str, Any]] = Field(default_factory=list)


class MedicationState(BaseModel):
    medication_id: str
    source: Source
    filename: str = ""
    preview_url: str = ""
    status: str
    # Mirrors the first entry, for older readers of this session.
    fields: list[MedicationField]
    other_visible_text: str = ""
    confirmed: bool = False
    entries: list[MedicationEntry] = Field(default_factory=list)
    # The label text exactly as read, and how it was read:
    # typed | text_layer | ocr | vision
    label_text: str = ""
    text_source: str = ""


class TypedLabelRequest(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class ConfirmRequest(BaseModel):
    fields: list[MedicationField]
    reviewed_name_strength_instructions: bool
    acknowledged_record_ids: list[str] = Field(default_factory=list)


class EntryConfirmRequest(BaseModel):
    fields: list[MedicationField]
    reviewed: bool
    # Existing records the reviewer compared this one with (required when
    # the medication matches a record already confirmed).
    acknowledged_record_ids: list[str] = Field(default_factory=list)


class InfoRequest(BaseModel):
    question: str = ""
    entry_id: str | None = None


class MedicationInfoResponse(BaseModel):
    medication_id: str
    answer_markdown: str
    sources: list[EvidenceSource]
    limitations: list[str]


def _folder(medication_id: str) -> Path:
    return file_store.folder("medications", TEMP_DIR, medication_id)


def _state_path(medication_id: str) -> Path:
    return _folder(medication_id) / "state.json"


def _save_state(state: MedicationState) -> None:
    folder = _folder(state.medication_id)
    folder.mkdir(parents=True, exist_ok=True)
    _state_path(state.medication_id).write_text(
        json.dumps(state.model_dump(), indent=2),
        encoding="utf-8",
    )


def _load_state(medication_id: str) -> MedicationState:
    path = _state_path(medication_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Medication session not found.")
    return MedicationState.model_validate_json(path.read_text(encoding="utf-8"))


def _owner_path(medication_id: str) -> Path:
    return _folder(medication_id) / "owner"


def _claim_folder(medication_id: str, user: User) -> Path:
    """Creates the session folder and records who owns it. Review sessions
    live on disk rather than in the database until confirmed, so the owner
    is stored alongside them."""
    folder = _folder(medication_id)
    folder.mkdir(parents=True, exist_ok=True)
    _owner_path(medication_id).write_text(user.id, encoding="utf-8")
    return folder


def _load_owned_state(medication_id: str, user: User) -> MedicationState:
    try:
        owner = _owner_path(medication_id).read_text(encoding="utf-8").strip()
    except OSError:
        owner = ""
    if owner != user.id:
        raise not_found("Medication session")
    return _load_state(medication_id)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _cleanup_expired_sessions() -> None:
    """Best-effort sweep of stale medication sessions, mirroring the
    document-intelligence sweep since neither app has a background
    scheduler — cleanup piggybacks on the next upload instead.
    """
    if not TEMP_DIR.exists():
        return

    cutoff = time.time() - (RETENTION_MINUTES * 60)

    for session_dir in TEMP_DIR.iterdir():
        if not session_dir.is_dir():
            continue

        try:
            if session_dir.stat().st_mtime < cutoff:
                shutil.rmtree(session_dir, ignore_errors=True)
        except OSError:
            continue


MED_EXTRACTION_PROMPT = """
You are MediGuide's medication LABEL extraction engine.
Do not diagnose, dose, or recommend treatment changes. Extract only what is
visibly printed on the label or information sheet.

Return JSON only:
{
  "medication_name": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "strength": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "form": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "instructions": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "quantity": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "prescriber_or_pharmacy": {"value": "", "confidence": "clearly_visible", "source_text": ""},
  "other_visible_text": ""
}

Rules:
- Preserve medication names, numbers, units, and directions exactly as printed.
- "instructions" is the directions for use (the sig), e.g. "Take 1 tablet by mouth twice daily".
- confidence is one of: clearly_visible, needs_review, could_not_read.
- Use could_not_read with an empty value for anything not legible.
- Never invent a medication name, strength, or instruction that is not visible.
"""


def _build_fields(data: dict[str, Any]) -> tuple[list[MedicationField], str]:
    """Fields from the AI fallback's JSON. Its values are never trusted as
    clearly visible: every one is marked for review."""
    found: dict[str, MedicationField] = {}
    for old_key in ("medication_name", "strength", "form", "instructions", "quantity", "prescriber_or_pharmacy"):
        item = data.get(old_key) or {}
        if not isinstance(item, dict):
            item = {}
        key = LEGACY_KEYS.get(old_key, old_key)
        value = str(item.get("value", "")).strip()
        confidence = "needs_review" if value else "could_not_read"
        flags = ["ai_read"] + (["may_be_prescriber"] if old_key == "prescriber_or_pharmacy" and value else [])
        found[key] = MedicationField(
            key=key, label=MED_FIELD_LABELS[key], value=value, confidence=confidence,
            source_text=str(item.get("source_text", "")).strip(), flags=flags, extracted=value,
        )
    fields = [found.get(key) or MedicationField(key=key, label=MED_FIELD_LABELS[key], confidence="not_found", extracted="")
              for key in MED_FIELD_ORDER]
    other_text = str(data.get("other_visible_text", "")).strip()
    return fields, other_text


def _call_with_classification(fn, *, stage: str):
    """Runs an Ollama call with the same bounded retry/backoff and
    transient-vs-permanent classification document/imaging extraction use
    (see src/shared/resilience.py), raising a MediGuideError with a
    standardized code instead of leaking a raw exception type name to the
    client. No ProcessingJob row is created here — medication labels have
    no Document-backed job to attach one to (see MedicationRecord's
    docstring) — so retry state lives only within this one request."""
    try:
        return call_with_retry(
            fn,
            attempts=PROCESSING_RETRY_ATTEMPTS,
            backoff_schedule=PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS,
        )
    except TransientProcessingError as error:
        raise MediGuideError(
            "AI_SERVICE_TEMPORARILY_UNAVAILABLE",
            "We couldn't finish reading this label. Please try again in a moment.",
            status_code=503,
            retryable=True,
            technical_detail=error.technical_detail,
            stage=stage,
        ) from error
    except Exception as error:
        raise MediGuideError(
            "MEDICATION_LABEL_EXTRACTION_FAILED",
            "MediGuide could not read this label.",
            status_code=422,
            retryable=False,
            technical_detail=f"{type(error).__name__}: {error}",
            stage=stage,
        ) from error


def _extract_from_image(image_path: Path) -> tuple[list[MedicationField], str]:
    from src.shared.ollama_health import require_vision_ready

    try:
        require_vision_ready()
    except PermanentProcessingError as error:
        raise MediGuideError(
            "AI_SERVICE_UNAVAILABLE",
            error.message,
            status_code=503,
            retryable=False,
            technical_detail=error.technical_detail,
            stage="extracting",
        ) from error

    vision_path = prepare_vision_image(
        image_path,
        image_path.with_name(f"{image_path.stem}-vision.png"),
    )

    def _call() -> Any:
        client = _ollama_client()
        return client.chat(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": MED_EXTRACTION_PROMPT,
                "images": [str(vision_path)],
            }],
            options={"temperature": 0.0},
        )

    response = _call_with_classification(_call, stage="extracting")
    return _build_fields(_parse_json(response.message.content))


def _extract_from_text(label_text: str) -> tuple[list[MedicationField], str]:
    def _call() -> Any:
        client = _ollama_client()
        return client.chat(
            model=TEXT_MODEL,
            messages=[{
                "role": "user",
                "content": MED_EXTRACTION_PROMPT + "\n\n<label_text>\n" + label_text[:4000] + "\n</label_text>",
            }],
            options={"temperature": 0.0},
        )

    response = _call_with_classification(_call, stage="extracting")
    return _build_fields(_parse_json(response.message.content))


def _fields_from_parsed(parsed, *, ocr: bool) -> list[MedicationField]:
    fields: list[MedicationField] = []
    for key in MED_FIELD_ORDER:
        item = parsed.fields.get(key)
        if item is None or not item.value:
            fields.append(MedicationField(key=key, label=MED_FIELD_LABELS[key], confidence="not_found", extracted=""))
            continue
        uncertain = ocr and item.confidence < OCR_TRUSTED_CONFIDENCE
        ambiguous = any(flag in item.flags for flag in ("ambiguous_directions", "risky_abbreviation", "dose_range", "several_strengths"))
        fields.append(MedicationField(
            key=key,
            label=MED_FIELD_LABELS[key],
            value=item.value,
            confidence="needs_review" if (uncertain or ambiguous) else "clearly_visible",
            source_text=item.source_text,
            flags=list(item.flags),
            extracted=item.value,
            page=item.page,
        ))
    return fields


def _entries_from_lines(medication_id: str, lines: list[LabelLine], *, ocr: bool) -> list[MedicationEntry]:
    entries: list[MedicationEntry] = []
    for index, parsed in enumerate(parse_label(lines)):
        notes = list(parsed.review_notes)
        if ocr and any(line.confidence < OCR_TRUSTED_CONFIDENCE for line in lines):
            notes.append("low_confidence_text")
        entries.append(MedicationEntry(
            entry_id=f"{medication_id[:8]}-{index}",
            index=index,
            fields=_fields_from_parsed(parsed, ocr=ocr),
            review_notes=notes,
        ))
    return entries


def _ocr_label_lines(image: Image.Image, page: int) -> list[LabelLine]:
    from src.labs.table_reader import Word, group_rows

    result = ocr_image(image, page_number=page)
    rows = group_rows([Word(w.x0, w.y0, w.x1, w.y1, w.text, w.confidence) for w in result.words])
    return [LabelLine(row.text, page, min((w.confidence for w in row.words), default=0.0)) for row in rows if row.text.strip()]


def _read_label_file(folder: Path, preview: Path) -> tuple[list[LabelLine], str]:
    """The label's lines and how they were read: the PDF's own text first,
    then local OCR. Nothing is sent to an outside service."""
    with client_ocr(folder):
        return _read_label_lines(folder, preview)


def _read_label_lines(folder: Path, preview: Path) -> tuple[list[LabelLine], str]:
    pdf_path = folder / "upload.pdf"
    if pdf_path.exists():
        doc = pymupdf.open(pdf_path)
        try:
            lines = [LabelLine(text.strip(), index + 1) for index, page in enumerate(doc) if index < 5
                     for text in page.get_text("text").splitlines() if text.strip()]
            if lines:
                return lines, "text_layer"
            if ocr_available():
                ocr_lines: list[LabelLine] = []
                for index, page in enumerate(doc):
                    if index >= 3:
                        break
                    pix = page.get_pixmap(dpi=300, alpha=False)
                    ocr_lines.extend(_ocr_label_lines(Image.frombytes("RGB", (pix.width, pix.height), pix.samples), index + 1))
                return ocr_lines, "ocr"
        finally:
            doc.close()
        return [], ""
    if ocr_available():
        with Image.open(preview) as image:
            return _ocr_label_lines(image.convert("RGB"), 1), "ocr"
    return [], ""


def _legacy_entry(state: MedicationState) -> MedicationEntry:
    """Sessions saved before entries existed: their single set of fields."""
    by_key: dict[str, MedicationField] = {}
    for field in state.fields:
        key = LEGACY_KEYS.get(field.key, field.key)
        if key in MED_FIELD_LABELS:
            by_key[key] = field.model_copy(update={"key": key, "label": MED_FIELD_LABELS[key]})
    fields = [by_key.get(key) or MedicationField(key=key, label=MED_FIELD_LABELS[key], confidence="not_found", extracted="")
              for key in MED_FIELD_ORDER]
    return MedicationEntry(entry_id=f"{state.medication_id[:8]}-0", index=0, fields=fields,
                           decision="confirmed" if state.confirmed else "unverified")


def _ensure_entries(state: MedicationState) -> MedicationState:
    if not state.entries:
        state.entries = [_legacy_entry(state)]
    return state


def _value(fields: list[MedicationField], key: str) -> str:
    return next((field.value for field in fields if LEGACY_KEYS.get(field.key, field.key) == key), "")


_COMPARED = (("strength", "strength"), ("dose", "dose"), ("frequency", "frequency"),
             ("directions", "instructions"), ("route", "route"), ("dosage_form", "form"))


def _record_summary(record) -> dict[str, Any]:
    return {
        "record_id": record.id,
        "medication_name": record.medication_name,
        "strength": record.strength,
        "directions": record.instructions,
        "source": record.filename or ("typed label" if record.source == "typed" else "uploaded label"),
        "confirmed_at": utc_iso(record.confirmed_at),
    }


def _matches_for(fields: list[MedicationField], records: list, exclude_ids: set[str]) -> list[dict[str, Any]]:
    """Confirmed records naming the same medication (exact name match on the
    printed, brand or generic name; similar-looking names are not matched).
    "possible_duplicate" when the compared details agree, "conflict" when
    any printed detail differs. Neither record is treated as current."""
    keys = {name_key(_value(fields, k)) for k in ("medication_name", "generic_name", "brand_name")} - {""}
    if not keys:
        return []
    matches: list[dict[str, Any]] = []
    for record in records:
        if record.id in exclude_ids:
            continue
        record_keys = {name_key(record.medication_name), name_key(record.generic_name or ""), name_key(record.brand_name or "")} - {""}
        if not keys & record_keys:
            continue
        differences = []
        for key, column in _COMPARED:
            mine, theirs = _value(fields, key), getattr(record, column) or ""
            if compact(mine) and compact(theirs) and comparable(key, mine) != comparable(key, theirs):
                differences.append({"field": key, "label": MED_FIELD_LABELS[key], "this_label": mine, "existing_record": theirs})
        matches.append({**_record_summary(record), "kind": "conflict" if differences else "possible_duplicate", "differences": differences})
    return matches


def _refresh_matches(state: MedicationState, user: User) -> MedicationState:
    _ensure_entries(state)
    with session_scope() as session:
        records = list_medication_records(session, user.id)
        own_ids = {entry.record_id for entry in state.entries if entry.record_id}
        for entry in state.entries:
            if entry.decision == "unverified":
                entry.matches = _matches_for(entry.fields, records, own_ids)
    state.fields = state.entries[0].fields if state.entries else state.fields
    state.confirmed = any(entry.decision == "confirmed" for entry in state.entries)
    if state.entries and all(entry.decision != "unverified" for entry in state.entries):
        state.status = "confirmed" if state.confirmed else "rejected"
    return state


def _new_state(medication_id: str, *, source: Source, filename: str, preview_url: str,
               entries: list[MedicationEntry], label_text: str, text_source: str,
               fallback_fields: list[MedicationField] | None = None, other_text: str = "") -> MedicationState:
    if not entries and fallback_fields is not None:
        entries = [MedicationEntry(entry_id=f"{medication_id[:8]}-0", index=0, fields=fallback_fields,
                                   review_notes=["ai_read"])]
    return MedicationState(
        medication_id=medication_id,
        source=source,
        filename=filename,
        preview_url=preview_url,
        status="review_required",
        fields=entries[0].fields if entries else [],
        other_visible_text=other_text,
        confirmed=False,
        entries=entries,
        label_text=label_text,
        text_source=text_source,
    )


async def _ingest_pdf(file: UploadFile, folder: Path) -> Path:
    pdf_path = folder / "upload.pdf"
    max_bytes = MAX_MB * 1024 * 1024
    total = 0

    with pdf_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"PDF exceeds {MAX_MB} MB.")
            out.write(chunk)

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid PDF.") from e

    try:
        if doc.page_count < 1:
            raise HTTPException(status_code=400, detail="PDF has no pages.")
        preview = folder / "preview.png"
        doc[0].get_pixmap(dpi=RENDER_DPI, alpha=False).save(str(preview))
    finally:
        doc.close()

    return preview


async def _ingest_image(file: UploadFile, folder: Path) -> Path:
    # Keep the (already allowed) extension: the image validator checks the
    # format by it, so a bare "raw-upload" rejected every photo label.
    raw_path = folder / f"raw-upload{Path(file.filename or '').suffix.lower()}"
    max_bytes = MAX_IMAGE_MB * 1024 * 1024
    total = 0

    with raw_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"Image exceeds {MAX_IMAGE_MB} MB.")
            out.write(chunk)

    validation = validate_image_file(str(raw_path))

    if not validation.valid or not validation.path:
        raise HTTPException(status_code=422, detail=validation.error)

    preview = folder / "preview.png"

    with Image.open(validation.path) as image:
        image.convert("RGB").save(preview, format="PNG")

    raw_path.unlink(missing_ok=True)
    return preview


@router.post("/upload", response_model=MedicationState)
async def upload(
    file: UploadFile = File(...),
    client_ocr_pages: str | None = Form(None, alias="client_ocr"),
    user: User = Depends(require_user),
) -> MedicationState:
    _cleanup_expired_sessions()

    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix or 'unknown'}'. "
                f"Accepted: {', '.join(sorted(SUPPORTED_SUFFIXES))}."
            ),
        )

    medication_id = uuid.uuid4().hex
    folder = _claim_folder(medication_id, user)

    try:
        preview = await (_ingest_pdf(file, folder) if suffix == ".pdf" else _ingest_image(file, folder))
        save_client_ocr(folder, client_ocr_pages)
        lines, text_source = await run_in_threadpool(_read_label_file, folder, preview)
        entries = _entries_from_lines(medication_id, lines, ocr=text_source == "ocr")
        fallback_fields, other_text = None, ""
        if not entries:
            # Last resort: the local AI vision model. Every value it returns
            # is marked for review.
            fallback_fields, other_text = await run_in_threadpool(_extract_from_image, preview)
            text_source = "vision"
        state = _new_state(
            medication_id, source="upload", filename=file.filename or f"label{suffix}",
            preview_url=f"/api/medications/v2/{medication_id}/preview", entries=entries,
            label_text="\n".join(line.text for line in lines), text_source=text_source,
            fallback_fields=fallback_fields, other_text=other_text,
        )
        state = _refresh_matches(state, user)
        _save_state(state)
        return state

    except (HTTPException, MediGuideError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise MediGuideError(
            "MEDICATION_LABEL_UPLOAD_FAILED",
            "MediGuide could not store this upload.",
            status_code=500,
            retryable=False,
            technical_detail=f"{type(e).__name__}: {e}",
        ) from e


@router.post("/text", response_model=MedicationState)
async def upload_typed(request: TypedLabelRequest, user: User = Depends(require_user)) -> MedicationState:
    _cleanup_expired_sessions()

    medication_id = uuid.uuid4().hex
    folder = _claim_folder(medication_id, user)

    try:
        lines = lines_from_text(request.text)
        entries = _entries_from_lines(medication_id, lines, ocr=False)
        fallback_fields, other_text, text_source = None, "", "typed"
        if not entries:
            fallback_fields, other_text = await run_in_threadpool(_extract_from_text, request.text)
            text_source = "typed_ai"
        state = _new_state(
            medication_id, source="typed", filename="", preview_url="", entries=entries,
            label_text=request.text.strip(), text_source=text_source,
            fallback_fields=fallback_fields, other_text=other_text,
        )
        state = _refresh_matches(state, user)
        _save_state(state)
        return state
    except (HTTPException, MediGuideError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise MediGuideError(
            "MEDICATION_LABEL_UPLOAD_FAILED",
            "MediGuide could not process that label text.",
            status_code=500,
            retryable=False,
            technical_detail=f"{type(e).__name__}: {e}",
        ) from e


@router.get("/records")
async def list_records_endpoint(user: User = Depends(require_user)) -> dict[str, Any]:
    """Every confirmed medication, each with the other records that name
    the same medication. MediGuide never decides which record is current;
    differences are shown for the user to check with a pharmacist."""
    with session_scope() as session:
        records = list_medication_records(session, user.id)
        items = []
        for record in records:
            item = serialize_medication_record(record)
            fields = [MedicationField(key=key, label=MED_FIELD_LABELS[key], value=str(item.get(key) or ""))
                      for key in MED_FIELD_ORDER]
            item["matches"] = _matches_for(fields, records, {record.id})
            items.append(item)
        return {"records": items, "count": len(items)}


@router.get("/{medication_id}", response_model=MedicationState)
async def get_medication(medication_id: str, user: User = Depends(require_user)) -> MedicationState:
    return _refresh_matches(_load_owned_state(medication_id, user), user)


@router.get("/{medication_id}/preview")
async def preview(medication_id: str, user: User = Depends(require_user)):
    state = _load_owned_state(medication_id, user)
    if state.source != "upload":
        raise HTTPException(status_code=404, detail="This entry has no image preview.")
    path = _folder(medication_id) / "preview.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found.")
    return FileResponse(path, media_type="image/png")


def _record_id(state: MedicationState, entry: MedicationEntry) -> str:
    return state.medication_id if entry.index == 0 else f"{state.medication_id}-{entry.index}"


def _confirm_entry(state: MedicationState, entry: MedicationEntry, submitted: list[MedicationField],
                   acknowledged: list[str], user: User) -> MedicationState:
    if entry.decision == "confirmed":
        raise MediGuideError(
            "MEDICATION_ALREADY_CONFIRMED",
            "This medication was already confirmed. Its saved details are kept as they were.",
            status_code=409,
        )
    by_key = {LEGACY_KEYS.get(field.key, field.key): field for field in submitted}
    name = by_key.get("medication_name")
    if not name or not name.value.strip():
        raise HTTPException(status_code=400, detail="Medication name is required before confirming.")
    pending = [m["record_id"] for m in entry.matches if m["record_id"] not in set(acknowledged)]
    if pending:
        raise MediGuideError(
            "MATCH_REVIEW_REQUIRED",
            "You already have a confirmed record for this medication. Compare the two before confirming; nothing will be merged.",
            status_code=409,
        )

    # Values the reviewer confirmed; what was read stays in `extracted`.
    original = {field.key: field for field in entry.fields}
    confirmed_fields: list[MedicationField] = []
    for key in MED_FIELD_ORDER:
        before = original.get(key) or MedicationField(key=key, label=MED_FIELD_LABELS[key], confidence="not_found", extracted="")
        after = by_key.get(key)
        value = after.value.strip() if after is not None else before.value
        confirmed_fields.append(before.model_copy(update={
            "value": value,
            "user_edited": value != (before.extracted if before.extracted is not None else before.value),
        }))
    values = {field.key: field.value for field in confirmed_fields}
    record_id = _record_id(state, entry)
    flags = sorted({*entry.review_notes, *(flag for field in confirmed_fields for flag in field.flags)})
    try:
        with session_scope() as session:
            create_medication_record(
                session,
                medication_id=record_id,
                medication_name=values["medication_name"],
                strength=values["strength"],
                form=values["dosage_form"],
                instructions=values["directions"],
                quantity=values["quantity"],
                prescriber_or_pharmacy=" · ".join(v for v in (values["prescriber"], values["pharmacy"]) if v),
                source=state.source,
                filename=state.filename,
                other_visible_text=state.other_visible_text,
                owner_id=user.id,
                details={
                    "brand_name": values["brand_name"], "generic_name": values["generic_name"],
                    "route": values["route"], "dose": values["dose"], "frequency": values["frequency"],
                    "refills": values["refills"], "prescriber": values["prescriber"], "pharmacy": values["pharmacy"],
                    "prescription_date": values["prescription_date"],
                    "source_session_id": state.medication_id, "entry_index": entry.index,
                    "source_page": original.get("medication_name").page if original.get("medication_name") else None,
                    "text_source": state.text_source,
                    "extracted_snapshot": {f.key: f.extracted for f in entry.fields if f.extracted},
                    "review_flags": flags,
                    "acknowledged_records": list(acknowledged),
                },
            )
    except (HTTPException, MediGuideError):
        raise
    except Exception as error:
        logger.warning(
            "medication_persist_failed",
            extra={"medication_id": state.medication_id, "error_type": type(error).__name__},
        )
        raise MediGuideError(
            "CONFIRMATION_NOT_SAVED",
            "This medication wasn't saved, so nothing changed. Please try confirming again.",
            status_code=503,
            retryable=True,
            technical_detail=f"{type(error).__name__}: {error}",
        ) from error

    entry.fields = confirmed_fields
    entry.decision = "confirmed"
    entry.record_id = record_id
    entry.matches = []
    state = _refresh_matches(state, user)
    _save_state(state)
    return state


def _owned_entry(medication_id: str, entry_id: str, user: User) -> tuple[MedicationState, MedicationEntry]:
    state = _refresh_matches(_load_owned_state(medication_id, user), user)
    entry = next((item for item in state.entries if item.entry_id == entry_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="That medication isn't in this upload.")
    return state, entry


@router.post("/{medication_id}/entries/{entry_id}/confirm", response_model=MedicationState)
async def confirm_entry(
    medication_id: str, entry_id: str, request: EntryConfirmRequest, user: User = Depends(require_user)
) -> MedicationState:
    """Confirm one medication from the upload. Nothing is added to the
    confirmed list without this explicit step."""
    state, entry = _owned_entry(medication_id, entry_id, user)
    if not request.reviewed:
        raise HTTPException(status_code=400, detail="Review the medication details first.")
    return _confirm_entry(state, entry, request.fields, request.acknowledged_record_ids, user)


@router.post("/{medication_id}/entries/{entry_id}/reject", response_model=MedicationState)
async def reject_entry(medication_id: str, entry_id: str, user: User = Depends(require_user)) -> MedicationState:
    state, entry = _owned_entry(medication_id, entry_id, user)
    if entry.decision == "confirmed":
        raise HTTPException(status_code=409, detail="This medication is already confirmed.")
    entry.decision = "rejected"
    state = _refresh_matches(state, user)
    _save_state(state)
    return state


@router.post("/{medication_id}/entries/{entry_id}/restore", response_model=MedicationState)
async def restore_entry(medication_id: str, entry_id: str, user: User = Depends(require_user)) -> MedicationState:
    state, entry = _owned_entry(medication_id, entry_id, user)
    if entry.decision != "rejected":
        raise HTTPException(status_code=409, detail="Only a rejected medication can be restored.")
    entry.decision = "unverified"
    state.status = "review_required"
    state = _refresh_matches(state, user)
    _save_state(state)
    return state


@router.post("/{medication_id}/confirm")
async def confirm(medication_id: str, request: ConfirmRequest, user: User = Depends(require_user)):
    """Confirms the first (or only) medication in the upload. Kept for
    single-label clients; /entries/{entry_id}/confirm handles lists."""
    state = _refresh_matches(_load_owned_state(medication_id, user), user)
    if not request.reviewed_name_strength_instructions:
        raise HTTPException(
            status_code=400,
            detail="Review the medication name, strength, and instructions first.",
        )
    if not request.fields:
        raise HTTPException(status_code=400, detail="No reviewed fields supplied.")
    entry = state.entries[0]
    state = _confirm_entry(state, entry, request.fields, request.acknowledged_record_ids, user)
    return {"medication_id": medication_id, "confirmed": True, "fields": state.entries[0].fields, "state": state.model_dump()}


@router.get("/{medication_id}/record")
async def get_medication_record_endpoint(medication_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    """Read-only, persisted view of a confirmed medication — powers the
    Unified Health Timeline's "View medication" drawer independently of
    the session-based upload/review flow (which expires)."""
    with session_scope() as session:
        record = get_medication_record(session, medication_id, user.id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="No confirmed medication record found for this id.",
            )
        return serialize_medication_record(record)


def _confirmed_context(fields: list[MedicationField]) -> str:
    by_key = {field.key: field.value for field in fields if field.value}
    lines = [f"{MED_FIELD_LABELS[key]}: {value}" for key, value in by_key.items() if key in MED_FIELD_LABELS]
    return "\n".join(lines)


@router.post("/{medication_id}/info", response_model=MedicationInfoResponse)
async def info(
    medication_id: str, request: InfoRequest, user: User = Depends(require_user)
) -> MedicationInfoResponse:
    state = _ensure_entries(_load_owned_state(medication_id, user))
    confirmed_entries = [entry for entry in state.entries if entry.decision == "confirmed"]
    chosen = next((entry for entry in confirmed_entries if entry.entry_id == request.entry_id), None) or (
        confirmed_entries[0] if confirmed_entries else None
    )
    if chosen is None:
        raise HTTPException(
            status_code=409,
            detail="Human review and confirmation are required before educational information is provided.",
        )

    extra_question = request.question.strip()

    if extra_question:
        emergency = check_for_emergency(extra_question)
        if emergency.is_emergency:
            return MedicationInfoResponse(
                medication_id=medication_id,
                answer_markdown=emergency.message or "Call emergency services immediately.",
                sources=[],
                limitations=["This response did not use the label or approved sources."],
            )

    by_key = {field.key: field.value for field in chosen.fields}
    name = by_key.get("medication_name", "")
    strength = by_key.get("strength", "")
    context = _confirmed_context(chosen.fields)

    query = f"{name} {strength} medication purpose precautions patient education".strip()
    evidence = retrieve_approved_evidence(query, top_k=5)

    if not evidence:
        return MedicationInfoResponse(
            medication_id=medication_id,
            answer_markdown=(
                "### Limited trusted information available\n\n"
                f"MediGuide could not find an approved educational source specific to "
                f"\"{name or 'this medication'}\". The label details you confirmed are shown "
                "below. Ask a pharmacist or clinician for medication-specific education.\n\n"
                + context
            ),
            sources=[],
            limitations=[
                "No sufficiently relevant approved knowledge source was retrieved for this medication.",
                "This is not personalized dosing guidance.",
                "Confirm all details with a licensed pharmacist or clinician.",
            ],
        )

    source_text = []
    sources = []
    for idx, item in enumerate(evidence, 1):
        sources.append(EvidenceSource(
            citation_number=idx,
            title=item.get("title", "Untitled source"),
            publisher=item.get("publisher", "Unknown publisher"),
            source_url=item.get("source_url", ""),
            passage=item.get("passage", ""),
        ))
        source_text.append(f"[{idx}] {item.get('title','')} — {item.get('passage','')}")

    prompt = f"""
LABEL DETAILS CONFIRMED BY THE USER
{context}

USER QUESTION (optional)
{extra_question or "Provide general educational information about this medication."}

APPROVED EVIDENCE
{chr(10).join(source_text)}

Write plain-language educational information using only the approved evidence above
and the confirmed label details above. Use [1], [2], etc. for claims drawn from the
approved evidence. Structure the answer as three sections:
- Purpose: what this type of medicine is generally used for
- Common precautions: general warnings and things to watch for
- Questions to ask your pharmacist or clinician

STRICT RULES:
- Do not state or imply a personalized dose, a dosing schedule change, or an
  individualized treatment decision.
- Do not tell the user to start, stop, skip, or adjust a dose.
- If the user's question asks about dosing, answer only by directing them to their
  pharmacist or prescriber.
- Do not invent citations or medication facts not present in the approved evidence.
"""

    try:
        client = _ollama_client()
        response = client.chat(
            model=TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Use only the confirmed label details and supplied approved evidence. "
                        "Never provide personalized dosing instructions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
    except Exception:
        # No text model on this deployment: show the confirmed label and the
        # approved passages as-is rather than failing.
        logger.exception("medication explanation model unavailable")
        return MedicationInfoResponse(
            medication_id=medication_id,
            answer_markdown=(
                "### Confirmed label details\n\n"
                "The explanation model is unavailable on this deployment, so MediGuide is "
                "showing the label details you confirmed and the approved sources below, "
                "quoted as-is.\n\n"
                + context
            ),
            sources=sources,
            limitations=[
                "Educational explanation model is unavailable on this deployment.",
                "This is not personalized dosing guidance.",
                "Confirm all details with a licensed pharmacist or clinician.",
            ],
        )

    return MedicationInfoResponse(
        medication_id=medication_id,
        answer_markdown=response.message.content.strip(),
        sources=sources,
        limitations=[
            "Automated label extraction can be incorrect — confirm the printed text yourself.",
            "This is general education, not a personalized dosing recommendation.",
            "Contact your prescribing clinician or pharmacist with medication-specific questions.",
        ],
    )
