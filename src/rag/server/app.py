"""FastAPI + Uvicorn retrieval server with automatic ChromaDB release sync on startup."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Callable

import chromadb
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.rag.config import RagConfig
from src.rag.llm_client import LMStudioClient
from src.rag.server.schemas import HealthResponse, RetrieveRequest
from src.rag.storage.chroma_release import SyncResult, ensure_chroma_db_up_to_date

logger = logging.getLogger(__name__)

SyncCallable = Callable[[RagConfig], SyncResult]


def _extract_chunk_body(document: str) -> str:
    """Strip the 'Contexte : ...\\nTexte : ' prefix injected at indexing time."""
    marker = "\nTexte : "
    if document.startswith("Contexte : ") and marker in document:
        return document.split(marker, 1)[1].strip()
    return document.strip()


def _merge_adjacent_texts(texts: list[str]) -> str:
    """Concatenate ordered chunk texts while collapsing exact overlap seams."""
    cleaned = [t for t in texts if t]
    if not cleaned:
        return ""

    merged = cleaned[0]
    for nxt in cleaned[1:]:
        max_overlap = min(len(merged), len(nxt))
        overlap_len = 0
        for size in range(max_overlap, 19, -1):
            if merged.endswith(nxt[:size]):
                overlap_len = size
                break
        if overlap_len:
            merged = merged + nxt[overlap_len:]
        else:
            merged = f"{merged}\n{nxt}"
    return merged


def _format_context_block(metadata: dict[str, Any], merged_text: str) -> str:
    """Format document source metadata and concatenated chunk text for an LLM."""
    if not metadata:
        return merged_text

    title = str(metadata.get("title") or "").strip()
    authors = str(metadata.get("authors") or "").strip()
    mission = str(metadata.get("mission_program") or "").strip()
    year = metadata.get("experiment_year")
    source_type = str(metadata.get("source_type") or "").strip()
    headers_path = str(metadata.get("headers_path") or "").strip()
    url = str(metadata.get("experiment_url") or metadata.get("pdf_url") or "").strip()

    header_lines: list[str] = []
    if title:
        header_lines.append(f"Document : {title}")

    meta_parts: list[str] = []
    if authors and authors != "Unknown":
        meta_parts.append(f"Auteurs : {authors}")
    if mission and mission != "Unknown":
        meta_parts.append(f"Mission : {mission}")
    if year:
        meta_parts.append(f"Année : {year}")
    if source_type:
        meta_parts.append(f"Source : {source_type}")
    if meta_parts:
        header_lines.append(" | ".join(meta_parts))

    if headers_path:
        header_lines.append(f"Section : {headers_path}")
    if url:
        header_lines.append(f"URL : {url}")

    if not header_lines:
        return merged_text
    return "\n".join(header_lines) + "\n---\n" + merged_text


def _fetch_neighbors_map(
    collection: Any,
    hits_meta: list[dict[str, Any]],
    neighbors: int,
) -> dict[tuple[str, int], str]:
    """Fetch adjacent chunks per unique id_pdf in batched ChromaDB calls."""
    if neighbors <= 0:
        return {}

    needed_by_doc: dict[str, set[int]] = {}
    for meta in hits_meta:
        id_pdf = meta.get("id_pdf")
        raw_idx = meta.get("chunk_index")
        if id_pdf is None or raw_idx is None:
            continue
        idx = int(raw_idx)
        indices = needed_by_doc.setdefault(str(id_pdf), set())
        for candidate in range(max(0, idx - neighbors), idx + neighbors + 1):
            indices.add(candidate)

    chunk_map: dict[tuple[str, int], str] = {}
    for id_pdf, indices in needed_by_doc.items():
        fetched = collection.get(
            where={
                "$and": [
                    {"id_pdf": id_pdf},
                    {"chunk_index": {"$in": sorted(indices)}},
                ]
            },
            include=["documents", "metadatas"],
        )
        docs = fetched.get("documents") or []
        metas = fetched.get("metadatas") or []
        for doc_text, doc_meta in zip(docs, metas):
            if not doc_meta or doc_meta.get("chunk_index") is None:
                continue
            key = (id_pdf, int(doc_meta["chunk_index"]))
            chunk_map[key] = _extract_chunk_body(str(doc_text or ""))
    return chunk_map


def _retrieve_contexts(
    collection: Any,
    query_vector: list[float],
    top_k: int,
    neighbors: int,
) -> list[str]:
    """Query ChromaDB and return one concatenated context string per hit."""
    total_chunks = int(collection.count())
    if total_chunks == 0:
        return []

    n_results = min(top_k, total_chunks)
    raw = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        include=["documents", "metadatas"],
    )
    documents = (raw.get("documents") or [[]])[0]
    metadatas = [dict(m or {}) for m in ((raw.get("metadatas") or [[]])[0])]
    if not documents:
        return []

    neighbor_map = _fetch_neighbors_map(collection, metadatas, neighbors)
    contexts: list[str] = []

    for idx, hit_doc in enumerate(documents):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        hit_body = _extract_chunk_body(str(hit_doc or ""))
        id_pdf = meta.get("id_pdf")
        raw_cidx = meta.get("chunk_index")

        if neighbors > 0 and id_pdf is not None and raw_cidx is not None:
            center = int(raw_cidx)
            ordered_parts: list[str] = []
            for pos in range(max(0, center - neighbors), center + neighbors + 1):
                part = neighbor_map.get((str(id_pdf), pos))
                if part is None and pos == center:
                    part = hit_body
                if part:
                    ordered_parts.append(part)
            merged_text = _merge_adjacent_texts(ordered_parts) if ordered_parts else hit_body
        else:
            merged_text = hit_body

        contexts.append(_format_context_block(meta, merged_text))

    return contexts


def create_app(
    config: RagConfig | None = None,
    *,
    sync_fn: SyncCallable = ensure_chroma_db_up_to_date,
    chroma_client: Any | None = None,
    llm_client: LMStudioClient | None = None,
    skip_sync: bool | None = None,
) -> FastAPI:
    """Build the FastAPI retrieval application with startup ChromaDB synchronization."""
    load_dotenv()
    resolved_config = config or RagConfig.from_env()
    should_skip_sync = (
        skip_sync
        if skip_sync is not None
        else os.getenv("RAG_SKIP_CHROMA_SYNC", "0").lower() in {"1", "true", "yes"}
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        if should_skip_sync:
            sync_result = SyncResult(
                status="skipped",
                tag_name=None,
                chunk_count=None,
                chroma_dir=resolved_config.chroma_dir,
                message="Synchronisation ChromaDB ignorée (--skip-sync).",
            )
        else:
            logger.info("Vérification de la base ChromaDB avant démarrage du serveur...")
            sync_result = sync_fn(resolved_config)
            logger.info("[Sync %s] %s", sync_result.status, sync_result.message)

        client = chroma_client or chromadb.PersistentClient(
            path=str(resolved_config.chroma_dir)
        )
        collection = client.get_or_create_collection(
            name=resolved_config.chroma_collection
        )
        embedder = llm_client or LMStudioClient(
            base_url=resolved_config.lm_studio_base_url,
            api_key=resolved_config.lm_studio_api_key,
            metadata_model=resolved_config.metadata_model,
            embedding_model=resolved_config.embedding_model,
            embedding_batch_size=resolved_config.embedding_batch_size,
        )

        app_instance.state.config = resolved_config
        app_instance.state.sync_result = sync_result
        app_instance.state.chroma_client = client
        app_instance.state.collection = collection
        app_instance.state.llm_client = embedder
        yield

    application = FastAPI(
        title="NASA Flame in Freefall — RAG Retrieval API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        collection = application.state.collection
        sync_result: SyncResult = application.state.sync_result
        return HealthResponse(
            status="ok",
            sync_status=sync_result.status,
            release_tag=sync_result.tag_name,
            collection=resolved_config.chroma_collection,
            chunk_count=int(collection.count()),
        )

    @application.post("/retrieve", response_model=list[str])
    def retrieve(payload: RetrieveRequest) -> list[str]:
        collection = application.state.collection
        embedder: LMStudioClient = application.state.llm_client
        if int(collection.count()) == 0:
            return []

        try:
            query_vector = embedder.embed_texts([payload.query])[0]
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Impossible de calculer l'embedding de la requête : {exc}",
            ) from exc

        return _retrieve_contexts(
            collection=collection,
            query_vector=query_vector,
            top_k=payload.top_k,
            neighbors=payload.neighbors,
        )

    return application


app = create_app()


def main(argv: list[str] | None = None) -> int:
    """Launch the FastAPI retrieval server with Uvicorn."""
    parser = argparse.ArgumentParser(
        description="Lance le serveur web FastAPI RAG après synchronisation ChromaDB."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute.")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute.")
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Ne vérifie pas la release GitHub au démarrage.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    if args.skip_sync:
        os.environ["RAG_SKIP_CHROMA_SYNC"] = "1"

    uvicorn.run(
        "src.rag.server.app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
