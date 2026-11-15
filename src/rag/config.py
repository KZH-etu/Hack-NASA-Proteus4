"""Configuration for the 3-stage NASA RAG ingestion pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RagConfig:
    """Central configuration for paths, local LM Studio ingestion, webapp embeddings, and chunking."""

    catalog_csv_path: Path = Path("data/raw/ntrs/catalog.csv")
    pdf_dir: Path = Path("data/rag/pdfs")
    md_dir: Path = Path("data/rag/markdown")
    tracking_db_path: Path = Path("data/rag/tracking.db")
    chroma_dir: Path = Path("data/rag/chroma_db")
    chroma_collection: str = "nasa_scientific_reports"
    source_manifest_path: Path = Path("data/rag/source_manifest.json")
    github_repo: str = "KZH-etu/Hack-NASA-Proteus4"
    chroma_release_prefix: str = "chroma-db-"
    chroma_sync_strict: bool = False

    # Preprocessing / ingestion (local LM Studio only)
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    metadata_model: str = "phi-3.5-mini-instruct"
    embedding_model: str = "text-embedding-qwen3-embedding-0.6b"

    # Webapp query embedding (remote OpenAI-compatible server)
    webapp_embedding_base_url: str = "https://ai.derveloy.eu/v1"
    webapp_embedding_api_key: str = ""
    webapp_embedding_model: str = "qwen3-embedding:0.6b"

    metadata_char_limit: int = 3000
    chunk_size: int = 1000
    chunk_overlap: int = 200
    embedding_batch_size: int = 32

    @classmethod
    def from_env(cls) -> "RagConfig":
        """Build configuration from environment variables with sensible defaults."""
        return cls(
            catalog_csv_path=Path(
                os.getenv("RAG_CATALOG_CSV", "data/raw/ntrs/catalog.csv")
            ),
            pdf_dir=Path(os.getenv("RAG_PDF_DIR", "data/rag/pdfs")),
            md_dir=Path(os.getenv("RAG_MD_DIR", "data/rag/markdown")),
            tracking_db_path=Path(os.getenv("RAG_TRACKING_DB", "data/rag/tracking.db")),
            chroma_dir=Path(os.getenv("RAG_CHROMA_DIR", "data/rag/chroma_db")),
            chroma_collection=os.getenv("RAG_CHROMA_COLLECTION", "nasa_scientific_reports"),
            source_manifest_path=Path(
                os.getenv("RAG_SOURCE_MANIFEST", "data/rag/source_manifest.json")
            ),
            github_repo=os.getenv("RAG_GITHUB_REPO", "KZH-etu/Hack-NASA-Proteus4"),
            chroma_release_prefix=os.getenv("RAG_CHROMA_RELEASE_PREFIX", "chroma-db-"),
            chroma_sync_strict=os.getenv("RAG_CHROMA_SYNC_STRICT", "false").lower()
            in {"1", "true", "yes"},
            lm_studio_base_url=os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1"),
            lm_studio_api_key=os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
            metadata_model=os.getenv("RAG_METADATA_MODEL", "phi-3.5-mini-instruct"),
            embedding_model=os.getenv(
                "RAG_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-0.6b"
            ),
            webapp_embedding_base_url=os.getenv(
                "WEBAPP_EMBEDDING_BASE_URL", "https://ai.derveloy.eu/v1"
            ),
            webapp_embedding_api_key=(
                os.getenv("QWEN3_EMBEDDING")
                or os.getenv("WEBAPP_EMBEDDING_API_KEY")
                or ""
            ).strip(),
            webapp_embedding_model=os.getenv(
                "WEBAPP_EMBEDDING_MODEL", "qwen3-embedding:0.6b"
            ),
            metadata_char_limit=int(os.getenv("RAG_METADATA_CHAR_LIMIT", "3000")),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "1000")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "200")),
            embedding_batch_size=int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "32")),
        )
