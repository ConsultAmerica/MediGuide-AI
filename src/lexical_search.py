"""Keyword (BM25) search over the approved knowledge base.

Used where the vector store can't run, such as the Vercel deployment,
which has neither chromadb nor an embedding model. It reads the same
approved documents and chunks them exactly as ``src.ingest`` does, so
citations point at the same sources either way.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.chunking import chunk_document
from src.config import KNOWLEDGE_DIR
from src.document_loader import load_source_document
from src.observability.logging import get_logger
from src.schemas import RetrievedChunk

logger = get_logger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt"}

# BM25 defaults.
K1 = 1.5
B = 0.75

# Title words count this many extra times, so a question about diabetes
# lands on the diabetes sources rather than a passage that mentions it.
TITLE_WEIGHT = 3

# A chunk must match the query this well to count as evidence, and be at
# least this fraction of the best match, so weak keyword overlaps (a
# shared "blood" or "test") don't pass as support.
MIN_SCORE = 1.0
MIN_RELATIVE_SCORE = 0.5

# Common English plus the field labels of the visit-prep summary, which
# would otherwise outweigh what the person actually wrote.
STOPWORDS = frozenset(
    """a about above after again all am an and any are as at be because been
    before being below between both but by can could did do does doing down
    during each few for from further had has have having he her here hers him
    his how i if in into is it its itself just me more most my no nor not now
    of off on once only or other our ours out over own same she should so some
    such than that the their them then there these they this those through to
    too under until up very was we were what when where which while who whom
    why will with would you your yours help me please tell explain mean means
    using these notes plain language simple simply words understand
    understanding question questions ask
    healthcare professional clinician patient provided prepare entered
    medications onset duration frequency severity triggers relieving factors
    concern symptoms mg""".split()
)

TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in TOKEN.findall(text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


@dataclass(frozen=True)
class _Index:
    chunks: tuple[RetrievedChunk, ...]
    term_counts: tuple[Counter, ...]
    lengths: tuple[int, ...]
    average_length: float
    document_frequency: dict[str, int]


@lru_cache(maxsize=1)
def _index(knowledge_dir: Path = KNOWLEDGE_DIR) -> _Index:
    chunks: list[RetrievedChunk] = []

    for path in sorted(knowledge_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            document = load_source_document(path)
        except Exception:
            # Unapproved or retired sources are refused here, as in ingest.
            logger.info("skipped knowledge document %s", path.name)
            continue
        for chunk in chunk_document(document):
            chunks.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    distance=0.0,
                    metadata=chunk.metadata,
                )
            )

    term_counts = []
    for chunk in chunks:
        counts = Counter(tokenize(chunk.text))
        for term in tokenize(str(chunk.metadata.get("title", ""))):
            counts[term] += TITLE_WEIGHT
        term_counts.append(counts)
    lengths = [sum(counts.values()) for counts in term_counts]
    frequency: Counter = Counter()
    for counts in term_counts:
        frequency.update(counts.keys())

    return _Index(
        chunks=tuple(chunks),
        term_counts=tuple(term_counts),
        lengths=tuple(lengths),
        average_length=(sum(lengths) / len(lengths)) if lengths else 0.0,
        document_frequency=dict(frequency),
    )


def chunk_count() -> int:
    return len(_index().chunks)


def search(query: str, top_k: int = 6) -> list[RetrievedChunk]:
    """Returns the best-matching approved chunks, or [] when nothing
    matches well enough to count as evidence."""
    index = _index()
    terms = set(tokenize(query))

    if not terms or not index.chunks:
        return []

    total = len(index.chunks)
    scored: list[tuple[float, int]] = []

    for position, counts in enumerate(index.term_counts):
        length_norm = 1 - B + B * index.lengths[position] / (index.average_length or 1)
        score = 0.0
        for term in terms:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            documents = index.document_frequency[term]
            idf = math.log(1 + (total - documents + 0.5) / (documents + 0.5))
            score += idf * frequency * (K1 + 1) / (frequency + K1 * length_norm)
        if score > 0:
            scored.append((score, position))

    if not scored:
        return []

    scored.sort(reverse=True)
    best = scored[0][0]
    floor = max(MIN_SCORE, best * MIN_RELATIVE_SCORE)

    results: list[RetrievedChunk] = []
    for score, position in scored[:top_k]:
        if score < floor:
            break
        chunk = index.chunks[position]
        # Lower is better, as with vector distances.
        results.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                distance=round(1 / (1 + score), 4),
                metadata=chunk.metadata,
            )
        )

    return results


SENTENCE = re.compile(r"(?<=[.!?])\s+")


def best_passage(text: str, query: str, max_words: int = 70) -> str:
    """The run of up to three sentences in ``text`` that mentions the most
    query words, trimmed to ``max_words``. Quoted as-is, never reworded."""
    sentences = [part.strip() for part in SENTENCE.split(text) if part.strip()]
    if not sentences:
        return ""

    terms = set(tokenize(query))
    best_start, best_hits = 0, -1
    for start in range(len(sentences)):
        window = " ".join(sentences[start:start + 3])
        hits = sum(1 for token in tokenize(window) if token in terms)
        if hits > best_hits:
            best_start, best_hits = start, hits

    words = " ".join(sentences[best_start:best_start + 3]).split()
    passage = " ".join(words[:max_words])
    if len(words) > max_words:
        passage += " …"
    return passage
