"""Imaging workspace: study organization + radiology-report intelligence.

MediGuide Imaging organizes imaging studies, extracts and displays the TEXT
of radiology reports, compares report wording over time, and explains
imaging terminology from approved sources. It never interprets pixels: no
endpoint in this module diagnoses, scores, or classifies the underlying
scan image — only the report text a radiologist already wrote.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import select

from src.config import (
    BASE_DIR,
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_VISION_TIMEOUT_SECONDS,
    PROCESSING_RETRY_ATTEMPTS,
    PROCESSING_RETRY_BACKOFF_SCHEDULE_SECONDS,
    VISION_MODEL_NAME,
)
from src.database.imaging_repository import (
    confirm_findings,
    confirm_report_sections,
    create_study,
    decide_report_section,
    delete_study,
    derive_study_verification_status,
    get_finding,
    get_findings,
    get_report_sections,
    get_owned_study,
    list_studies,
    modality_summary,
    report_gaps_for_study,
    serialize_finding,
    serialize_section,
    serialize_study,
    set_pending_report_document,
    set_study_report_document,
    set_study_verification_status,
    replace_report_sections,
    upsert_findings_from_sections,
)
from src.auth.dependencies import not_found, require_user
from src.database.models import ImagingStudy, ProcessingJob, User
from src.database.repository import (
    add_document_page,
    create_uploaded_document,
    get_owned_document,
    set_document_page_count,
)
from src.database.session import probe_database, session_scope
from src.document_intelligence import retrieve_approved_evidence
from src.image_validator import prepare_vision_image, validate_image_file
from src.imaging_compare import compare_section_text
from src.imaging_dicom import is_dicom_file
from src.imaging_sections import (
    SECTION_TYPES,
    ReportLine,
    SectionSpan,
    classify_report,
    extract_report_details,
    find_sections,
    lines_from_rows,
    section_regions,
    sections_from_ranges,
)
from src.labs.table_reader import Word, group_rows, rows_from_words
from src.ocr import client_ocr, ocr_available, ocr_image, save_client_ocr
from src.observability.logging import get_logger
from src.shared import file_store
from src.shared.errors import MediGuideError
from src.shared.job_runner import run_extraction_job
from src.shared.resilience import (
    PermanentProcessingError,
    TransientProcessingError,
    call_with_retry,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/imaging", tags=["Imaging"])

MODALITY_LABELS: dict[str, str] = {
    "xray": "X-Ray",
    "ct": "CT",
    "mri": "MRI",
    "ultrasound": "Ultrasound",
    "pet_ct": "PET/CT",
}

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

TEMP_DIR = Path(os.getenv("IMAGING_TEMP_DIR", str(BASE_DIR / "outputs" / "imaging")))


def _folder(document_id: str) -> Path:
    """A report's folder (original, page previews, lines.json)."""
    return file_store.folder("imaging", TEMP_DIR, document_id)
MAX_MB = int(os.getenv("IMAGING_MAX_MB", "20"))
MAX_PAGES = int(os.getenv("IMAGING_MAX_PAGES", "25"))
RENDER_DPI = int(os.getenv("IMAGING_RENDER_DPI", "140"))
PROCESSOR_VERSION = "imaging-sections-v2"
OCR_RENDER_DPI = 300


# --------------------------------------------------------------------------
# Request/response schemas
# --------------------------------------------------------------------------


class StudyCreateRequest(BaseModel):
    modality: str
    body_region: str = ""
    study_description: str = ""
    study_date: str | None = None
    institution: str = ""
    accession_identifier: str = ""


class SectionEdit(BaseModel):
    section_type: str
    text: str


class ConfirmSectionsRequest(BaseModel):
    sections: list[SectionEdit] = []
    confirm_types: list[str] = []
    reviewed: bool = False


class SectionDecision(BaseModel):
    decision: str
    text: str | None = None


class SectionBoundary(BaseModel):
    section_type: str
    line_start: int
    line_end: int


class SectionBoundariesRequest(BaseModel):
    sections: list[SectionBoundary]


class ApplyDetailsRequest(BaseModel):
    fields: list[str]


class FindingUpdate(BaseModel):
    finding_id: str
    confirmed_text: str | None = None
    verification_status: str = "confirmed"


class ConfirmFindingsRequest(BaseModel):
    findings: list[FindingUpdate] = []
    reviewed: bool = False


class FindingExplainRequest(BaseModel):
    finding_id: str
    language: str = "English"


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str


class TerminologyRequest(BaseModel):
    term: str
    modality: str | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    cleaned = cleaned.removesuffix("```")
    return json.loads(cleaned.strip())


IMAGING_SECTION_PROMPT = """
You are MediGuide's radiology-report reading assistant. Do not diagnose or
interpret images. Extract ONLY the verbatim text already present in this
report page, organized under these section names if present: exam,
clinical_history, technique, comparison, findings, impression,
recommendations.

Return JSON only:
{"sections": {"exam": "", "clinical_history": "", "technique": "", "comparison": "", "findings": "", "impression": "", "recommendations": ""}}

Rules:
- Use an empty string for any section not present on this page.
- Copy text exactly as printed. Never summarize, infer, or add content.
- Never invent diagnostic language.
"""


def _extract_sections_via_vision(
    image_path: Path,
    set_stage: Callable[[str], None] = lambda stage: None,
) -> dict[str, str]:
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
            model=VISION_MODEL_NAME,
            messages=[{
                "role": "user",
                "content": IMAGING_SECTION_PROMPT,
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
            f"Vision OCR could not read this report ({type(error).__name__}).",
            technical_detail=f"{type(error).__name__}: {error}",
        ) from error

    data = _parse_json(response.message.content)
    raw_sections = data.get("sections", {})
    if not isinstance(raw_sections, dict):
        return {}
    return {
        key: str(value).strip()
        for key, value in raw_sections.items()
        if key in SECTION_TYPES and str(value).strip()
    }


def _ocr_lines(image: Image.Image, page_number: int) -> tuple[list[ReportLine], tuple[float, float], int]:
    """Lines read by local Tesseract OCR, with their positions. Returns the
    coordinate space size and the rotation applied before reading."""
    ocr = ocr_image(image, dpi=OCR_RENDER_DPI, page_number=page_number)
    rows = group_rows([Word(w.x0, w.y0, w.x1, w.y1, w.text, w.confidence) for w in ocr.words])
    return lines_from_rows(rows, page_number), (ocr.width, ocr.height), ocr.rotation_applied


def _read_report(
    saved_path: Path, suffix: str, pages_dir: Path
) -> tuple[list[ReportLine], dict[int, tuple[float, float]], dict[int, str], int]:
    """Every line of the report in reading order, across pages.

    PDF pages use their text layer; a page without one (a scan) and photo
    uploads are read by local OCR. Nothing is sent to an outside service.
    Returns (lines, page sizes for regions, read method per page, page count).
    """
    lines: list[ReportLine] = []
    sizes: dict[int, tuple[float, float]] = {}
    methods: dict[int, str] = {}
    pages_dir.mkdir(parents=True, exist_ok=True)

    if suffix == ".pdf":
        try:
            doc = pymupdf.open(saved_path)
        except Exception as error:
            raise PermanentProcessingError(
                "Invalid report PDF.", technical_detail=f"{type(error).__name__}: {error}"
            ) from error
        try:
            if doc.page_count < 1:
                raise PermanentProcessingError("Report PDF has no pages.")
            if doc.page_count > MAX_PAGES:
                raise PermanentProcessingError(f"Maximum {MAX_PAGES} pages.")
            for index, page in enumerate(doc):
                page_number = index + 1
                preview = pages_dir / f"page-{page_number}.png"
                page.get_pixmap(dpi=RENDER_DPI, alpha=False).save(str(preview))
                page_lines = lines_from_rows(rows_from_words(page.get_text("words")), page_number)
                if page_lines:
                    lines.extend(page_lines)
                    sizes[page_number] = (page.rect.width, page.rect.height)
                    methods[page_number] = "native_text"
                elif ocr_available():
                    pix = page.get_pixmap(dpi=OCR_RENDER_DPI, alpha=False)
                    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    page_lines, size, rotation = _ocr_lines(image, page_number)
                    if page_lines:
                        lines.extend(page_lines)
                        sizes[page_number] = size
                        methods[page_number] = "tesseract_ocr"
                        if rotation:
                            with Image.open(preview) as shown:
                                shown.rotate(-rotation, expand=True).save(preview, format="PNG")
            return lines, sizes, methods, doc.page_count
        finally:
            doc.close()

    validation = validate_image_file(str(saved_path))
    if not validation.valid or not validation.path:
        raise PermanentProcessingError(validation.error or "Invalid image.")
    preview = pages_dir / "page-1.png"
    with Image.open(validation.path) as image:
        upright = image.convert("RGB")
        upright.save(preview, format="PNG")
        if ocr_available():
            page_lines, size, rotation = _ocr_lines(upright, 1)
            if page_lines:
                lines.extend(page_lines)
                sizes[1] = size
                methods[1] = "tesseract_ocr"
                if rotation:
                    upright.rotate(-rotation, expand=True).save(preview, format="PNG")
    return lines, sizes, methods, 1


def _section_method(span: SectionSpan, methods: dict[int, str]) -> str:
    used = {methods.get(line.page, "") for line in span.lines}
    return "tesseract_ocr" if "tesseract_ocr" in used else "native_text"


def _span_payload(span: SectionSpan, sizes: dict[int, tuple[float, float]], methods: dict[int, str]) -> dict[str, Any]:
    return {
        "section_type": span.section_type,
        "text": span.text,
        "page_start": span.page_start,
        "page_end": span.page_end,
        "line_start": span.line_start,
        "line_end": span.line_end,
        "regions": section_regions(span, sizes),
        "extraction_method": _section_method(span, methods),
    }


def _page_texts(span_lines: list[ReportLine]) -> list[tuple[int, str]]:
    by_page: dict[int, list[str]] = {}
    for line in span_lines:
        by_page.setdefault(line.page, []).append(line.text)
    return [(page, " ".join(texts)) for page, texts in sorted(by_page.items())]


def _save_lines(folder: Path, lines: list[ReportLine], sizes: dict[int, tuple[float, float]], methods: dict[int, str]) -> None:
    """The report's lines (with pages and positions) for boundary corrections."""
    (folder / "lines.json").write_text(json.dumps({
        "lines": [{"page": line.page, "text": line.text, "bbox": list(line.bbox) if line.bbox else None} for line in lines],
        "sizes": {str(page): list(size) for page, size in sizes.items()},
        "methods": {str(page): method for page, method in methods.items()},
    }), encoding="utf-8")


def _load_lines(folder: Path) -> tuple[list[ReportLine], dict[int, tuple[float, float]], dict[int, str]] | None:
    path = folder / "lines.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [ReportLine(int(item["page"]), str(item["text"]), tuple(item["bbox"]) if item.get("bbox") else None) for item in data.get("lines", [])]
    sizes = {int(page): (float(size[0]), float(size[1])) for page, size in data.get("sizes", {}).items()}
    methods = {int(page): str(method) for page, method in data.get("methods", {}).items()}
    return lines, sizes, methods


async def _save_report_upload(file: UploadFile, document_id: str, suffix: str) -> Path:
    folder = _folder(document_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"report{suffix}"
    max_bytes = MAX_MB * 1024 * 1024
    total = 0

    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise MediGuideError(
                    "FILE_TOO_LARGE", f"File exceeds {MAX_MB} MB.", status_code=413
                )
            out.write(chunk)

    if not total:
        raise MediGuideError("EMPTY_FILE", "The uploaded file was empty.", status_code=422)

    if suffix == ".pdf" and not target.read_bytes()[:5].startswith(b"%PDF"):
        target.unlink(missing_ok=True)
        raise MediGuideError("INVALID_PDF", "File is not a valid PDF.", status_code=422)

    return target


# --------------------------------------------------------------------------
# Synthetic sample fixtures (educational demos — not real patient data)
# --------------------------------------------------------------------------


@router.get("/samples")
async def list_imaging_samples() -> dict[str, Any]:
    from src.sample_imaging_fixtures import generate_sample_imaging_reports, list_sample_metadata, sample_pdf_path

    samples_dir = BASE_DIR / "data" / "samples" / "imaging"
    # Self-heal missing fixtures the same way the lab sample endpoint does.
    if not any(sample_pdf_path(item["slug"], samples_dir) for item in list_sample_metadata()):
        generate_sample_imaging_reports(samples_dir)
    return {"samples": list_sample_metadata()}


@router.get("/samples/{slug}")
async def download_imaging_sample(slug: str) -> FileResponse:
    from src.sample_imaging_fixtures import generate_sample_imaging_reports, list_sample_metadata, sample_pdf_path

    allowed = {item["slug"] for item in list_sample_metadata()}
    if slug not in allowed:
        raise HTTPException(status_code=404, detail="Sample report not found.")

    samples_dir = BASE_DIR / "data" / "samples" / "imaging"
    path = sample_pdf_path(slug, samples_dir)
    if path is None:
        generate_sample_imaging_reports(samples_dir)
        path = sample_pdf_path(slug, samples_dir)
    if path is None:
        raise HTTPException(status_code=404, detail="Sample report file is missing.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{slug}.pdf",
    )


# --------------------------------------------------------------------------
# Study endpoints
# --------------------------------------------------------------------------


@router.get("/modalities")
async def list_modalities(user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        summary = {row["modality"]: row for row in modality_summary(session, user.id)}
    return {
        "modalities": [
            {
                "modality": code,
                "label": label,
                "study_count": summary.get(code, {}).get("study_count", 0),
                "latest_study_date": summary.get(code, {}).get("latest_study_date"),
            }
            for code, label in MODALITY_LABELS.items()
        ]
    }


@router.post("/studies")
async def create_study_endpoint(
    request: StudyCreateRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    if request.modality not in MODALITY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown modality '{request.modality}'. Expected one of: {', '.join(MODALITY_LABELS)}.",
        )
    with session_scope() as session:
        study = create_study(
            session,
            modality=request.modality,
            body_region=request.body_region,
            study_description=request.study_description,
            study_date=_parse_date(request.study_date),
            institution=request.institution,
            accession_identifier=request.accession_identifier,
            owner_id=user.id,
        )
        return serialize_study(study)


@router.get("/studies")
async def list_studies_endpoint(
    modality: str | None = None,
    body_region: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    with session_scope() as session:
        studies = list_studies(
            session,
            owner_id=user.id,
            modality=modality,
            body_region=body_region,
            date_from=_parse_date(date_from),
            date_to=_parse_date(date_to),
        )
        return {"studies": [serialize_study(study) for study in studies]}


@router.get("/studies/{study_id}")
async def get_study_endpoint(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        return serialize_study(study)


@router.delete("/studies/{study_id}")
async def delete_study_endpoint(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        deleted = (
            get_owned_study(session, study_id, user.id) is not None
            and delete_study(session, study_id)
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Imaging study not found.")
    return {"deleted": True}


# --------------------------------------------------------------------------
# Report attach / extract / confirm
# --------------------------------------------------------------------------


@router.post("/studies/{study_id}/report")
async def upload_report(
    study_id: str,
    file: UploadFile = File(...),
    client_ocr_pages: str | None = Form(None, alias="client_ocr"),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        # A new upload would replace the report the owner already reviewed
        # and hide its confirmed findings, so that is refused outright.
        # Unverified studies (including failed attempts) can still retry.
        if study.report_document_id and study.verification_status != "unverified":
            raise MediGuideError(
                "STUDY_ALREADY_VERIFIED",
                "This study already has a reviewed report. Add a new study for a different report.",
                status_code=409,
            )

    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    if is_dicom_file(Path(filename)):
        raise MediGuideError(
            "DICOM_NOT_YET_SUPPORTED",
            "DICOM files aren't processed yet — upload the report as a PDF or image for now.",
            status_code=415,
            retryable=False,
        )
    if suffix not in SUPPORTED_SUFFIXES:
        raise MediGuideError(
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type '{suffix or 'unknown'}'. Accepted: {', '.join(sorted(SUPPORTED_SUFFIXES))}.",
            status_code=415,
        )

    document_id = uuid.uuid4().hex
    folder = _folder(document_id)
    pages_dir = folder / "pages"

    try:
        saved_path = await _save_report_upload(file, document_id, suffix)
        save_client_ocr(folder, client_ocr_pages)
    except MediGuideError:
        shutil.rmtree(folder, ignore_errors=True)
        raise

    with session_scope() as session:
        create_uploaded_document(
            session,
            document_id=document_id,
            filename=filename or f"report{suffix}",
            content_type=file.content_type or "",
            storage_path=str(folder),
            owner_id=user.id,
        )
        # Set before extraction begins (not after it fails) so a status
        # poll started the moment this request was fired — before the
        # frontend has even seen this response — can already find it.
        set_pending_report_document(session, study_id, document_id)

    def work(set_stage) -> dict[str, str]:
        set_stage("reading")
        with client_ocr(folder):
            lines, sizes, methods, page_count = _read_report(saved_path, suffix, pages_dir)

        set_stage("extracting")
        spans = find_sections(lines)
        payloads = [_span_payload(span, sizes, methods) for span in spans]
        span_pages = {span.section_type: _page_texts(span.lines) for span in spans}

        if not payloads:
            # Last resort: the local AI vision model, page by page. Its text
            # is flagged as AI-read and has no positions to highlight.
            last_permanent: PermanentProcessingError | None = None
            found: dict[str, dict[str, Any]] = {}
            for page_number in range(1, page_count + 1):
                preview_path = pages_dir / f"page-{page_number}.png"
                try:
                    vision_sections = _extract_sections_via_vision(preview_path, set_stage)
                except PermanentProcessingError as error:
                    last_permanent = error
                    vision_sections = {}
                for key, value in vision_sections.items():
                    if key not in found:
                        found[key] = {"section_type": key, "text": value, "page_start": page_number,
                                      "page_end": page_number, "regions": [], "extraction_method": "vision_ocr"}
                        span_pages[key] = [(page_number, value)]
            payloads = [found[key] for key in SECTION_TYPES if key in found]
            if not payloads:
                if last_permanent is not None:
                    raise last_permanent
                raise PermanentProcessingError(
                    "No report sections could be read from this file. Upload a "
                    "text-based PDF, or a clear photo of the written radiology report.",
                )

        all_text = "\n".join(line.text for line in lines) or "\n".join(item["text"] for item in payloads)
        classification = classify_report(all_text, spans)
        details = extract_report_details(lines, spans) if lines else {}

        set_stage("saving")
        _save_lines(folder, lines, sizes, methods)
        with session_scope() as session:
            for page_number in range(1, page_count + 1):
                add_document_page(
                    session,
                    document_id=document_id,
                    page_number=page_number,
                    preview_path=f"/api/imaging/studies/{study_id}/report/pages/{page_number}/preview",
                    text_available=page_number in methods,
                )
            set_document_page_count(session, document_id, page_count)
            section_rows = replace_report_sections(
                session,
                study_id=study_id,
                document_id=document_id,
                spans=payloads,
                extractor_version=PROCESSOR_VERSION,
            )
            upsert_findings_from_sections(
                session,
                study_id=study_id,
                document_id=document_id,
                sections=section_rows,
                page_texts=span_pages,
            )
            set_study_report_document(session, study_id, document_id)
            study_row = session.get(ImagingStudy, study_id)
            if study_row is not None:
                study_row.report_details = json.dumps({
                    "classification": classification,
                    "details": details,
                    "applied": {},
                })
                set_study_verification_status(session, study_id, "unverified")

        return {item["section_type"]: item["text"] for item in payloads}

    sections = await run_in_threadpool(
        run_extraction_job,
        document_id=document_id,
        job_type="imaging_report_extraction",
        work=work,
    )
    return {"document_id": document_id, "sections": sections}


@router.get("/studies/{study_id}/report/status")
async def report_status(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    """Polling target for a report upload in flight — see
    ImagingStudy.pending_report_document_id's docstring for why this is
    keyed by study_id rather than document_id."""
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")

        document_id = study.pending_report_document_id
        if not document_id:
            return {"status": "idle", "stage": "", "retry_attempt": 0, "retry_max": 0, "safe_error_message": ""}

        job = session.execute(
            select(ProcessingJob).where(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == "imaging_report_extraction",
            )
        ).scalar_one_or_none()
        if job is None:
            return {"status": "idle", "stage": "", "retry_attempt": 0, "retry_max": 0, "safe_error_message": ""}

        return {
            "document_id": document_id,
            "status": job.status,
            "stage": job.stage,
            "retry_attempt": job.retry_attempt,
            "retry_max": job.retry_max,
            "safe_error_message": job.safe_error_message,
        }


@router.get("/studies/{study_id}/report/sections")
async def get_sections_endpoint(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        if not study.report_document_id:
            return {"sections": []}
        sections = get_report_sections(session, study.report_document_id)
        return {"sections": [serialize_section(section) for section in sections]}


@router.post("/studies/{study_id}/report/confirm")
async def confirm_sections_endpoint(
    study_id: str, request: ConfirmSectionsRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    if not request.reviewed:
        raise HTTPException(
            status_code=400, detail="Review the extracted report sections before confirming."
        )
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        if not study.report_document_id:
            raise HTTPException(status_code=409, detail="No report attached to this study yet.")

        edits = {item.section_type: item.text for item in request.sections}
        confirm_types = set(request.confirm_types) if request.confirm_types else None
        rows = confirm_report_sections(
            session,
            document_id=study.report_document_id,
            edits=edits,
            confirm_types=confirm_types,
        )
        new_status = derive_study_verification_status(rows)
        set_study_verification_status(session, study_id, new_status)
        return {
            "sections": [serialize_section(row) for row in rows],
            "verification_status": new_status,
        }


def _owned_report(session, study_id: str, user: User) -> ImagingStudy:
    study = get_owned_study(session, study_id, user.id)
    if study is None:
        raise HTTPException(status_code=404, detail="Imaging study not found.")
    if not study.report_document_id:
        raise HTTPException(status_code=409, detail="No report attached to this study yet.")
    return study


@router.post("/studies/{study_id}/report/sections/{section_type}/decision")
async def decide_section_endpoint(
    study_id: str, section_type: str, request: SectionDecision, user: User = Depends(require_user)
) -> dict[str, Any]:
    """Confirm (optionally with a correction), reject or undo one section.

    Saved immediately, so a partly reviewed report can be resumed later.
    """
    if request.decision not in {"confirmed", "rejected", "unverified"}:
        raise HTTPException(status_code=422, detail="Decision must be confirmed, rejected or unverified.")
    if request.text is not None and not request.text.strip():
        raise HTTPException(status_code=422, detail="A corrected section can't be empty. Reject it instead.")
    with session_scope() as session:
        study = _owned_report(session, study_id, user)
        row = decide_report_section(
            session,
            document_id=study.report_document_id,
            section_type=section_type,
            decision=request.decision,
            text=request.text,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="That section isn't in this report.")
        rows = get_report_sections(session, study.report_document_id)
        new_status = derive_study_verification_status(rows)
        set_study_verification_status(session, study_id, new_status)
        return {"sections": [serialize_section(item) for item in rows], "verification_status": new_status}


@router.get("/studies/{study_id}/report/lines")
async def report_lines_endpoint(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    """The report's lines in reading order (for correcting section boundaries)."""
    with session_scope() as session:
        study = _owned_report(session, study_id, user)
        document_id = study.report_document_id
    loaded = _load_lines(_folder(document_id))
    if loaded is None:
        return {"lines": [], "adjustable": False}
    lines, _, _ = loaded
    return {"lines": [{"index": index, "page": line.page, "text": line.text} for index, line in enumerate(lines)], "adjustable": True}


@router.put("/studies/{study_id}/report/sections/boundaries")
async def adjust_boundaries_endpoint(
    study_id: str, request: SectionBoundariesRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    """Re-draw section boundaries over the report's own lines.

    Each section is a contiguous range of report lines, so its text is
    always the radiologist's wording; nothing can be added. Only allowed
    while no section has been confirmed or rejected (undo those first), and
    every section starts unreviewed again afterwards.
    """
    with session_scope() as session:
        study = _owned_report(session, study_id, user)
        document_id = study.report_document_id
        current = get_report_sections(session, document_id)
        before = {
            row.section_type: ((json.loads(row.source_map or "{}") or {}).get("line_start"), (json.loads(row.source_map or "{}") or {}).get("line_end"))
            for row in current
        }
        if any(row.verification_status != "unverified" for row in current):
            raise MediGuideError(
                "SECTIONS_ALREADY_REVIEWED",
                "Undo the confirmed or rejected sections before changing section boundaries.",
                status_code=409,
            )
    loaded = _load_lines(_folder(document_id))
    if loaded is None:
        raise MediGuideError(
            "BOUNDARIES_NOT_ADJUSTABLE",
            "This report was read without line positions, so its section boundaries can't be adjusted. Edit the section text instead.",
            status_code=422,
        )
    lines, sizes, methods = loaded
    types = [item.section_type for item in request.sections]
    if not request.sections or any(t not in SECTION_TYPES for t in types) or len(set(types)) != len(types):
        raise HTTPException(status_code=422, detail="Each section type can be used once, from the known report sections.")
    ordered = sorted(request.sections, key=lambda item: item.line_start)
    previous_end = -1
    for item in ordered:
        if item.line_start < 0 or item.line_end >= len(lines) or item.line_start > item.line_end or item.line_start <= previous_end:
            raise HTTPException(status_code=422, detail="Section ranges must be within the report and must not overlap.")
        previous_end = item.line_end
    spans = sections_from_ranges(lines, [(item.section_type, item.line_start, item.line_end) for item in ordered])
    if not spans:
        raise HTTPException(status_code=422, detail="These boundaries leave every section empty.")
    payloads = [_span_payload(span, sizes, methods) for span in spans]
    for payload in payloads:
        # Only sections whose lines actually changed count as adjusted.
        payload["boundary_adjusted"] = before.get(payload["section_type"]) != (payload["line_start"], payload["line_end"])
    with session_scope() as session:
        rows = replace_report_sections(
            session,
            study_id=study_id,
            document_id=document_id,
            spans=payloads,
            extractor_version=PROCESSOR_VERSION,
            boundary_adjusted=True,
        )
        upsert_findings_from_sections(
            session, study_id=study_id, document_id=document_id, sections=rows,
            page_texts={span.section_type: _page_texts(span.lines) for span in spans},
        )
        set_study_verification_status(session, study_id, "unverified")
        return {"sections": [serialize_section(row) for row in rows], "verification_status": "unverified"}


_APPLICABLE_DETAILS = {
    "modality": ("classification", "modality"),
    "study_date": ("details", "exam_date"),
    "body_region": ("details", "body_region"),
    "institution": ("details", "facility"),
    "study_description": ("details", "study_description"),
}


@router.post("/studies/{study_id}/report/details/apply")
async def apply_report_details_endpoint(
    study_id: str, request: ApplyDetailsRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    """Copy details the report prints onto the study, only those the user
    picked. The report's own reading and the study's previous values are
    both kept in report_details for audit."""
    unknown = [name for name in request.fields if name not in _APPLICABLE_DETAILS]
    if unknown or not request.fields:
        raise HTTPException(status_code=422, detail="Pick details from: " + ", ".join(_APPLICABLE_DETAILS))
    with session_scope() as session:
        study = _owned_report(session, study_id, user)
        stored = json.loads(study.report_details or "{}")
        applied = stored.setdefault("applied", {})
        for name in request.fields:
            group, key = _APPLICABLE_DETAILS[name]
            if group == "classification":
                value = (stored.get("classification") or {}).get(key)
            else:
                value = ((stored.get("details") or {}).get(key) or {}).get("value")
            if not value:
                raise HTTPException(status_code=422, detail=f"The report doesn't state a {name.replace('_', ' ')}.")
            if name == "modality" and value not in MODALITY_LABELS:
                raise HTTPException(status_code=422, detail="That report type isn't one of the study types MediGuide organizes.")
            previous = getattr(study, name)
            if name == "study_date":
                value = _parse_date(value)
                previous = previous.isoformat() if previous else None
            setattr(study, name, value)
            applied[name] = {
                "value": value.isoformat() if isinstance(value, date) else value,
                "previous": previous,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            }
        study.report_details = json.dumps(stored)
        session.flush()
        return serialize_study(study)


@router.get("/studies/{study_id}/findings")
async def list_findings_endpoint(study_id: str, user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        findings = get_findings(session, study_id)
        gaps = report_gaps_for_study(session, study_id)
        return {
            "findings": [serialize_finding(row) for row in findings],
            "gaps": gaps,
            "boundary": (
                "MediGuide explains the radiologist's report. "
                "It does not independently diagnose the scan."
            ),
        }


@router.post("/studies/{study_id}/findings/confirm")
async def confirm_findings_endpoint(
    study_id: str, request: ConfirmFindingsRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    if not request.reviewed:
        raise HTTPException(
            status_code=400, detail="Review extracted findings before confirming."
        )
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None:
            raise HTTPException(status_code=404, detail="Imaging study not found.")
        rows = confirm_findings(
            session,
            study_id=study_id,
            updates=[item.model_dump() for item in request.findings],
        )
        return {"findings": [serialize_finding(row) for row in rows]}


@router.post("/findings/explain")
async def explain_finding_endpoint(
    request: FindingExplainRequest, user: User = Depends(require_user)
) -> dict[str, Any]:
    """Educational explanation for a verified finding — Layer 2 only.

    Report summary and source evidence remain available if the educational
    model or knowledge retrieval is unavailable.
    """
    with session_scope() as session:
        finding = get_finding(session, request.finding_id)
        study = get_owned_study(session, finding.study_id, user.id) if finding else None
        if finding is None or study is None:
            raise HTTPException(status_code=404, detail="Finding not found.")
        if finding.verification_status not in {"confirmed"}:
            raise HTTPException(
                status_code=409,
                detail="Confirm this finding before requesting an educational explanation.",
            )
        modality = study.modality
        finding_payload = serialize_finding(finding)
        report_excerpt = finding.confirmed_text or finding.original_text

    query = finding.normalized_concept or report_excerpt
    evidence = retrieve_approved_evidence(query, top_k=5)

    record_provenance = {
        "finding_id": finding_payload["finding_id"],
        "finding_text": report_excerpt,
        "section": finding_payload["section"],
        "source_document_id": finding_payload["source_document_id"],
        "source_page": finding_payload["source_page"],
        "verification_status": finding_payload["verification_status"],
    }

    if not evidence:
        return {
            "finding": finding_payload,
            "record_provenance": record_provenance,
            "answer_markdown": (
                "We don't have enough approved source information to explain "
                "this finding reliably."
            ),
            "what_this_means": "",
            "what_can_be_associated": "",
            "what_may_be_discussed_next": "",
            "sources": [],
            "education_available": False,
            "unavailable_reason": "insufficient_evidence",
        }

    sources = []
    source_lines = []
    for index, item in enumerate(evidence, 1):
        sources.append(
            {
                "citation_number": index,
                "title": item.get("title", "Untitled source"),
                "publisher": item.get("publisher", "Unknown publisher"),
                "source_url": item.get("source_url", ""),
                "passage": item.get("passage", ""),
            }
        )
        source_lines.append(f"[{index}] {item.get('title', '')} — {item.get('passage', '')}")

    modality_label = MODALITY_LABELS.get(modality, modality)
    prompt = f"""Explain this radiology-report finding for a patient using ONLY the approved evidence.

FINDING (from the radiology report — do not invent beyond this wording):
{report_excerpt}

Normalized concept (may be empty): {finding.normalized_concept or "not mapped"}
Modality context: {modality_label}

Write three short sections with these exact headings:
WHAT DOES THIS MEAN?
WHAT CAN BE ASSOCIATED WITH THIS?
WHAT MAY BE DISCUSSED NEXT?

Rules:
- Use phrases like "can be associated with", "may occur with", "possible contributing factors include".
- Never say "This happened because...", "The cause is...", "You need surgery", or prescribe treatment.
- Prefer "A clinician may consider..." and "Depending on examination findings...".
- Cite approved evidence with [n].
- If evidence is weak for a section, say so plainly.

APPROVED EVIDENCE
{chr(10).join(source_lines)}
"""

    try:
        from ollama import Client

        client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "General educational information only. Use only the supplied "
                        "approved evidence. Never diagnose from pixels or prescribe treatment."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        answer = response.message.content.strip()
        education_available = True
        unavailable_reason = ""
    except Exception:
        answer = "Educational explanation is temporarily unavailable."
        education_available = False
        unavailable_reason = "model_unavailable"

    return {
        "finding": finding_payload,
        "record_provenance": record_provenance,
        "answer_markdown": answer,
        "sources": sources,
        "education_available": education_available,
        "unavailable_reason": unavailable_reason,
        "education_provenance": {
            "citations": sources,
            "corpus": "approved_knowledge",
        },
    }


@router.get("/studies/{study_id}/report/pages/{page_number}/preview")
async def report_page_preview(study_id: str, page_number: int, user: User = Depends(require_user)):
    with session_scope() as session:
        study = get_owned_study(session, study_id, user.id)
        if study is None or not study.report_document_id:
            raise HTTPException(status_code=404, detail="No report attached to this study.")
        document_id = study.report_document_id

    path = _folder(document_id) / "pages" / f"page-{page_number}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Page preview not found.")
    return FileResponse(path, media_type="image/png")


# --------------------------------------------------------------------------
# Compare + terminology
# --------------------------------------------------------------------------


@router.post("/compare")
async def compare_reports(request: CompareRequest, user: User = Depends(require_user)) -> dict[str, Any]:
    with session_scope() as session:
        for document_id in (request.document_id_a, request.document_id_b):
            if get_owned_document(session, document_id, user.id) is None:
                raise not_found("Report")
        sections_a = {
            section.section_type: section
            for section in get_report_sections(session, request.document_id_a)
            if section.verification_status == "confirmed"
        }
        sections_b = {
            section.section_type: section
            for section in get_report_sections(session, request.document_id_b)
            if section.verification_status == "confirmed"
        }

    if not sections_a or not sections_b:
        raise MediGuideError(
            "REPORTS_NOT_VERIFIED",
            "Both reports must be reviewed and confirmed before they can be compared.",
            status_code=409,
        )

    comparisons = []
    for section_type in SECTION_TYPES:
        earlier = sections_a.get(section_type)
        later = sections_b.get(section_type)
        if earlier is None and later is None:
            continue
        diff = compare_section_text(
            earlier.section_text if earlier else "", later.section_text if later else ""
        )
        comparisons.append({
            "section_type": section_type,
            "earlier": {
                "text": earlier.section_text if earlier else "",
                "document_id": request.document_id_a,
                "page_number": earlier.page_number if earlier else None,
            },
            "later": {
                "text": later.section_text if later else "",
                "document_id": request.document_id_b,
                "page_number": later.page_number if later else None,
            },
            **diff,
        })

    return {"comparisons": comparisons}


IMAGING_TERM_PROMPT = """
Provide a brief, general, plain-language educational explanation of the
medical imaging term below. This is general education only — it is not
about any specific patient's results, and it must not diagnose or interpret
an individual's imaging.

Term: {term}
{modality_context}

Use only the approved evidence supplied below. If the evidence does not
clearly define this term, say so plainly rather than guessing.

APPROVED EVIDENCE
{evidence}
"""


@router.post("/terminology/explain")
async def explain_terminology(request: TerminologyRequest, user: User = Depends(require_user)) -> dict[str, Any]:
    term = request.term.strip()
    if not term:
        raise HTTPException(status_code=422, detail="A term is required.")

    evidence = retrieve_approved_evidence(term, top_k=5)

    if not evidence:
        return {
            "term": term,
            "answer_markdown": (
                "MediGuide could not find enough approved educational information "
                "to explain this term."
            ),
            "sources": [],
        }

    sources = []
    source_lines = []
    for index, item in enumerate(evidence, 1):
        sources.append({
            "citation_number": index,
            "title": item.get("title", "Untitled source"),
            "publisher": item.get("publisher", "Unknown publisher"),
            "source_url": item.get("source_url", ""),
            "passage": item.get("passage", ""),
        })
        source_lines.append(f"[{index}] {item.get('title', '')} — {item.get('passage', '')}")

    modality_context = (
        f"Context: this term appears in a {MODALITY_LABELS.get(request.modality, request.modality)} report."
        if request.modality
        else ""
    )
    prompt = IMAGING_TERM_PROMPT.format(
        term=term, modality_context=modality_context, evidence="\n".join(source_lines)
    )

    try:
        from ollama import Client

        client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
        response = client.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "General educational information only. Use only the supplied approved evidence.",
                },
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        answer = response.message.content.strip()
    except Exception:
        answer = "The educational explanation model is unavailable on this deployment."

    return {"term": term, "answer_markdown": answer, "sources": sources}


def probe_imaging_documents() -> tuple[bool, str]:
    db_ok, db_detail = probe_database()
    if not db_ok:
        return False, db_detail
    try:
        with session_scope() as session:
            modality_summary(session, None)
        return True, "Imaging studies reachable"
    except Exception as error:
        return False, f"Unreadable ({type(error).__name__})"


def probe_imaging_viewer() -> tuple[bool, str]:
    try:
        import pymupdf  # noqa: F401

        return True, "Report page preview rendering available"
    except Exception as error:
        return False, f"Unavailable ({type(error).__name__})"
