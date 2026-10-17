from collections.abc import Iterator
from typing import Any

from ollama import Client

from src.chatbot import (
    SAFETY_REMINDER,
    format_history,
)
from src.citations import (
    CitationSource,
    build_citation_sources,
    build_source_number_map,
    find_citation_numbers,
    format_evidence_context,
    format_source_list,
    validate_citation_numbers,
)
from src.config import (
    MODEL_NAME,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT_SECONDS,
    RAG_MAX_OUTPUT_TOKENS,
    RAG_MAX_PASSAGE_WORDS,
    TEMPERATURE,
)
from src.observability.logging import get_logger
from src.prompts import RAG_MEDICAL_SYSTEM_PROMPT
from src.schemas import RetrievedChunk
from src.retriever import (
    diversify_results,
    retrieve_chunks,
)
from src.safety import check_for_emergency
from src.validator import validate_response


ANSWER_DETAIL_INSTRUCTIONS = {
    "Concise": (
        "Answer briefly: one to two sentences per section. Omit any "
        "section that would only restate a point already made."
    ),
    "Detailed": (
        "Provide thorough detail in each section, including relevant "
        "nuances, and note any caveats present in the evidence."
    ),
}

logger = get_logger(__name__)

# Technical detail is logged, never shown (see src/shared/errors.py).
SEARCH_FAILED_MESSAGE = (
    "MediGuide could not search the approved knowledge base right now. "
    "Please try again in a moment."
)
GENERATION_FAILED_MESSAGE = (
    "The evidence was found, but MediGuide could not write the answer "
    "right now. Please try again in a moment."
)

# Where no text model is reachable (the Vercel deployment), chat still
# answers by quoting the best-matching approved passages, labelled as
# quotes. Nothing is generated, so nothing needs model validation.
SOURCES_ONLY_EXCERPTS = 3
SOURCES_ONLY_NOTE = (
    "## About this answer\n"
    "AI writing is switched off on this version of MediGuide, so these "
    "are passages quoted from approved sources, not a written answer. "
    "They may not cover your exact question. Ask a qualified healthcare "
    "professional about your own situation."
)


def text_model_ready() -> bool:
    """True when Ollama answers and has the chat model pulled."""
    from src.shared.ollama_health import probe_ollama

    reachable, _detail, installed = probe_ollama()
    wanted = MODEL_NAME if ":" in MODEL_NAME else f"{MODEL_NAME}:latest"
    return reachable and (wanted in installed or MODEL_NAME in installed)


def _sources_only_answer(
    query: str,
    retrieved: list[RetrievedChunk],
) -> tuple[str, list[CitationSource]]:
    from src.lexical_search import best_passage

    chosen: list[RetrievedChunk] = []
    seen: set[str] = set()
    for chunk in retrieved:
        source_id = str(chunk.metadata.get("source_id", chunk.chunk_id))
        if source_id in seen:
            continue
        seen.add(source_id)
        chosen.append(chunk)
        if len(chosen) == SOURCES_ONLY_EXCERPTS:
            break

    sources = build_citation_sources(chosen)
    numbers = build_source_number_map(sources)
    excerpts = [
        f"“{best_passage(chunk.text, query)}” "
        f"[{numbers[str(chunk.metadata.get('source_id', chunk.chunk_id))]}]"
        for chunk in chosen
    ]
    answer = (
        "## What approved sources say\n"
        + "\n\n".join(excerpts)
        + f"\n\n{SOURCES_ONLY_NOTE}\n\n---\n"
        + f"{format_source_list(sources)}\n\n---\n{SAFETY_REMINDER}"
    )
    return answer, sources


READING_LEVEL_INSTRUCTIONS = {
    "Plain": (
        "Use plain, everyday language at roughly a sixth-grade reading "
        "level. Avoid medical jargon; when a medical term is necessary, "
        "briefly define it in parentheses the first time it appears."
    ),
}


def _prepare_generation(
    user_message: str,
    history: list[dict[str, Any]] | None,
    *,
    answer_detail: str = "Standard",
    reading_level: str = "Standard",
) -> tuple[str, list[dict[str, Any]] | None, list[CitationSource] | None]:
    """Runs the pre-generation pipeline.

    Returns ("early", answer, None) if a final answer can already be
    given without calling the model, ("sources", answer, sources) when
    no model is reachable and the answer is quoted approved passages,
    otherwise ("ready", messages, sources).
    """
    if not user_message or not user_message.strip():
        return "early", "Please enter a health-education question.", None

    clean_message = user_message.strip()

    emergency = check_for_emergency(clean_message)

    if emergency.is_emergency:
        return (
            "early",
            emergency.message or "Call emergency services immediately.",
            None,
        )

    try:
        retrieved = retrieve_chunks(clean_message)
        retrieved = diversify_results(retrieved)
    except Exception:
        logger.exception("approved-source retrieval failed")
        return "early", SEARCH_FAILED_MESSAGE, None

    if not retrieved:
        return (
            "early",
            "Limited trusted information available\n\n"
            "MediGuide couldn’t find enough approved source material "
            "to answer this question confidently.\n\n"
            "Try:\n"
            "• Asking a more specific question\n"
            "• Reviewing one of the available topics\n"
            "• Adding a trusted source to the knowledge base\n\n"
            "Supported demo topics include blood pressure, cholesterol, "
            "diabetes, CBC lab tests, medication labels, antibiotics, "
            "fever, allergies, and appointment preparation.\n\n"
            "---\n"
            f"{SAFETY_REMINDER}",
            None,
        )

    if not text_model_ready():
        answer, quoted = _sources_only_answer(clean_message, retrieved)
        return "sources", answer, quoted

    sources = build_citation_sources(retrieved)
    source_map = build_source_number_map(sources)

    evidence_context = format_evidence_context(
        retrieved,
        source_map,
        max_words_per_passage=RAG_MAX_PASSAGE_WORDS,
    )

    valid_source_numbers = sorted(
        source.number for source in sources
    )

    style_instructions = " ".join(
        instruction
        for instruction in (
            ANSWER_DETAIL_INSTRUCTIONS.get(answer_detail),
            READING_LEVEL_INSTRUCTIONS.get(reading_level),
        )
        if instruction
    )

    user_prompt = f"""
USER QUESTION

{clean_message}

APPROVED EVIDENCE

{evidence_context}

The only valid citation numbers for this answer are:
{valid_source_numbers}

Write a patient-education answer using only this evidence.

Use these exact headings in order:
## General explanation
## What this means
## What MediGuide cannot determine
## Questions to ask a healthcare professional
## When to seek professional care

Cite factual statements with valid numbers such as
[{valid_source_numbers[0]}]. Do not invent citations. Do not write a
Sources section. Keep sections short — not one large paragraph. If the
evidence cannot fully answer the question, say what remains unknown in
"What MediGuide cannot determine".{(" " + style_instructions) if style_instructions else ""}
"""

    messages = [
        {
            "role": "system",
            "content": RAG_MEDICAL_SYSTEM_PROMPT,
        },
        *format_history(history),
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    return "ready", messages, sources


def _finalize(
    answer: str,
    sources: list[CitationSource],
) -> tuple[str, str]:
    """Validates a draft answer.

    Returns ``(text, status)`` where status is ``"answered"`` when the
    draft passed every check, or ``"withheld"`` when it was replaced by
    an explanation of why it could not be shown.
    """
    valid_numbers = {
        source.number
        for source in sources
    }

    citations_valid, invalid_numbers = (
        validate_citation_numbers(
            answer,
            valid_numbers,
        )
    )

    if not citations_valid:
        return (
            "The model generated an invalid citation reference. "
            "The answer was withheld to prevent unsupported sourcing.",
            "withheld",
        )

    used_citations = find_citation_numbers(answer)

    if not used_citations:
        return (
            "The response did not include evidence citations, so it was "
            "withheld. Please try the question again.",
            "withheld",
        )

    validation = validate_response(answer)

    if not validation.is_valid:
        return (
            "The generated response failed the medical-safety check. "
            "Please rephrase the question or consult a qualified "
            "healthcare professional.",
            "withheld",
        )

    source_list = format_source_list(sources)

    return (
        f"{answer}\n\n"
        f"---\n"
        f"{source_list}\n\n"
        f"---\n"
        f"{SAFETY_REMINDER}",
        "answered",
    )


def _finalize_answer(
    answer: str,
    sources: list[CitationSource],
) -> str:
    return _finalize(answer, sources)[0]


def serialize_sources(
    sources: list[CitationSource] | None,
) -> list[dict[str, Any]]:
    """Converts citation sources into JSON-ready dictionaries."""
    return [
        {
            "number": source.number,
            "title": source.title,
            "publisher": source.publisher,
            "published": source.publication_date,
            "reviewed": source.review_date,
            "url": source.source_url,
        }
        for source in sources or []
    ]


def stream_rag_response(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    *,
    answer_detail: str = "Standard",
    reading_level: str = "Standard",
) -> Iterator[str]:
    """Yields the answer as it is generated.

    Every yielded value before the last one is an unvalidated draft of
    the model's output, shown only so the wait does not feel frozen.
    The final yielded value is always the fully validated answer (or a
    withheld/error message), exactly as ``generate_rag_response``
    would return.
    """
    stage, payload, sources = _prepare_generation(
        user_message,
        history,
        answer_detail=answer_detail,
        reading_level=reading_level,
    )

    if stage in ("early", "sources"):
        yield payload
        return

    messages = payload
    client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
    accumulated = ""

    try:
        for chunk in client.chat(
            model=MODEL_NAME,
            messages=messages,
            options={
                "temperature": TEMPERATURE,
                "num_predict": RAG_MAX_OUTPUT_TOKENS,
            },
            stream=True,
        ):
            piece = chunk.message.content or ""

            if not piece:
                continue

            accumulated += piece
            yield accumulated

    except Exception:
        logger.exception("answer generation failed")
        yield GENERATION_FAILED_MESSAGE
        return

    yield _finalize_answer(accumulated.strip(), sources)


def stream_rag_events(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    *,
    answer_detail: str = "Standard",
    reading_level: str = "Standard",
) -> Iterator[dict[str, Any]]:
    """Yields structured events describing the answer as it is built.

    Event shapes:

    ``{"type": "stage", "stage": str}``
        A pipeline step the caller can surface while waiting.
    ``{"type": "sources", "sources": list}``
        The approved sources backing the answer, known before the model
        starts writing so citations can be resolved as they stream in.
    ``{"type": "delta", "text": str}``
        The next fragment of the unvalidated draft.
    ``{"type": "done", "answer": str, "sources": list, "status": str}``
        The validated answer. ``status`` is ``"answered"``,
        ``"withheld"``, ``"emergency"``, ``"no_evidence"``, ``"error"``
        or ``"sources_only"`` (quoted passages; no model was available).
        The answer always replaces any streamed draft.
    """
    yield {"type": "stage", "stage": "Checking safety"}

    if user_message and user_message.strip():
        emergency = check_for_emergency(user_message.strip())

        if emergency.is_emergency:
            message = (
                emergency.message
                or "Call emergency services immediately."
            )
            yield {
                "type": "done",
                "answer": message,
                "sources": [],
                "status": "emergency",
            }
            return

    yield {"type": "stage", "stage": "Searching approved sources"}

    stage, payload, sources = _prepare_generation(
        user_message,
        history,
        answer_detail=answer_detail,
        reading_level=reading_level,
    )

    if stage == "early":
        status = (
            "no_evidence"
            if "Limited trusted information" in payload
            else "error"
        )
        yield {
            "type": "done",
            "answer": payload,
            "sources": [],
            "status": status,
        }
        return

    serialized = serialize_sources(sources)
    yield {"type": "sources", "sources": serialized}

    if stage == "sources":
        yield {
            "type": "done",
            "answer": payload,
            "sources": serialized,
            "status": "sources_only",
        }
        return

    yield {"type": "stage", "stage": "Writing a cited answer"}

    messages = payload
    client = Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)
    accumulated = ""

    try:
        for chunk in client.chat(
            model=MODEL_NAME,
            messages=messages,
            options={
                "temperature": TEMPERATURE,
                "num_predict": RAG_MAX_OUTPUT_TOKENS,
            },
            stream=True,
        ):
            piece = chunk.message.content or ""

            if not piece:
                continue

            accumulated += piece
            yield {"type": "delta", "text": piece}

    except Exception:
        logger.exception("answer generation failed")
        yield {
            "type": "done",
            "answer": GENERATION_FAILED_MESSAGE,
            "sources": serialized,
            "status": "error",
        }
        return

    yield {"type": "stage", "stage": "Validating citations"}

    answer, status = _finalize(accumulated.strip(), sources)

    yield {
        "type": "done",
        "answer": answer,
        "sources": serialized if status == "answered" else [],
        "status": status,
    }


def generate_rag_response(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    *,
    answer_detail: str = "Standard",
    reading_level: str = "Standard",
) -> str:
    answer = "Please enter a health-education question."

    for answer in stream_rag_response(
        user_message,
        history,
        answer_detail=answer_detail,
        reading_level=reading_level,
    ):
        pass

    return answer
