from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    serialize_medication_record,
)
from src.auth.dependencies import not_found, require_user
from src.database.models import User
from src.database.session import session_scope
from src.document_intelligence import EvidenceSource, retrieve_approved_evidence
from src.image_validator import prepare_vision_image, validate_image_file
from src.observability.logging import get_logger
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

Confidence = Literal["clearly_visible", "needs_review", "could_not_read"]
Source = Literal["upload", "typed"]

MED_FIELD_LABELS: dict[str, str] = {
    "medication_name": "Medication name",
    "strength": "Strength",
    "form": "Form",
    "instructions": "Directions for use",
    "quantity": "Quantity / refills",
    "prescriber_or_pharmacy": "Prescriber or pharmacy",
}
MED_FIELD_ORDER = list(MED_FIELD_LABELS)


class MedicationField(BaseModel):
    key: str
    label: str
    value: str = ""
    confidence: Confidence = "needs_review"
    source_text: str = ""
    user_edited: bool = False


class MedicationState(BaseModel):
    medication_id: str
    source: Source
    filename: str = ""
    preview_url: str = ""
    status: str
    fields: list[MedicationField]
    other_visible_text: str = ""
    confirmed: bool = False


class TypedLabelRequest(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


class ConfirmRequest(BaseModel):
    fields: list[MedicationField]
    reviewed_name_strength_instructions: bool


class InfoRequest(BaseModel):
    question: str = ""


class MedicationInfoResponse(BaseModel):
    medication_id: str
    answer_markdown: str
    sources: list[EvidenceSource]
    limitations: list[str]


def _folder(medication_id: str) -> Path:
    return TEMP_DIR / medication_id


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
    fields: list[MedicationField] = []

    for key in MED_FIELD_ORDER:
        item = data.get(key) or {}
        if not isinstance(item, dict):
            item = {}

        confidence = item.get("confidence", "needs_review")
        if confidence not in {"clearly_visible", "needs_review", "could_not_read"}:
            confidence = "needs_review"

        fields.append(MedicationField(
            key=key,
            label=MED_FIELD_LABELS[key],
            value=str(item.get("value", "")).strip(),
            confidence=confidence,
            source_text=str(item.get("source_text", "")).strip(),
        ))

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
    raw_path = folder / "raw-upload"
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
async def upload(file: UploadFile = File(...), user: User = Depends(require_user)) -> MedicationState:
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
        fields, other_text = await run_in_threadpool(_extract_from_image, preview)

        state = MedicationState(
            medication_id=medication_id,
            source="upload",
            filename=file.filename or f"label{suffix}",
            preview_url=f"/api/medications/v2/{medication_id}/preview",
            status="review_required",
            fields=fields,
            other_visible_text=other_text,
            confirmed=False,
        )
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
        fields, other_text = await run_in_threadpool(_extract_from_text, request.text)
        state = MedicationState(
            medication_id=medication_id,
            source="typed",
            status="review_required",
            fields=fields,
            other_visible_text=other_text,
            confirmed=False,
        )
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


@router.get("/{medication_id}", response_model=MedicationState)
async def get_medication(medication_id: str, user: User = Depends(require_user)) -> MedicationState:
    return _load_owned_state(medication_id, user)


@router.get("/{medication_id}/preview")
async def preview(medication_id: str, user: User = Depends(require_user)):
    state = _load_owned_state(medication_id, user)
    if state.source != "upload":
        raise HTTPException(status_code=404, detail="This entry has no image preview.")
    path = _folder(medication_id) / "preview.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found.")
    return FileResponse(path, media_type="image/png")


@router.post("/{medication_id}/confirm")
async def confirm(medication_id: str, request: ConfirmRequest, user: User = Depends(require_user)):
    state = _load_owned_state(medication_id, user)
    if state.confirmed:
        raise MediGuideError(
            "MEDICATION_ALREADY_CONFIRMED",
            "This medication was already confirmed. Its saved details are kept as they were.",
            status_code=409,
        )

    if not request.reviewed_name_strength_instructions:
        raise HTTPException(
            status_code=400,
            detail="Review the medication name, strength, and instructions first.",
        )
    if not request.fields:
        raise HTTPException(status_code=400, detail="No reviewed fields supplied.")

    by_key = {field.key: field for field in request.fields}
    name_value = by_key.get("medication_name")

    if not name_value or not name_value.value.strip():
        raise HTTPException(
            status_code=400,
            detail="Medication name is required before confirming.",
        )

    # The database row comes first: it is what lets a confirmed medication
    # appear in the Unified Health Timeline after the session's temp files
    # expire. If it can't be written, the session stays unconfirmed so the
    # user can retry, instead of showing a confirmation that went nowhere.
    try:
        values = {key: (by_key[key].value if key in by_key else "") for key in MED_FIELD_ORDER}
        with session_scope() as session:
            create_medication_record(
                session,
                medication_id=medication_id,
                medication_name=values["medication_name"],
                strength=values["strength"],
                form=values["form"],
                instructions=values["instructions"],
                quantity=values["quantity"],
                prescriber_or_pharmacy=values["prescriber_or_pharmacy"],
                source=state.source,
                filename=state.filename,
                other_visible_text=state.other_visible_text,
                owner_id=user.id,
            )
    except Exception as error:
        logger.warning(
            "medication_persist_failed",
            extra={"medication_id": medication_id, "error_type": type(error).__name__},
        )
        raise MediGuideError(
            "CONFIRMATION_NOT_SAVED",
            "This medication wasn't saved, so nothing changed. Please try confirming again.",
            status_code=503,
            retryable=True,
            technical_detail=f"{type(error).__name__}: {error}",
        ) from error

    state.fields = [field.model_copy(update={"user_edited": True}) for field in request.fields]
    state.confirmed = True
    state.status = "confirmed"
    _save_state(state)

    return {"medication_id": medication_id, "confirmed": True, "fields": state.fields}


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
    state = _load_owned_state(medication_id, user)

    if not state.confirmed:
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

    by_key = {field.key: field.value for field in state.fields}
    name = by_key.get("medication_name", "")
    strength = by_key.get("strength", "")
    context = _confirmed_context(state.fields)

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
