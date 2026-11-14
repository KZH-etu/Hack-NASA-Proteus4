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
from src.rag.server.schemas import (
    HealthResponse,
    RetrieveChunk,
    RetrieveRequest,
    RetrieveResponse,
)
from src.rag.storage.chroma_release import SyncResult, ensure_chroma_db_up_to_date

logger = logging.getLogger(__name__)

SyncCallable = Callable[[RagConfig], SyncResult]


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

    @application.post("/retrieve", response_model=RetrieveResponse)
    def retrieve(payload: RetrieveRequest) -> RetrieveResponse:
        collection = application.state.collection
        embedder: LMStudioClient = application.state.llm_client
        total_chunks = int(collection.count())
        if total_chunks == 0:
            return RetrieveResponse(query=payload.query, count=0, results=[])

        try:
            query_vector = embedder.embed_texts([payload.query])[0]
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Impossible de calculer l'embedding de la requête : {exc}",
            ) from exc

        n_results = min(payload.top_k, total_chunks)
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if payload.where:
            query_kwargs["where"] = payload.where

        raw = collection.query(**query_kwargs)
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        chunks: list[RetrieveChunk] = []
        for idx, chunk_id in enumerate(ids):
            chunks.append(
                RetrieveChunk(
                    id=str(chunk_id),
                    document=str(documents[idx]) if idx < len(documents) else "",
                    distance=(
                        float(distances[idx])
                        if idx < len(distances) and distances[idx] is not None
                        else None
                    ),
                    metadata=dict(metadatas[idx] or {}) if idx < len(metadatas) else {},
                )
            )

        return RetrieveResponse(query=payload.query, count=len(chunks), results=chunks)

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
