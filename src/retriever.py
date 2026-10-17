import importlib.util

from src.config import (
    RAG_MAX_DISTANCE,
    RAG_TOP_K,
)
from src.embeddings import OllamaEmbeddingService
from src.observability.logging import get_logger
from src.schemas import RetrievedChunk

logger = get_logger(__name__)


def get_chroma_collection():
    # Imported on use: chromadb isn't installed on every deployment.
    from src.vector_store import get_chroma_collection as load_collection

    return load_collection()


def vector_search_available() -> bool:
    """False where chromadb isn't installed (the Vercel deployment)."""
    return importlib.util.find_spec("chromadb") is not None


def retrieve_chunks(
    query: str,
    top_k: int = RAG_TOP_K,
) -> list[RetrievedChunk]:
    if not query or not query.strip():
        return []

    if vector_search_available():
        try:
            return _vector_search(query.strip(), top_k)
        except Exception:
            # Ollama (for embeddings) or the index is down: keyword search
            # over the same approved sources still finds evidence.
            logger.exception("vector search failed; using keyword search")

    from src.lexical_search import search

    return search(query.strip(), top_k=top_k)


def _vector_search(
    query: str,
    top_k: int,
) -> list[RetrievedChunk]:
    embedding_service = OllamaEmbeddingService()
    query_embedding = embedding_service.embed_query(query)

    collection = get_chroma_collection()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]

    retrieved: list[RetrievedChunk] = []

    for chunk_id, text, metadata, distance in zip(
        ids,
        documents,
        metadatas,
        distances,
    ):
        numeric_distance = float(distance)

        if numeric_distance > RAG_MAX_DISTANCE:
            continue

        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text=text,
                distance=numeric_distance,
                metadata=metadata,
            )
        )

    return retrieved


def diversify_results(
    chunks: list[RetrievedChunk],
    maximum_per_source: int = 2,
) -> list[RetrievedChunk]:
    counts: dict[str, int] = {}
    diversified: list[RetrievedChunk] = []

    for chunk in chunks:
        source_id = str(
            chunk.metadata.get(
                "source_id",
                "unknown",
            )
        )

        current_count = counts.get(source_id, 0)

        if current_count >= maximum_per_source:
            continue

        diversified.append(chunk)
        counts[source_id] = current_count + 1

    return diversified
