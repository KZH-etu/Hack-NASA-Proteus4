"""Phase 3: Double chunking with breadcrumbs, Qwen3 embeddings, and ChromaDB indexing."""

from __future__ import annotations

import argparse
import uuid
from typing import Any

import chromadb
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from tqdm import tqdm

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.llm_client import LMStudioClient
from src.rag.text_utils import strip_html_tags

_HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]


def chunk_markdown(
    markdown_text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[dict[str, str]]:
    """Strip any HTML tags, split Markdown by headers then recursively, with breadcrumbs."""
    clean_markdown = strip_html_tags(markdown_text)
    if not clean_markdown:
        return []

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS_TO_SPLIT_ON,
        strip_headers=True,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    sections = header_splitter.split_text(clean_markdown)
    if not sections:
        return []

    chunks: list[dict[str, str]] = []
    for section in sections:
        header_parts = [
            strip_html_tags(str(section.metadata[key]))
            for _, key in _HEADERS_TO_SPLIT_ON
            if key in section.metadata and str(section.metadata[key]).strip()
        ]
        headers_path = " > ".join(header_parts) if header_parts else "Document"

        sub_chunks = text_splitter.split_text(section.page_content)
        for content in sub_chunks:
            cleaned_content = strip_html_tags(content)
            if not cleaned_content:
                continue
            chunks.append(
                {
                    "headers_path": headers_path,
                    "content": cleaned_content,
                    "document_text": f"Contexte : {headers_path}\nTexte : {cleaned_content}",
                }
            )
    return chunks


def build_chroma_metadata(
    doc_row: dict[str, Any],
    chunk_index: int,
    headers_path: str,
) -> dict[str, str | int]:
    """Build ChromaDB-safe metadata keyed by id_pdf (no None values, no document_id)."""
    year_raw = doc_row.get("experiment_year")
    experiment_year = int(year_raw) if year_raw is not None else 0
    return {
        "id_pdf": str(doc_row["id_pdf"]),
        "title": str(doc_row.get("title") or ""),
        "source_type": str(doc_row.get("source_type") or "autres"),
        "chunk_index": int(chunk_index),
        "headers_path": str(headers_path or "Document"),
        "mission_program": str(doc_row.get("mission_program") or "Unknown"),
        "experiment_year": experiment_year,
        "authors": str(doc_row.get("authors") or "Unknown"),
        "pdf_url": str(doc_row.get("pdf_url") or ""),
        "experiment_url": str(doc_row.get("experiment_url") or ""),
    }


def run(
    config: RagConfig,
    db: TrackingDB | None = None,
    llm_client: LMStudioClient | None = None,
    chroma_client: Any | None = None,
    limit: int | None = None,
    retry_errors: bool = False,
) -> dict[str, int]:
    """Run Phase 3: double chunking, Qwen3 embedding, and ChromaDB indexing."""
    tracking_db = db or TrackingDB(config.tracking_db_path)
    client = llm_client or LMStudioClient(
        base_url=config.lm_studio_base_url,
        api_key=config.lm_studio_api_key,
        metadata_model=config.metadata_model,
        embedding_model=config.embedding_model,
        embedding_batch_size=config.embedding_batch_size,
    )
    client.check_connection()

    config.chroma_dir.mkdir(parents=True, exist_ok=True)
    chroma = chroma_client or chromadb.PersistentClient(path=str(config.chroma_dir))
    collection = chroma.get_or_create_collection(name=config.chroma_collection)

    pending = tracking_db.get_pending_for_stage(
        stage=3, retry_errors=retry_errors, limit=limit
    )
    if not pending:
        tqdm.write("[Stage 3] Aucun document en attente.")
        return {"processed": 0, "done": 0, "error": 0}

    tqdm.write(f"[Stage 3] {len(pending)} document(s) à indexer dans ChromaDB...")
    done_count = 0
    error_count = 0
    total = len(pending)

    for idx, row in enumerate(tqdm(pending, desc="Stage 3 - Indexing", unit="doc"), start=1):
        id_pdf = str(row["id_pdf"])
        md_filename = row.get("md_filename")
        title = str(row.get("title") or md_filename or id_pdf)
        try:
            if not md_filename:
                raise FileNotFoundError(f"Missing md_filename for id_pdf={id_pdf}")
            md_path = config.md_dir / str(md_filename)
            if not md_path.exists():
                raise FileNotFoundError(f"Markdown file not found: {md_path}")

            markdown_text = md_path.read_text(encoding="utf-8")
            chunks = chunk_markdown(
                markdown_text,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
            )
            if not chunks:
                raise ValueError(f"No indexable chunks produced from {md_filename}")

            documents = [chunk["document_text"] for chunk in chunks]
            embeddings = client.embed_texts(documents)
            if len(embeddings) != len(documents):
                raise ValueError(
                    f"Embedding count mismatch: expected {len(documents)}, got {len(embeddings)}"
                )

            ids = [str(uuid.uuid4()) for _ in chunks]
            metadatas = [
                build_chroma_metadata(row, chunk_index=c_idx, headers_path=chunk["headers_path"])
                for c_idx, chunk in enumerate(chunks)
            ]

            collection.delete(where={"id_pdf": id_pdf})
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            tracking_db.mark_stage_done(id_pdf, stage=3)
            done_count += 1
            tqdm.write(
                f"[Stage 3] ({idx}/{total}) OK -> {md_filename} ({len(chunks)} chunks) | {title[:60]}"
            )
        except Exception as exc:
            tracking_db.mark_stage_error(id_pdf, stage=3, error_message=str(exc))
            error_count += 1
            tqdm.write(
                f"[Stage 3] ({idx}/{total}) ERREUR -> {md_filename} ({id_pdf}) : {exc}"
            )

    return {
        "processed": len(pending),
        "done": done_count,
        "error": error_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3: Chunk Markdown, embed with Qwen3, and index into ChromaDB."
    )
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process.")
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="Reprocess documents previously marked as error.",
    )
    args = parser.parse_args()

    config = RagConfig.from_env()
    tracking_db = TrackingDB(config.tracking_db_path)
    summary = run(config, db=tracking_db, limit=args.limit, retry_errors=args.retry_errors)
    print(f"Stage 3 summary: {summary}")
    print(f"DB stats: {tracking_db.get_stats()}")


if __name__ == "__main__":
    main()
