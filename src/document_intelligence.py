from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from collections.abc import Callable
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
    OLLAMA_VISION_TIMEOUT_SECONDS,
    PROCESSING_RETRY_ATTEMPTS,
    PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS,
    RAG_MAX_PASSAGE_WORDS,
    VISION_MODEL_NAME,
)
from src.auth.dependencies import not_found, require_user
from src.database.models import User
from src.database.repository import (
    create_uploaded_document,
    document_exists,
    get_owned_document,
    owned_document_ids,
)
from src.database.session import session_scope
from src.image_validator import prepare_vision_image, validate_image_file
from src.labs.service import create_observations_from_document
from src.observability.logging import get_logger
from src.safety import check_for_emergency
from src.sample_fixtures import generate_sample_lab_report
from src.shared.errors import MediGuideError
from src.shared.job_runner import run_extraction_job
from src.shared.resilience import (
    PermanentProcessingError,
    TransientProcessingError,
    call_with_retry,
)

logger = get_logger(__name__)


router = APIRouter(prefix="/api/documents/v2", tags=["Document Intelligence V2"])

TEMP_DIR = Path(
    os.getenv("DOC_INTEL_TEMP_DIR", str(BASE_DIR / "outputs" / "document_intelligence"))
)
VISION_MODEL = VISION_MODEL_NAME
TEXT_MODEL = MODEL_NAME
MAX_MB = int(os.getenv("DOC_INTEL_MAX_MB", "20"))
MAX_PAGES = int(os.getenv("DOC_INTEL_MAX_PAGES", "25"))
RENDER_DPI = int(os.getenv("DOC_INTEL_RENDER_DPI", "140"))
RETENTION_MINUTES = int(os.getenv("DOC_INTEL_RETENTION_MINUTES", "120"))

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

Confidence = Literal["clearly_visible", "needs_review", "could_not_read"]
Status = Literal[
    "in_listed_range",
    "outside_listed_range",
    "flagged_high_on_report",
    "flagged_low_on_report",
    "not_applicable",
    "unknown",
]
ExtractionMethod = Literal["native_text", "vision_ocr", ""]


class ExtractedField(BaseModel):
    field_id: str
    label: str
    value: str = ""
    unit: str = ""
    reference_range: str = ""
    status: Status = "unknown"
    confidence: Confidence = "needs_review"
    page_number: int = Field(ge=1)
    source_text: str = ""
    extraction_method: ExtractionMethod = ""
    user_edited: bool = False


class PageInfo(BaseModel):
    page_number: int
    preview_url: str
    text_available: bool
    extracted_field_count: int


class DocumentState(BaseModel):
    document_id: str
    filename: str
    page_count: int
    status: str
    pages: list[PageInfo]
    fields: list[ExtractedField]
    confirmed: bool = False
    content_type: str = ""
    file_size: int = 0
    # Granular processing stage (validating/reading/extracting/saving/
    # waiting_for_service) — distinct from `status` above, which stays the
    # coarse value the existing UI already keys off of. Mirrored here from
    # ProcessingJob (see src/shared/job_runner.py's on_stage hook) purely so
    # the polling /status route — which reads this JSON state, not the DB —
    # can show live retry progress.
    stage: str = ""
    retry_attempt: int = 0
    retry_max: int = 0
    safe_error_message: str = ""


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    content_type: str = ""
    file_size: int
    status: str = "uploaded"


class DocumentStatusResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int = 0
    field_count: int = 0
    stage: str = ""
    retry_attempt: int = 0
    retry_max: int = 0
    safe_error_message: str = ""


class ConfirmRequest(BaseModel):
    # Only field_id plus the reviewable text (label/value/unit/
    # reference_range) is taken from these — page, source text, confidence
    # and extraction method always come from the server's own extraction,
    # so a confirm can't rewrite where a value came from.
    fields: list[ExtractedField]
    reviewed_names_values_units_dates: bool
    # Fields the reviewer rejected; they are left out of the confirmed
    # record and never become lab observations.
    excluded_field_ids: list[str] = Field(default_factory=list)


class ExplainRequest(BaseModel):
    question: str = (
        "Explain the confirmed information in plain language and suggest "
        "questions for a qualified healthcare professional."
    )


class EvidenceSource(BaseModel):
    citation_number: int
    title: str
    publisher: str
    source_url: str = ""
    passage: str = ""


class ExplainResponse(BaseModel):
    document_id: str
    answer_markdown: str
    document_pages_cited: list[int]
    sources: list[EvidenceSource]
    limitations: list[str]


def _folder(document_id: str) -> Path:
    return TEMP_DIR / document_id


def _state_path(document_id: str) -> Path:
    return _folder(document_id) / "state.json"


def _save_state(state: DocumentState) -> None:
    folder = _folder(state.document_id)
    folder.mkdir(parents=True, exist_ok=True)
    _state_path(state.document_id).write_text(
        json.dumps(state.model_dump(), indent=2),
        encoding="utf-8",
    )


def _load_state(document_id: str) -> DocumentState:
    path = _state_path(document_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document session not found.")
    return DocumentState.model_validate_json(path.read_text(encoding="utf-8"))


def _load_owned_state(document_id: str, user: User) -> DocumentState:
    """Loads a review session only for its owner. Anyone else gets the same
    404 as a document that doesn't exist."""
    with session_scope() as session:
        owned = get_owned_document(session, document_id, user.id) is not None
    if not owned:
        raise not_found("Document")
    return _load_state(document_id)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _field_id(page: int, index: int, label: str) -> str:
    digest = hashlib.sha256(f"{page}|{index}|{label}".encode()).hexdigest()[:10]
    return f"p{page}-{digest}"


def _cleanup_expired_sessions() -> None:
    """Best-effort sweep of abandoned upload folders.

    Only folders with no Document row are removed: those are uploads whose
    database write never happened, so nobody can reach them. Every owned
    document keeps its original file and page previews until the owner
    deletes it — including failed ones, so "Retry processing" still has
    the upload, and confirmed ones, so "View source" keeps working.
    """
    if not TEMP_DIR.exists():
        return

    cutoff = time.time() - (RETENTION_MINUTES * 60)

    try:
        with session_scope() as session:
            candidates = [
                folder
                for folder in TEMP_DIR.iterdir()
                if folder.is_dir() and folder.stat().st_mtime < cutoff
            ]
            orphans = [folder for folder in candidates if not document_exists(session, folder.name)]
    except Exception as error:  # noqa: BLE001 — if the DB is unreachable, delete nothing
        logger.warning("session_sweep_skipped", extra={"error_type": type(error).__name__})
        return

    for folder in orphans:
        shutil.rmtree(folder, ignore_errors=True)


_LEADING_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_RANGE_SEARCH_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)")
_COMPARISON_SEARCH_PATTERN = re.compile(r"(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)")


def _recompute_status(
    value: str,
    reference_range: str,
    model_status: Status,
) -> Status:
    """Deterministically overrides the model's in/out-of-range call when
    both the value and the printed reference range parse cleanly as
    numbers, so "based only on the report's printed reference range" is
    a mechanical check for the common numeric case rather than an LLM
    guess. Qualitative ranges (e.g. "Negative", "Normal") have nothing
    to parse, so they fall back to the model's already-constrained
    judgment (the extraction prompt forbids claiming in/out of range
    unless a printed range is visible).
    """
    if not value or not reference_range:
        return model_status

    number_match = _LEADING_NUMBER_PATTERN.search(value)

    if not number_match:
        return model_status

    number = float(number_match.group())
    normalized = (
        reference_range.strip()
        .replace("–", "-")
        .replace("—", "-")
        .replace("≤", "<=")
        .replace("≥", ">=")
    )

    range_match = _RANGE_SEARCH_PATTERN.search(normalized)

    if range_match:
        low, high = sorted(
            (float(range_match.group(1)), float(range_match.group(2)))
        )
        if number < low:
            return "flagged_low_on_report"
        if number > high:
            return "flagged_high_on_report"
        return "in_listed_range"

    comparison_match = _COMPARISON_SEARCH_PATTERN.search(normalized)

    if comparison_match:
        operator, bound_text = comparison_match.groups()
        bound = float(bound_text)
        in_range = {
            "<": number < bound,
            "<=": number <= bound,
            ">": number > bound,
            ">=": number >= bound,
        }[operator]
        if in_range:
            return "in_listed_range"
        if operator in {"<", "<="}:
            return "flagged_high_on_report"
        return "flagged_low_on_report"

    return model_status


EXTRACTION_PROMPT = """
You are MediGuide's medical DOCUMENT extraction engine.
Do not diagnose. Extract only visible information.

Return JSON only:
{
  "fields": [
    {
      "label": "",
      "value": "",
      "unit": "",
      "reference_range": "",
      "status": "unknown",
      "confidence": "clearly_visible",
      "source_text": ""
    }
  ]
}

Rules:
- Preserve numbers, decimals, dates, names, and units exactly.
- Never invent unreadable content.
- Use needs_review for partial/uncertain content.
- Use could_not_read when a value cannot be read.
- Only use in_listed_range/outside_listed_range when the printed document
  itself contains a visible reference range that supports that comparison.
- Otherwise status=unknown.
"""


def _extract_page_fields(
    image_path: Path,
    page_number: int,
    native_text: str,
    set_stage: Callable[[str], None] = lambda stage: None,
) -> list[ExtractedField]:
    from src.shared.ollama_health import require_vision_ready

    require_vision_ready()
    from ollama import Client

    vision_path = prepare_vision_image(
        image_path,
        image_path.with_name(f"{image_path.stem}-vision.png"),
    )

    def _call() -> Any:
        client = Client(host=OLLAMA_HOST, timeout=OLLAMA_VISION_TIMEOUT_SECONDS)
        return client.chat(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": EXTRACTION_PROMPT + "\n\n<native_document_text>\n"
                           + native_text[:12000] + "\n</native_document_text>",
                "images": [str(vision_path)],
            }],
            options={"temperature": 0.0},
        )

    def _on_retry(attempt: int, attempts: int, delay: float) -> None:
        set_stage("waiting_for_service", retry_attempt=attempt, retry_max=attempts)

    try:
        response = call_with_retry(
            _call,
            attempts=PROCESSING_RETRY_ATTEMPTS,
            backoff_schedule=PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS,
            on_retry=_on_retry,
        )
    except TransientProcessingError:
        raise
    except Exception as error:
        raise PermanentProcessingError(
            f"Vision OCR could not read this page ({type(error).__name__}).",
            technical_detail=f"{type(error).__name__}: {error}",
        ) from error

    data = _parse_json(response.message.content)
    result: list[ExtractedField] = []
    for i, item in enumerate(data.get("fields", [])):
        label = str(item.get("label", "")).strip() or "Unlabeled field"
        confidence = item.get("confidence", "needs_review")
        if confidence not in {"clearly_visible", "needs_review", "could_not_read"}:
            confidence = "needs_review"
        status = item.get("status", "unknown")
        if status not in {
            "in_listed_range",
            "outside_listed_range",
            "flagged_high_on_report",
            "flagged_low_on_report",
            "not_applicable",
            "unknown",
        }:
            status = "unknown"
        value = str(item.get("value", "")).strip()
        reference_range = str(item.get("reference_range", "")).strip()
        status = _recompute_status(value, reference_range, status)
        result.append(ExtractedField(
            field_id=_field_id(page_number, i, label),
            label=label,
            value=value,
            unit=str(item.get("unit", "")).strip(),
            reference_range=reference_range,
            status=status,
            confidence=confidence,
            page_number=page_number,
            source_text=str(item.get("source_text", "")).strip(),
            extraction_method="vision_ocr",
        ))
    return result


def retrieve_approved_evidence(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Pulls real approved sources from the same RAG pipeline the chat
    endpoint uses (`src.retriever`, `src.citations`), so document
    explanations cite genuine local sources instead of an empty stub.
    Returns [] when the approved knowledge base does not support the
    query, or if retrieval itself fails (e.g. Ollama/Chroma unreachable)
    — callers already treat an empty list as "no supporting evidence".
    """
    try:
        from src.citations import build_citation_sources
        from src.retriever import diversify_results, retrieve_chunks

        chunks = diversify_results(retrieve_chunks(query, top_k=top_k))
    except Exception:
        return []

    if not chunks:
        return []

    sources = build_citation_sources(chunks)
    chunk_by_source_id = {
        str(chunk.metadata.get("source_id", chunk.chunk_id)): chunk
        for chunk in reversed(chunks)
    }

    evidence: list[dict[str, Any]] = []

    for source in sources:
        chunk = chunk_by_source_id.get(source.source_id)
        passage = ""

        if chunk is not None:
            words = chunk.text.split()
            passage = " ".join(words[:RAG_MAX_PASSAGE_WORDS])
            if len(words) > RAG_MAX_PASSAGE_WORDS:
                passage += " …"

        evidence.append(
            {
                "title": source.title,
                "publisher": source.publisher,
                "source_url": source.source_url,
                "passage": passage,
            }
        )

    return evidence


def _confirmed_context(fields: list[ExtractedField]) -> str:
    lines = []
    for f in fields:
        unit = f" {f.unit}" if f.unit else ""
        rr = f"; printed reference range: {f.reference_range}" if f.reference_range else ""
        lines.append(f"[D{f.page_number}] {f.label}: {f.value}{unit}{rr}")
    return "\n".join(lines)


async def _save_upload_file(
    file: UploadFile,
    folder: Path,
    pages_dir: Path,
    suffix: str,
) -> tuple[Path, int]:
    """Persist the raw upload to disk without extraction."""
    max_bytes = (MAX_MB if suffix == ".pdf" else MAX_IMAGE_MB) * 1024 * 1024
    total = 0

    if suffix == ".pdf":
        target = folder / "document.pdf"
    else:
        pages_dir.mkdir(parents=True, exist_ok=True)
        target = pages_dir / f"upload{suffix}"

    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                limit = MAX_MB if suffix == ".pdf" else MAX_IMAGE_MB
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds {limit} MB.",
                )
            out.write(chunk)

    if suffix == ".pdf":
        header = target.read_bytes()[:5]
        if not header.startswith(b"%PDF"):
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File is not a valid PDF.")
        try:
            doc = pymupdf.open(target)
            page_count = doc.page_count
            doc.close()
        except Exception as error:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Invalid or unreadable PDF.") from error
        if page_count < 1:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="PDF has no pages.")

    return target, total


def _extract_native_text_fields(text: str, page_number: int) -> list[ExtractedField]:
    """Parse structured medical lab fields directly from digital PDF text.

    Fast, deterministic, and does not require Ollama/GPU when clean text is present.
    """
    if not text:
        return []

    results: list[ExtractedField] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    index = 0
    for line in lines:
        if re.search(r"^(?:sample|page\s*\d|report\s*date|collection\s*date|patient|doctor|physician|date\b|test\s*name|component\b)", line, re.I):
            continue

        label: str = ""
        value: str = ""
        unit: str = ""
        ref_range: str = ""

        # Pattern 1: Label Value Unit Ref Range (e.g. "Hemoglobin 13.2 g/dL Ref 12.0-15.5")
        m1 = re.match(
            r"^([A-Za-z0-9\s/_\-\(\)\.]+?)\s+([<>]?\s*\d+(?:\.\d+)?)\s*([a-zA-Z0-9^/%µ\-_/]*)\s*(?:(?:Ref|Reference|Range|Ref\s*Range|Normal|Limits)[:\s]*|[\[\(])\s*([<>]?\s*\d+(?:\.\d+)?\s*(?:[-–to]+\s*\d+(?:\.\d+)?)?)[\]\)]?",
            line,
            re.I,
        )
        if m1:
            label, value, unit, ref_range = m1.groups()
        else:
            # Pattern 2: Label : Value Unit (Range) (e.g. "Glucose: 98 mg/dL (70-99)")
            m2 = re.match(
                r"^([A-Za-z0-9\s/_\-\(\)\.]+?)\s*[:=]\s*([<>]?\s*\d+(?:\.\d+)?)\s*([a-zA-Z0-9^/%µ\-_/]*)\s*(?:[\[\(]?([<>]?\s*\d+(?:\.\d+)?\s*(?:[-–to]+\s*\d+(?:\.\d+)?)?)[\]\)]?)?",
                line,
                re.I,
            )
            if m2:
                label, value, unit, ref_range = m2.groups()
            else:
                # Pattern 3: Simple Label Value Unit (e.g. "WBC 6.4 10^3/uL")
                m3 = re.match(
                    r"^([A-Za-z0-9\s/_\-\(\)\.]+?)\s+([<>]?\s*\d+(?:\.\d+)?)\s*([a-zA-Z0-9^/%µ\-_/]+)$",
                    line,
                )
                if m3:
                    label, value, unit = m3.groups()

        if label and value:
            label_clean = label.strip()
            if len(label_clean) < 2 or label_clean.lower() in {"page", "report", "date", "dr", "md", "total"}:
                continue
            val_clean = value.strip()
            unit_clean = (unit or "").strip()
            ref_clean = (ref_range or "").strip()
            status = _recompute_status(val_clean, ref_clean, "unknown")
            field_id = _field_id(page_number, index, label_clean)
            results.append(
                ExtractedField(
                    field_id=field_id,
                    label=label_clean,
                    value=val_clean,
                    unit=unit_clean,
                    reference_range=ref_clean,
                    status=status,
                    confidence="clearly_visible",
                    page_number=page_number,
                    source_text=line,
                    extraction_method="native_text",
                    user_edited=False,
                )
            )
            index += 1

    date_match = re.search(
        r"(?:Report\s*date|Collection\s*date|Date\s*of\s*service)[:\s]*"
        r"([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
        text,
        re.I,
    )
    if date_match:
        results.append(
            ExtractedField(
                field_id=_field_id(page_number, index, "Report date"),
                label="Report date",
                value=date_match.group(1).strip(),
                unit="",
                reference_range="",
                status="not_applicable",
                confidence="clearly_visible",
                page_number=page_number,
                source_text=date_match.group(0).strip(),
                extraction_method="native_text",
                user_edited=False,
            )
        )

    return results


def _process_saved_pdf(
    pdf_path: Path,
    pages_dir: Path,
    document_id: str,
    set_stage: Callable[[str], None] = lambda stage: None,
) -> tuple[list[PageInfo], list[ExtractedField]]:
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        raise PermanentProcessingError(
            "Invalid PDF.", technical_detail=f"{type(e).__name__}: {e}"
        ) from e

    try:
        if doc.page_count < 1:
            raise PermanentProcessingError("PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise PermanentProcessingError(f"Maximum {MAX_PAGES} pages.")

        pages: list[PageInfo] = []
        fields: list[ExtractedField] = []

        set_stage("reading")

        for i, page in enumerate(doc):
            n = i + 1
            text = page.get_text("text", sort=True).strip()
            preview = pages_dir / f"page-{n}.png"
            page.get_pixmap(dpi=RENDER_DPI, alpha=False).save(str(preview))

            # Step 1: Native PDF text extraction
            native_fields = _extract_native_text_fields(text, n)
            if native_fields:
                page_fields = native_fields
            else:
                # Step 2: Vision model only for scanned/unparsed pages. A
                # transient failure (Ollama unreachable/timeout) propagates
                # so the whole job can be retried; a permanent per-page
                # failure just leaves that page's fields empty, matching
                # the existing "could_not_read" degrade-gracefully design.
                set_stage("extracting")
                try:
                    page_fields = _extract_page_fields(preview, n, text, set_stage)
                except PermanentProcessingError:
                    page_fields = []

            fields.extend(page_fields)
            pages.append(PageInfo(
                page_number=n,
                preview_url=f"/api/documents/v2/{document_id}/pages/{n}/preview",
                text_available=bool(text),
                extracted_field_count=len(page_fields),
            ))
    finally:
        doc.close()

    return pages, fields


def _process_saved_image(
    raw_path: Path,
    suffix: str,
    pages_dir: Path,
    document_id: str,
    set_stage: Callable[[str], None] = lambda stage: None,
) -> tuple[list[PageInfo], list[ExtractedField]]:
    set_stage("reading")
    validation = validate_image_file(str(raw_path))

    if not validation.valid or not validation.path:
        raise PermanentProcessingError(validation.error or "Invalid image.")

    preview = pages_dir / "page-1.png"

    with Image.open(validation.path) as image:
        image.convert("RGB").save(preview, format="PNG")

    raw_path.unlink(missing_ok=True)
    set_stage("extracting")
    try:
        page_fields = _extract_page_fields(preview, 1, "", set_stage)
    except TransientProcessingError as error:
        # Lab-field vision on dense radiology photos routinely exceeds the
        # local vision budget. Imaging already reads this class of upload —
        # fail permanently with a clear handoff instead of another retry loop.
        raise PermanentProcessingError(
            "This photo could not be read as a lab document. "
            "Radiology report photos (MRI, X-ray, CT) belong in Imaging — "
            "use Open Imaging instead.",
            technical_detail=error.technical_detail,
        ) from error

    pages = [
        PageInfo(
            page_number=1,
            preview_url=f"/api/documents/v2/{document_id}/pages/1/preview",
            text_available=False,
            extracted_field_count=len(page_fields),
        )
    ]

    return pages, page_fields


async def _ingest_pdf(
    file: UploadFile,
    folder: Path,
    pages_dir: Path,
    document_id: str,
) -> tuple[list[PageInfo], list[ExtractedField]]:
    pdf_path, _ = await _save_upload_file(file, folder, pages_dir, ".pdf")
    return _process_saved_pdf(pdf_path, pages_dir, document_id)


async def _ingest_image(
    file: UploadFile,
    suffix: str,
    pages_dir: Path,
    document_id: str,
) -> tuple[list[PageInfo], list[ExtractedField]]:
    raw_path, _ = await _save_upload_file(file, folder=pages_dir.parent, pages_dir=pages_dir, suffix=suffix)
    return _process_saved_image(raw_path, suffix, pages_dir, document_id)


class SessionSummary(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int = 0
    field_count: int = 0
    confirmed: bool = False
    updated_at: str = ""


def _list_document_sessions(user: User) -> list[SessionSummary]:
    if not TEMP_DIR.exists():
        return []

    with session_scope() as session:
        owned = owned_document_ids(session, user.id)

    sessions: list[SessionSummary] = []
    for document_id in owned:
        path = _state_path(document_id)
        if not path.is_file():
            continue
        try:
            state = DocumentState.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        sessions.append(
            SessionSummary(
                document_id=state.document_id,
                filename=state.filename,
                status=state.status,
                page_count=state.page_count,
                field_count=len(state.fields),
                confirmed=state.confirmed,
                updated_at=str(int(path.stat().st_mtime)),
            )
        )

    sessions.sort(key=lambda item: item.updated_at, reverse=True)
    return sessions[:20]


@router.get("/sessions")
async def list_sessions(user: User = Depends(require_user)) -> dict[str, object]:
    sessions = _list_document_sessions(user)
    return {"count": len(sessions), "sessions": [item.model_dump() for item in sessions]}


@router.get("/sample/lab-report")
async def sample_lab_report():
    """Serve the bundled three-date synthetic lab report for portfolio demos.

    The file ships in the repo (and the Docker image — see Dockerfile.render
    and .dockerignore), but a packaging mistake in either has previously
    made this file silently absent in a deployed environment while working
    fine locally. Regenerating it on demand means that class of bug
    degrades to "slightly slower first request," not "demo permanently
    broken until the next deploy."
    """
    sample_path = BASE_DIR / "data" / "samples" / "sample-lab-report.pdf"
    if not sample_path.exists():
        logger.warning(
            "sample_lab_report_missing_regenerating",
            extra={"path": str(sample_path)},
        )
        try:
            generate_sample_lab_report(sample_path)
        except Exception as error:
            logger.error(
                "sample_lab_report_generation_failed",
                extra={"technical_detail": f"{type(error).__name__}: {error}"},
                exc_info=error,
            )
            raise MediGuideError(
                "DEMO_FIXTURE_UNAVAILABLE",
                "We couldn't prepare the synthetic reports.",
                status_code=503,
                retryable=True,
                technical_detail=f"{type(error).__name__}: {error}",
            ) from error
    return FileResponse(
        sample_path,
        media_type="application/pdf",
        filename="sample-lab-report.pdf",
    )


@router.post("/upload", response_model=UploadResponse)
async def upload(
    file: UploadFile = File(...), user: User = Depends(require_user)
) -> UploadResponse:
    """Store the uploaded file and return immediately — no extraction yet."""
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

    document_id = uuid.uuid4().hex
    folder = _folder(document_id)
    pages_dir = folder / "pages"
    folder.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    try:
        _, file_size = await _save_upload_file(file, folder, pages_dir, suffix)
        state = DocumentState(
            document_id=document_id,
            filename=file.filename or f"document{suffix}",
            page_count=0,
            status="uploaded",
            pages=[],
            fields=[],
            confirmed=False,
            content_type=file.content_type or "",
            file_size=file_size,
        )
        _save_state(state)

        # The Document row is what makes this upload owned and reachable, so
        # it is required: without it nobody could open, retry or delete the
        # file, and it would only linger until the orphan sweep removes it.
        try:
            with session_scope() as session:
                create_uploaded_document(
                    session,
                    document_id=document_id,
                    filename=state.filename,
                    content_type=state.content_type,
                    storage_path=str(folder),
                    owner_id=user.id,
                )
        except Exception as db_error:
            raise MediGuideError(
                "UPLOAD_NOT_SAVED",
                "We couldn't save this upload. Please try again in a moment.",
                status_code=503,
                retryable=True,
                technical_detail=f"{type(db_error).__name__}: {db_error}",
            ) from db_error

        return UploadResponse(
            document_id=document_id,
            filename=state.filename,
            content_type=state.content_type,
            file_size=file_size,
            status="uploaded",
        )
    except (HTTPException, MediGuideError):
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"MediGuide could not store this upload: {type(e).__name__}",
        ) from e


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def document_status(
    document_id: str, user: User = Depends(require_user)
) -> DocumentStatusResponse:
    state = _load_owned_state(document_id, user)
    return DocumentStatusResponse(
        document_id=state.document_id,
        filename=state.filename,
        status=state.status,
        page_count=state.page_count,
        field_count=len(state.fields),
        stage=state.stage,
        retry_attempt=state.retry_attempt,
        retry_max=state.retry_max,
        safe_error_message=state.safe_error_message,
    )


@router.post("/{document_id}/process", response_model=DocumentState)
async def process_document(
    document_id: str, user: User = Depends(require_user)
) -> DocumentState:
    """Extract pages and fields from a previously uploaded document."""
    state = _load_owned_state(document_id, user)
    folder = _folder(document_id)
    pages_dir = folder / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    if state.status == "review_required" and state.fields:
        return state
    if state.status == "confirmed":
        return state

    state.status = "extracting"
    _save_state(state)

    def _run(set_stage: Callable[[str], None]) -> tuple[list[PageInfo], list[ExtractedField]]:
        set_stage("validating")
        pdf_path = folder / "document.pdf"
        if pdf_path.exists():
            return _process_saved_pdf(pdf_path, pages_dir, document_id, set_stage)

        upload_files = list(pages_dir.glob("upload.*"))
        if not upload_files:
            raise PermanentProcessingError("Uploaded file not found for this document.")
        raw_path = upload_files[0]
        suffix = raw_path.suffix.lower()
        return _process_saved_image(raw_path, suffix, pages_dir, document_id, set_stage)

    def _on_stage(stage: str, retry_attempt: int, retry_max: int) -> None:
        # Mutates the same `state` this closure captured, not a copy — the
        # success/failure paths below persist whatever this last recorded.
        state.stage = stage
        state.retry_attempt = retry_attempt
        state.retry_max = retry_max
        _save_state(state)

    try:
        pages, fields = await run_in_threadpool(
            run_extraction_job,
            document_id=document_id,
            job_type="document_extraction",
            work=_run,
            on_stage=_on_stage,
        )

        state = DocumentState(
            document_id=document_id,
            filename=state.filename,
            page_count=len(pages),
            status="review_required",
            pages=pages,
            fields=fields,
            confirmed=False,
            content_type=state.content_type,
            file_size=state.file_size,
        )
        _save_state(state)
        return state

    except MediGuideError as error:
        failed = state.model_copy(
            update={
                "status": "failed",
                "stage": error.stage,
                "safe_error_message": error.message,
                "retry_attempt": 0,
                "retry_max": 0,
            }
        )
        _save_state(failed)
        raise
    except Exception:
        failed = state.model_copy(update={"status": "failed"})
        _save_state(failed)
        raise


@router.post("/upload-and-process", response_model=DocumentState, include_in_schema=False)
async def upload_and_process(
    file: UploadFile = File(...), user: User = Depends(require_user)
) -> DocumentState:
    """Legacy one-step upload used by older clients."""
    uploaded = await upload(file, user)
    return await process_document(uploaded.document_id, user)


@router.get("/{document_id}", response_model=DocumentState)
async def get_document(document_id: str, user: User = Depends(require_user)) -> DocumentState:
    return _load_owned_state(document_id, user)


@router.get("/{document_id}/pages/{page_number}/preview")
async def preview(document_id: str, page_number: int, user: User = Depends(require_user)):
    state = _load_owned_state(document_id, user)
    if page_number < 1 or page_number > state.page_count:
        raise HTTPException(status_code=404, detail="Page not found.")
    path = _folder(document_id) / "pages" / f"page-{page_number}.png"
    return FileResponse(path, media_type="image/png")


_REVIEWABLE_ATTRIBUTES = ("label", "value", "unit", "reference_range")


def _merge_reviewed_fields(
    extracted: list[ExtractedField],
    submitted: list[ExtractedField],
    excluded_ids: set[str],
) -> list[ExtractedField]:
    """Applies the reviewer's text edits onto the server's own extraction.

    Provenance (page, source text, confidence, extraction method) is never
    taken from the request. A field id the server didn't extract is
    rejected rather than silently added.
    """
    by_id = {field.field_id: field for field in extracted}
    merged: list[ExtractedField] = []
    for item in submitted:
        original = by_id.get(item.field_id)
        if original is None:
            raise MediGuideError(
                "UNKNOWN_FIELD",
                "This review includes a value that wasn't extracted from the document. "
                "Reload the document and review it again.",
                status_code=422,
            )
        if item.field_id in excluded_ids:
            continue
        edits = {name: getattr(item, name) for name in _REVIEWABLE_ATTRIBUTES}
        edited = any(edits[name] != getattr(original, name) for name in _REVIEWABLE_ATTRIBUTES)
        update: dict[str, Any] = {**edits, "user_edited": original.user_edited or edited}
        if edited:
            update["status"] = _recompute_status(item.value, item.reference_range, item.status)
        merged.append(original.model_copy(update=update))
    return merged


def _report_date_for(document_id: str, fields: list[ExtractedField]) -> str | None:
    # Prefer human-confirmed date fields (supports multi-page / multi-date reports).
    for field in fields:
        if "date" in field.label.lower() and field.value.strip():
            return field.value.strip()
    pdf_path = _folder(document_id) / "document.pdf"
    if not pdf_path.exists():
        return None
    try:
        doc = pymupdf.open(pdf_path)
        try:
            for page in doc:
                match = re.search(
                    r"(?:Report\s*date|Date|Collection\s*date)[:\s]*([0-9\-/]+)",
                    page.get_text("text"),
                    re.I,
                )
                if match:
                    return match.group(1).strip()
        finally:
            doc.close()
    except Exception:
        return None
    return None


@router.post("/{document_id}/confirm")
async def confirm(
    document_id: str, request: ConfirmRequest, user: User = Depends(require_user)
):
    state = _load_owned_state(document_id, user)
    if state.confirmed:
        raise MediGuideError(
            "DOCUMENT_ALREADY_CONFIRMED",
            "This report was already confirmed. Its verified values are kept as they were.",
            status_code=409,
        )
    if state.status != "review_required" or not state.fields:
        raise MediGuideError(
            "DOCUMENT_NOT_READY",
            "This document hasn't finished processing, so there is nothing to confirm yet.",
            status_code=409,
        )
    if not request.reviewed_names_values_units_dates:
        raise HTTPException(
            status_code=400,
            detail="Review names, values, units, dates, and ranges first.",
        )
    if not request.fields:
        raise HTTPException(status_code=400, detail="No reviewed fields supplied.")

    confirmed_fields = _merge_reviewed_fields(
        state.fields, request.fields, set(request.excluded_field_ids)
    )
    if not confirmed_fields:
        raise HTTPException(
            status_code=400,
            detail="Every value was rejected. Keep at least one to confirm this report.",
        )
    report_date = _report_date_for(document_id, confirmed_fields)

    # The database write comes first and is all-or-nothing. Only once it has
    # committed is the review session marked confirmed, so a failure never
    # leaves a report that looks confirmed but is missing from Labs.
    try:
        with session_scope() as session:
            if get_owned_document(session, document_id, user.id) is None:
                raise not_found("Document")
            persistence = create_observations_from_document(
                session,
                document_id=document_id,
                filename=state.filename,
                page_count=state.page_count,
                pages=[page.model_dump() for page in state.pages],
                fields=[field.model_dump() for field in confirmed_fields],
                report_date=report_date,
                storage_path=str(_folder(document_id)),
            )
    except MediGuideError:
        raise
    except Exception as error:
        raise MediGuideError(
            "CONFIRMATION_NOT_SAVED",
            "Your review wasn't saved, so nothing changed. Please try confirming again.",
            status_code=503,
            retryable=True,
            technical_detail=f"{type(error).__name__}: {error}",
        ) from error

    state.fields = confirmed_fields
    state.confirmed = True
    state.status = "confirmed"
    _save_state(state)

    return {
        "document_id": document_id,
        "confirmed": True,
        "fields": state.fields,
        "persistence": {"persisted": True, **persistence},
    }


@router.delete("/{document_id}")
async def delete_document(document_id: str, user: User = Depends(require_user)) -> dict[str, object]:
    """Permanently removes an owned document: its database records (fields,
    lab observations, jobs) and its stored original and page previews."""
    with session_scope() as session:
        document = get_owned_document(session, document_id, user.id)
        if document is None:
            raise not_found("Document")
        session.delete(document)
    shutil.rmtree(_folder(document_id), ignore_errors=True)
    logger.info("document_deleted", extra={"document_id": document_id})
    return {"deleted": True, "document_id": document_id}


@router.post("/{document_id}/explain", response_model=ExplainResponse)
async def explain(
    document_id: str, request: ExplainRequest, user: User = Depends(require_user)
) -> ExplainResponse:
    state = _load_owned_state(document_id, user)
    if not state.confirmed:
        raise HTTPException(
            status_code=409,
            detail="Human review and confirmation are required before explanation.",
        )

    emergency = check_for_emergency(request.question)

    if emergency.is_emergency:
        return ExplainResponse(
            document_id=document_id,
            answer_markdown=emergency.message or "Call emergency services immediately.",
            document_pages_cited=[],
            sources=[],
            limitations=["This response did not use the document or approved sources."],
        )  

    context = _confirmed_context(state.fields)
    evidence = retrieve_approved_evidence(request.question + "\n" + context, top_k=5)
    pages = sorted({f.page_number for f in state.fields})

    if not evidence:
        return ExplainResponse(
            document_id=document_id,
            answer_markdown=(
                "### Limited trusted information available\n\n"
                "MediGuide preserved the user-confirmed document information, "
                "but no sufficiently relevant approved educational source was "
                "retrieved. It will not add unsupported medical explanation.\n\n"
                + context
            ),
            document_pages_cited=pages,
            sources=[],
            limitations=[
                "No sufficiently relevant approved knowledge source was retrieved.",
                "Document fields were reviewed and confirmed by the user.",
                "This is not a diagnosis or treatment recommendation.",
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
QUESTION
{request.question}

USER-CONFIRMED DOCUMENT INFORMATION
{context}

APPROVED EVIDENCE
{chr(10).join(source_text)}

Write a plain-language educational explanation.
Use [D1], [D2], etc. for document-page claims.
Use [1], [2], etc. for general claims from approved sources.
Do not diagnose, prescribe, recommend dose changes, or invent citations.
Include:
- What the document shows
- General explanation
- What cannot be determined
- Questions to ask your clinician
"""

    try:
        from ollama import Client

        client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
        response = client.chat(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": "Use only confirmed document data and supplied approved evidence."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        answer = response.message.content.strip()
    except Exception:
        return ExplainResponse(
            document_id=document_id,
            answer_markdown=(
                "### Confirmed document information\n\n"
                "The text model is unavailable on this deployment, so MediGuide is showing "
                "only the user-confirmed fields from your report.\n\n"
                + context
            ),
            document_pages_cited=pages,
            sources=sources,
            limitations=[
                "Educational explanation model is unavailable on this deployment.",
                "Document fields were reviewed and confirmed by the user.",
                "This is not a diagnosis or treatment recommendation.",
            ],
        )

    return ExplainResponse(
        document_id=document_id,
        answer_markdown=answer,
        document_pages_cited=pages,
        sources=sources,
        limitations=[
            "Automated extraction can be incorrect.",
            "The user confirmed the fields used in this explanation.",
            "Printed reference ranges vary by laboratory and context.",
            "This explanation is educational and is not a diagnosis.",
        ],
    )
