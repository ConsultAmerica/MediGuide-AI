"""FastAPI adapter for the MediGuide local AI services."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.agents import MedicalAgentOrchestrator, OrchestratorRequest
from src.api.labs import router as labs_router
from src.auth.router import router as auth_router
from src.config import (
    BASE_DIR,
    CHROMA_COLLECTION_NAME,
    EMBEDDING_MODEL_NAME,
    KNOWLEDGE_DIR,
    MAX_AUDIO_MB,
    MAX_IMAGE_MB,
    MAX_TTS_CHARACTERS,
    MODEL_NAME,
    OLLAMA_HOST,
    PIPER_EXECUTABLE,
    SPEECH_OUTPUT_DIR,
    TRANSLATION_MODEL_NAME,
    VECTOR_STORE_DIR,
    VISION_MODEL_NAME,
    WHISPER_MODEL_SIZE,
)
from src.database.repository import stuck_job_count
from src.database.session import init_db, probe_database, session_scope
from src.document_intelligence import router as document_intelligence_router
from src.document_loader import load_metadata
from src.health_timeline import probe_timeline
from src.health_timeline import router as health_timeline_router
from src.search import router as search_router
from src.imaging import probe_imaging_documents, probe_imaging_viewer
from src.imaging import router as imaging_router
from src.medication_workspace import router as medication_workspace_router
from src.observability.logging import (
    configure_logging,
    get_logger,
    new_request_id,
    set_request_id,
)
from src.shared import file_store
from src.shared.errors import install_error_handlers
from src.tts import TextToSpeechError

OLLAMA_PROBE_TIMEOUT = float(os.getenv("OLLAMA_PROBE_TIMEOUT", "2.5"))
UPLOAD_CHUNK_BYTES = 1024 * 1024

AUDIO_SUFFIXES = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".oga", ".flac", ".mp4"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

ANSWER_DETAIL_CHOICES = {"Concise", "Standard", "Detailed"}
READING_LEVEL_CHOICES = {"Plain", "Standard"}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)
    answer_detail: str = "Standard"
    reading_level: str = "Standard"

    def normalized_detail(self) -> str:
        return self.answer_detail if self.answer_detail in ANSWER_DETAIL_CHOICES else "Standard"

    def normalized_level(self) -> str:
        return self.reading_level if self.reading_level in READING_LEVEL_CHOICES else "Standard"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    language: str = Field(min_length=2, max_length=32)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TTS_CHARACTERS)
    language: str = "en"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


app = FastAPI(title="MediGuide AI API", version="1.2.0")

# These routers already declare their own prefixes — no extra prefix
# here, or every route (including served page/preview files) breaks.
app.include_router(auth_router)
app.include_router(document_intelligence_router)
app.include_router(medication_workspace_router)
app.include_router(labs_router)
app.include_router(imaging_router)
app.include_router(health_timeline_router)
app.include_router(search_router)

install_error_handlers(app)

logger = get_logger(__name__)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "").strip()
    request_id = incoming or new_request_id()
    set_request_id(request_id)
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        "request_completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.middleware("http")
async def _file_store_middleware(request: Request, call_next):
    """With durable storage enabled (serverless hosting), push every record
    folder this request touched before the response leaves: the instance may
    be frozen as soon as it does. A failed save is reported, never hidden."""
    token = file_store.begin_request()
    if token is None:
        return await call_next(request)
    try:
        response = await call_next(request)
        try:
            await asyncio.to_thread(file_store.persist_touched)
        except Exception:  # noqa: BLE001 — logged in file_store
            return JSONResponse(
                status_code=503,
                content={"detail": "Your changes couldn't be saved to storage. Please try again."},
            )
        return response
    finally:
        file_store.end_request(token)


# Production frontend (Vercel) + local Next.js. FRONTEND_ORIGINS can extend the
# list. Registered *after* _request_id_middleware (a BaseHTTPMiddleware) so it
# ends up outermost — Starlette applies the most-recently-added middleware
# first, and a BaseHTTPMiddleware whose call_next() raises (which it does
# whenever the wrapped app errors, even after an @app.exception_handler has
# already converted that error into a response) loses whatever headers an
# *inner* CORSMiddleware would have added, so the browser sees a CORS-blocked
# "Failed to fetch" instead of the real error response. Outermost avoids that.
_DEFAULT_ORIGINS = [
    "https://mediguide-ai-woad.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://medi.naziaasif1412.workers.dev",
    "https://frontend.naziaasif1412.workers.dev",
]
_env_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
_allow_origins = list(dict.fromkeys([*_DEFAULT_ORIGINS, *_env_origins]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_origin_regex=r"https://.*\.(workers\.dev|pages\.dev|vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, object]:
    """Avoid a bare JSON 404 when someone opens the API URL in a browser."""
    return {
        "service": "mediguide-api",
        "status": "ok",
        "message": "MediGuide AI API. Use /api/health for readiness.",
        "health": "/api/health",
        "system": "/api/system/status",
        "docs": "/docs",
    }


@app.on_event("startup")
def _startup() -> None:
    configure_logging()
    try:
        init_db()
    except Exception as error:
        # API remains usable for document upload even if the relational store
        # is offline — but logged, not silent, so a genuinely broken DB (e.g.
        # an unwritable data directory) shows up immediately instead of
        # surfacing later as confusing per-request "no such table" errors.
        logger.error(
            "database_init_failed",
            extra={"technical_detail": f"{type(error).__name__}: {error}"},
            exc_info=error,
        )


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------


async def _store_upload(
    file: UploadFile,
    *,
    max_mb: int,
    allowed_suffixes: set[str],
    fallback_name: str,
) -> Path:
    """Streams an upload to a temp file, rejecting oversized or unknown types.

    Reading in chunks keeps a large upload from being held in memory in
    full, and lets the request be refused as soon as the cap is passed.
    """
    suffix = Path(file.filename or fallback_name).suffix.lower()

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{suffix or 'unknown'}'. "
                f"Accepted: {', '.join(sorted(allowed_suffixes))}."
            ),
        )

    max_bytes = max_mb * 1024 * 1024
    temp_path = Path(tempfile.gettempdir()) / f"mediguide-{uuid.uuid4().hex}{suffix}"
    written = 0

    try:
        with temp_path.open("wb") as target:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)

                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is larger than the {max_mb} MB limit.",
                    )

                target.write(chunk)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    if not written:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="The uploaded file was empty.")

    return temp_path


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------


def _health_status(available: bool, detail: str = "") -> dict[str, str]:
    return {"status": "ready" if available else "unavailable", "detail": detail}


def _probe_ollama() -> tuple[bool, str, set[str]]:
    """Asks Ollama which models it actually has, rather than trusting config."""
    from src.shared.ollama_health import probe_ollama

    return probe_ollama(timeout=OLLAMA_PROBE_TIMEOUT)


def _model_status(model: str, installed: set[str], reachable: bool) -> dict[str, str]:
    if not model:
        return _health_status(False, "No model configured")

    if not reachable:
        return _health_status(False, f"{model} · Ollama unreachable")

    wanted = model if ":" in model else f"{model}:latest"

    if wanted in installed or model in installed:
        return _health_status(True, model)

    return _health_status(False, f"{model} · not pulled (ollama pull {model})")


def _probe_vector_store() -> dict[str, str]:
    if not VECTOR_STORE_DIR.exists():
        return _health_status(False, "No vector store — run ingest_knowledge.py")

    try:
        from src.vector_store import get_chroma_collection

        count = get_chroma_collection().count()
    except Exception as error:
        return _health_status(False, f"Unreadable ({type(error).__name__})")

    if not count:
        return _health_status(
            False, f"'{CHROMA_COLLECTION_NAME}' is empty — run ingest_knowledge.py"
        )

    return _health_status(True, f"{count} approved passages indexed")


def _probe_document_processing() -> dict[str, str]:
    try:
        import pymupdf  # noqa: F401

        return _health_status(True, "PyMuPDF native-text extraction available")
    except Exception as error:
        return _health_status(False, f"Unavailable ({type(error).__name__})")


PROCESSING_JOB_STALE_SECONDS = int(os.getenv("PROCESSING_JOB_STALE_SECONDS", "300"))


def _probe_processing_jobs(db_ok: bool) -> dict[str, str]:
    if not db_ok:
        return _health_status(False, "Job tracking needs the database")
    try:
        with session_scope() as session:
            stuck = stuck_job_count(session, stale_after_seconds=PROCESSING_JOB_STALE_SECONDS)
    except Exception as error:
        return _health_status(False, f"Unreadable ({type(error).__name__})")

    if stuck:
        return _health_status(
            False, f"{stuck} job(s) stuck in 'running' past {PROCESSING_JOB_STALE_SECONDS}s"
        )
    return _health_status(True, "No stuck processing jobs")


def _probe_imaging_documents() -> dict[str, str]:
    ok, detail = probe_imaging_documents()
    return _health_status(ok, detail)


def _probe_imaging_viewer() -> dict[str, str]:
    ok, detail = probe_imaging_viewer()
    return _health_status(ok, detail)


def _composite_ai_capability_status(
    *, storage_ok: bool, storage_detail: str, ai_ready: bool
) -> dict[str, str]:
    """Health isolation for an AI-dependent capability: storage/DB being
    down is a real outage (unavailable); Ollama alone being down only
    limits that one capability (degraded — the frontend renders this as
    "Limited", see friendlyComponentStatus in polish-ui.tsx) rather than
    marking the whole feature, or the whole app, unavailable."""
    if not storage_ok:
        return _health_status(False, storage_detail)
    if not ai_ready:
        return {"status": "degraded", "detail": "AI extraction unavailable — Ollama unreachable"}
    return _health_status(True, "Ready")


def _probe_medication_labels(reachable: bool, installed: set[str]) -> dict[str, str]:
    vision_ready = reachable and (
        VISION_MODEL_NAME in installed or f"{VISION_MODEL_NAME}:latest" in installed
    )
    # No dedicated storage layer of its own (see MedicationRecord's
    # docstring) — the database itself is the only non-Ollama dependency.
    db_ok, db_detail = probe_database()
    return _composite_ai_capability_status(
        storage_ok=db_ok, storage_detail=db_detail, ai_ready=vision_ready
    )


def _probe_imaging_reports(reachable: bool, installed: set[str]) -> dict[str, str]:
    vision_ready = reachable and (
        VISION_MODEL_NAME in installed or f"{VISION_MODEL_NAME}:latest" in installed
    )
    storage_ok, storage_detail = probe_imaging_documents()
    return _composite_ai_capability_status(
        storage_ok=storage_ok, storage_detail=storage_detail, ai_ready=vision_ready
    )


def _probe_timeline() -> dict[str, str]:
    ok, detail = probe_timeline()
    return _health_status(ok, detail)


def _probe_demo_data() -> dict[str, str]:
    """The /sample/lab-report endpoint regenerates this file on demand if
    missing, so this reports a shipped-fixture packaging problem for
    visibility — it does not mean "Try synthetic data" is actually broken."""
    sample_path = BASE_DIR / "data" / "samples" / "sample-lab-report.pdf"
    if sample_path.exists():
        return _health_status(True, "Synthetic lab report fixture present")
    return _health_status(
        True, "Fixture not shipped — will be generated on first demo request"
    )


@app.get("/api/health")
def health() -> dict[str, object]:
    """Render-safe health: API + document processing stay up without Ollama."""
    reachable, ollama_detail, installed = _probe_ollama()
    piper_ready = bool(shutil.which(str(PIPER_EXECUTABLE)) or PIPER_EXECUTABLE.exists())
    whisper_ready = importlib.util.find_spec("faster_whisper") is not None
    db_ok, db_detail = probe_database()
    document_processing = _probe_document_processing()

    statuses = {
        "fastapi": _health_status(True, "API is responding"),
        "document_processing": document_processing,
        "processing_jobs": _probe_processing_jobs(db_ok),
        "imaging_documents": _probe_imaging_documents(),
        "imaging_viewer": _probe_imaging_viewer(),
        "imaging_reports": _probe_imaging_reports(reachable, installed),
        "medication_labels": _probe_medication_labels(reachable, installed),
        "timeline": _probe_timeline(),
        "demo_data": _probe_demo_data(),
        "ollama": _health_status(reachable, ollama_detail),
        "text_model": _model_status(MODEL_NAME, installed, reachable),
        "vision_model": _model_status(VISION_MODEL_NAME, installed, reachable),
        "embedding_model": _model_status(EMBEDDING_MODEL_NAME, installed, reachable),
        "vector_store": _probe_vector_store(),
        "database": _health_status(db_ok, db_detail),
        "whisper": _health_status(
            whisper_ready,
            f"{WHISPER_MODEL_SIZE} model" if whisper_ready else "faster-whisper not installed",
        ),
        "piper": _health_status(
            piper_ready,
            "Speech executable" if piper_ready else "Install Piper for spoken responses",
        ),
        "translation_model": _model_status(TRANSLATION_MODEL_NAME, installed, reachable),
    }
    ready = sum(item["status"] == "ready" for item in statuses.values())

    # Flagship Health Document Intelligence path does not require Ollama.
    essential = ("fastapi", "document_processing", "database")
    core_ok = all(statuses[key]["status"] == "ready" for key in essential)

    knowledge_count = 0
    try:
        from src.vector_store import get_chroma_collection

        knowledge_count = get_chroma_collection().count()
    except Exception:
        knowledge_count = 0

    approved_sources = 0
    if KNOWLEDGE_DIR.exists():
        approved_sources = len(list(KNOWLEDGE_DIR.glob("*.json")))

    return {
        "status": "ok" if core_ok else "degraded",
        "service": "mediguide-api",
        "api": "healthy" if statuses["fastapi"]["status"] == "ready" else "unavailable",
        "document_processing": (
            "available" if document_processing["status"] == "ready" else "unavailable"
        ),
        "ollama": "available" if reachable else "unavailable",
        "whisper": "available" if whisper_ready else "unavailable",
        "tts": "available" if piper_ready else "unavailable",
        "ready": ready,
        "total": len(statuses),
        "statuses": statuses,
        "knowledge": {
            "active_chunks": knowledge_count,
            "approved_sources": approved_sources,
        },
    }


@app.get("/api/system/status")
def system_status() -> dict[str, object]:
    """Portfolio-friendly system page payload without secrets or paths."""
    payload = health()
    statuses = payload["statuses"]
    assert isinstance(statuses, dict)
    return {
        "service": "MediGuide System",
        "overall": payload["status"],
        "components": [
            {"name": "API", "key": "fastapi", **statuses["fastapi"]},
            {
                "name": "Document processing",
                "key": "document_processing",
                **statuses["document_processing"],
            },
            {
                "name": "Imaging documents",
                "key": "imaging_documents",
                **statuses["imaging_documents"],
            },
            {
                "name": "Imaging viewer",
                "key": "imaging_viewer",
                **statuses["imaging_viewer"],
            },
            {
                "name": "Imaging reports",
                "key": "imaging_reports",
                **statuses["imaging_reports"],
            },
            {
                "name": "Medication labels",
                "key": "medication_labels",
                **statuses["medication_labels"],
            },
            {
                "name": "Health Timeline",
                "key": "timeline",
                **statuses["timeline"],
            },
            {
                "name": "Processing jobs",
                "key": "processing_jobs",
                **statuses["processing_jobs"],
            },
            {"name": "Demo data", "key": "demo_data", **statuses["demo_data"]},
            {"name": "Ollama", "key": "ollama", **statuses["ollama"]},
            {"name": "Text model", "key": "text_model", **statuses["text_model"]},
            {"name": "Vision model", "key": "vision_model", **statuses["vision_model"]},
            {"name": "Whisper", "key": "whisper", **statuses["whisper"]},
            {"name": "Embedding model", "key": "embedding_model", **statuses["embedding_model"]},
            {"name": "ChromaDB", "key": "vector_store", **statuses["vector_store"]},
            {"name": "Database", "key": "database", **statuses["database"]},
            {"name": "Piper", "key": "piper", **statuses["piper"]},
            {
                "name": "n8n",
                "key": "n8n",
                # Nothing in the API calls n8n; the n8n/ folder only holds
                # example workflow exports. Reporting it "ready" was false.
                "status": "unavailable",
                "detail": "Not connected in this deployment (optional)",
            },
        ],
        "knowledge": payload.get("knowledge", {}),
    }


class OrchestrateRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    intent_hint: str | None = None
    conversation_id: str | None = None
    document_id: str | None = None


@app.post("/api/orchestrate")
async def orchestrate(request: OrchestrateRequest) -> dict[str, object]:
    orchestrator = MedicalAgentOrchestrator()
    hint = request.intent_hint if request.intent_hint in {
        "education",
        "document",
        "lab_timeline",
        "visit_preparation",
        "medication",
    } else None
    result = await orchestrator.process(
        OrchestratorRequest(
            message=request.message,
            intent_hint=hint,  # type: ignore[arg-type]
            conversation_id=request.conversation_id,
            document_id=request.document_id,
        )
    )
    return result



# --------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------


@app.get("/api/knowledge")
def knowledge() -> dict[str, object]:
    """Lists the approved sources the assistant is allowed to draw on."""
    entries: list[dict[str, str]] = []

    for metadata_path in sorted(KNOWLEDGE_DIR.glob("*.json")):
        try:
            metadata = load_metadata(metadata_path)
        except Exception:
            continue

        if not metadata.get("approved") or metadata.get("status", "active") != "active":
            continue

        entries.append(
            {
                "id": str(metadata.get("source_id", metadata_path.stem)),
                "title": str(metadata.get("title", metadata_path.stem)),
                "publisher": str(metadata.get("publisher", "")),
                "url": str(metadata.get("source_url", "")),
                "published": str(metadata.get("publication_date", "")),
                "reviewed": str(metadata.get("review_date", "")),
                "type": str(metadata.get("document_type", "patient_education")),
            }
        )

    return {"count": len(entries), "sources": entries}


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    try:
        from src.rag_chatbot import stream_rag_events
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Chat is unavailable on this deployment: {type(error).__name__}",
        ) from error

    answer = "MediGuide could not produce an answer."
    sources: list[dict[str, object]] = []
    status = "error"

    try:
        for event in stream_rag_events(
            request.message,
            request.history,
            answer_detail=request.normalized_detail(),
            reading_level=request.normalized_level(),
        ):
            if event["type"] == "done":
                answer, sources, status = (
                    event["answer"],
                    event["sources"],
                    event["status"],
                )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"The local AI service failed: {type(error).__name__}: {error}",
        ) from error

    return {"answer": answer, "sources": sources, "status": status}


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _chat_events(request: ChatRequest) -> Iterator[str]:
    try:
        from src.rag_chatbot import stream_rag_events

        for event in stream_rag_events(
            request.message,
            request.history,
            answer_detail=request.normalized_detail(),
            reading_level=request.normalized_level(),
        ):
            yield _sse(event)
    except Exception as error:
        yield _sse(
            {
                "type": "done",
                "answer": (
                    "MediGuide could not complete this answer.\n\n"
                    f"Technical detail: {type(error).__name__}: {error}"
                ),
                "sources": [],
                "status": "error",
            }
        )

    yield "data: [DONE]\n\n"


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Server-sent events carrying the answer as the model writes it.

    Only the final ``done`` event has passed citation and safety
    validation; everything before it is a draft shown so the wait is
    visible rather than blank.
    """
    return StreamingResponse(
        _chat_events(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------
# Voice, documents, translation, speech
# --------------------------------------------------------------------------


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        from src.transcriber import transcribe_audio
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Transcription is unavailable on this deployment: {type(error).__name__}",
        ) from error

    temp_path = await _store_upload(
        file,
        max_mb=MAX_AUDIO_MB,
        allowed_suffixes=AUDIO_SUFFIXES,
        fallback_name="audio.webm",
    )
    try:
        result = await asyncio.to_thread(transcribe_audio, str(temp_path))

        if not result.success:
            raise HTTPException(status_code=422, detail=result.error)

        return {
            "text": result.text,
            "language": result.language,
            "language_probability": result.language_probability,
        }
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/documents/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    question: str = Form("Extract and organize only the clearly visible information."),
) -> dict[str, object]:
    try:
        from src.image_analyzer import analyze_medical_document_image
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Image analysis is unavailable on this deployment: {type(error).__name__}",
        ) from error

    temp_path = await _store_upload(
        file,
        max_mb=MAX_IMAGE_MB,
        allowed_suffixes=IMAGE_SUFFIXES,
        fallback_name="document.png",
    )
    try:
        result = await asyncio.to_thread(
            analyze_medical_document_image, str(temp_path), question
        )

        if not result.success:
            raise HTTPException(status_code=422, detail=result.error)

        return {"data": result.structured_data, "raw_text": result.raw_text}
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/translate")
def translate(request: TranslateRequest) -> dict[str, str]:
    try:
        from ollama import Client
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Translation is unavailable on this deployment: {type(error).__name__}",
        ) from error

    try:
        response = Client(host=OLLAMA_HOST).chat(
            model=TRANSLATION_MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "Translate accurately. Preserve headings, citations, and safety language. Return only the translation.",
                },
                {
                    "role": "user",
                    "content": f"Translate into {request.language}:\n\n{request.text}",
                },
            ],
            options={"temperature": 0.1},
        )
        return {"text": response.message.content.strip(), "language": request.language}
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Translation failed: {error}") from error


@app.post("/api/speak")
def speak(request: SpeakRequest) -> FileResponse:
    try:
        from src.tts import synthesize_speech
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Speech is unavailable on this deployment: {type(error).__name__}",
        ) from error

    try:
        output_path = synthesize_speech(
            request.text,
            language_code=request.language,
            length_scale=1.0 / request.speed,
        )
    except (TextToSpeechError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FileResponse(output_path, media_type="audio/wav", filename="mediguide-answer.wav")
