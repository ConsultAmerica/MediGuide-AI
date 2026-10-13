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
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    upsert_findings_from_sections,
    upsert_report_sections,
)
from src.auth.dependencies import not_found, require_user
from src.database.models import ProcessingJob, User
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
from src.imaging_sections import SECTION_TYPES, split_report_sections
from src.observability.logging import get_logger
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
MAX_MB = int(os.getenv("IMAGING_MAX_MB", "20"))
MAX_PAGES = int(os.getenv("IMAGING_MAX_PAGES", "25"))
RENDER_DPI = int(os.getenv("IMAGING_RENDER_DPI", "140"))
PROCESSOR_VERSION = "imaging-sections-v1"


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


def _render_pages_and_native_text(
    pdf_path: Path, pages_dir: Path
) -> tuple[list[tuple[int, str]], int]:
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as error:
        raise PermanentProcessingError(
            "Invalid report PDF.", technical_detail=f"{type(error).__name__}: {error}"
        ) from error

    try:
        if doc.page_count < 1:
            raise PermanentProcessingError("Report PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise PermanentProcessingError(f"Maximum {MAX_PAGES} pages.")

        pages_dir.mkdir(parents=True, exist_ok=True)
        results: list[tuple[int, str]] = []
        for index, page in enumerate(doc):
            page_number = index + 1
            text = page.get_text("text", sort=True).strip()
            preview = pages_dir / f"page-{page_number}.png"
            page.get_pixmap(dpi=RENDER_DPI, alpha=False).save(str(preview))
            results.append((page_number, text))
        return results, doc.page_count
    finally:
        doc.close()


async def _save_report_upload(file: UploadFile, document_id: str, suffix: str) -> Path:
    folder = TEMP_DIR / document_id
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
    study_id: str, file: UploadFile = File(...), user: User = Depends(require_user)
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
    folder = TEMP_DIR / document_id
    pages_dir = folder / "pages"

    try:
        saved_path = await _save_report_upload(file, document_id, suffix)
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

        if suffix == ".pdf":
            page_texts, page_count = _render_pages_and_native_text(saved_path, pages_dir)
        else:
            validation = validate_image_file(str(saved_path))
            if not validation.valid or not validation.path:
                raise PermanentProcessingError(validation.error or "Invalid image.")
            pages_dir.mkdir(parents=True, exist_ok=True)
            preview = pages_dir / "page-1.png"
            with Image.open(validation.path) as image:
                image.convert("RGB").save(preview, format="PNG")
            page_texts = [(1, "")]
            page_count = 1

        set_stage("extracting")
        collected: dict[str, str] = {}
        source_page = 1
        last_permanent: PermanentProcessingError | None = None
        for page_number, text in page_texts:
            native_sections = split_report_sections(text)
            if native_sections:
                for key, value in native_sections.items():
                    collected.setdefault(key, value)
                source_page = page_number
                continue

            preview_path = pages_dir / f"page-{page_number}.png"
            try:
                vision_sections = _extract_sections_via_vision(preview_path, set_stage)
            except PermanentProcessingError as error:
                # Keep going for multi-page PDFs that already have some text,
                # but never silently save an empty report for photo uploads.
                last_permanent = error
                vision_sections = {}
            if vision_sections:
                for key, value in vision_sections.items():
                    collected.setdefault(key, value)
                source_page = page_number

        if not collected:
            if last_permanent is not None:
                raise last_permanent
            raise PermanentProcessingError(
                "No report text could be read from this file. Upload a "
                "text-based PDF, or a clear photo of the written radiology report.",
            )

        set_stage("saving")
        with session_scope() as session:
            for page_number, text in page_texts:
                add_document_page(
                    session,
                    document_id=document_id,
                    page_number=page_number,
                    preview_path=f"/api/imaging/studies/{study_id}/report/pages/{page_number}/preview",
                    text_available=bool(text),
                )
            set_document_page_count(session, document_id, page_count)
            section_rows = upsert_report_sections(
                session,
                study_id=study_id,
                document_id=document_id,
                sections=collected,
                page_number=source_page,
                extractor_version=PROCESSOR_VERSION,
            )
            upsert_findings_from_sections(
                session,
                study_id=study_id,
                document_id=document_id,
                sections=section_rows,
            )
            set_study_report_document(session, study_id, document_id)

        return collected

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

    path = TEMP_DIR / document_id / "pages" / f"page-{page_number}.png"
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
