"""Phase 2: Ingest HTML/JSON docs cleanly without tags and enrich metadata via Phi-3.5-mini."""

from __future__ import annotations

import argparse

from tqdm import tqdm

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.llm_client import LMStudioClient
from src.rag.source_adapter import CatalogSourceProvider, SourceProvider
from src.rag.text_utils import (
    html_to_clean_markdown,
    json_psi_to_markdown,
    strip_html_tags,
)


def ingest_non_pdf_documents(
    config: RagConfig,
    tracking_db: TrackingDB,
    non_pdf_provider: SourceProvider | None = None,
) -> dict[str, int]:
    """Integrate HTML and JSON catalog documents right before metadata extraction.

    Converts HTML into structured Markdown without any HTML tags while preserving
    heading hierarchy (#, ##, ###) for downstream chunking.
    """
    provider = non_pdf_provider
    if provider is None:
        if not config.catalog_csv_path.exists():
            return {"processed": 0, "done": 0, "error": 0}
        provider = CatalogSourceProvider(
            config.catalog_csv_path, extensions=(".html", ".json")
        )

    docs = provider.list_documents()
    if not docs:
        return {"processed": 0, "done": 0, "error": 0}

    config.md_dir.mkdir(parents=True, exist_ok=True)
    done_count = 0
    error_count = 0

    for src in docs:
        id_pdf = tracking_db.upsert_source_document(
            pdf_filename=src.pdf_filename,
            pdf_url=src.pdf_url,
            experiment_url=src.experiment_url,
            source_id=src.source_id or None,
            title=src.title or None,
            source_type=src.source_type or None,
            authors=src.authors or None,
            experiment_year=src.experiment_year,
            file_ext=src.file_ext,
        )
        row = tracking_db.get_document(id_pdf)
        if row is not None and row["ocr_status"] == "done":
            continue

        try:
            if src.file_ext == ".html":
                raw_html = src.pdf_path.read_text(encoding="utf-8", errors="replace")
                markdown_text = html_to_clean_markdown(raw_html, title=src.title)
            elif src.file_ext == ".json":
                markdown_text = json_psi_to_markdown(src.pdf_path, title=src.title)
            else:
                raise ValueError(f"Unsupported non-PDF extension: {src.file_ext}")

            if not markdown_text.strip():
                raise ValueError(f"Empty text extracted from {src.pdf_path.name}")

            md_filename = f"{id_pdf}.md"
            (config.md_dir / md_filename).write_text(markdown_text, encoding="utf-8")
            tracking_db.mark_stage_done(
                id_pdf,
                stage=1,
                pdf_filename=f"{id_pdf}{src.file_ext}",
                md_filename=md_filename,
            )
            done_count += 1
            tqdm.write(
                f"[Pre-Stage 2] HTML/JSON -> {md_filename} | {(src.title or src.pdf_filename)[:65]}"
            )
        except Exception as exc:
            tracking_db.mark_stage_error(id_pdf, stage=1, error_message=str(exc))
            error_count += 1
            tqdm.write(
                f"[Pre-Stage 2] ERREUR -> {src.pdf_filename} ({id_pdf}) : {exc}"
            )

    return {"processed": done_count + error_count, "done": done_count, "error": error_count}


def run(
    config: RagConfig,
    db: TrackingDB | None = None,
    llm_client: LMStudioClient | None = None,
    non_pdf_provider: SourceProvider | None = None,
    limit: int | None = None,
    retry_errors: bool = False,
) -> dict[str, int]:
    """Run Phase 2: integrate HTML/JSON docs, then extract missing metadata via Phi-3.5."""
    tracking_db = db or TrackingDB(config.tracking_db_path)
    client = llm_client or LMStudioClient(
        base_url=config.lm_studio_base_url,
        api_key=config.lm_studio_api_key,
        metadata_model=config.metadata_model,
        embedding_model=config.embedding_model,
        embedding_batch_size=config.embedding_batch_size,
    )
    client.check_connection()

    ingest_non_pdf_documents(config, tracking_db, non_pdf_provider=non_pdf_provider)

    pending = tracking_db.get_pending_for_stage(
        stage=2, retry_errors=retry_errors, limit=limit
    )
    if not pending:
        tqdm.write("[Stage 2] Aucun document en attente.")
        return {"processed": 0, "done": 0, "error": 0}

    tqdm.write(f"[Stage 2] {len(pending)} document(s) à enrichir via {config.metadata_model}...")
    done_count = 0
    error_count = 0
    total = len(pending)

    for idx, row in enumerate(tqdm(pending, desc="Stage 2 - Metadata", unit="doc"), start=1):
        id_pdf = str(row["id_pdf"])
        md_filename = row.get("md_filename")
        title = str(row.get("title") or md_filename or id_pdf)
        try:
            if not md_filename:
                raise FileNotFoundError(f"Missing md_filename for id_pdf={id_pdf}")
            md_path = config.md_dir / str(md_filename)
            if not md_path.exists():
                raise FileNotFoundError(f"Markdown file not found: {md_path}")

            existing_program = (row.get("mission_program") or "").strip()
            existing_year = row.get("experiment_year")
            existing_authors = (row.get("authors") or "").strip()

            has_program = bool(existing_program) and existing_program.lower() != "unknown"
            has_year = existing_year is not None and int(existing_year) != 0
            has_authors = bool(existing_authors) and existing_authors.lower() != "unknown"

            if has_program and has_year and has_authors:
                final_program = existing_program
                final_year = int(existing_year)
                final_authors = existing_authors
            else:
                raw_text = md_path.read_text(encoding="utf-8")
                clean_excerpt = strip_html_tags(raw_text)[: config.metadata_char_limit]
                meta = client.extract_metadata_json(clean_excerpt)
                final_program = existing_program if has_program else meta.mission_program
                final_year = int(existing_year) if has_year else meta.experiment_year
                final_authors = existing_authors if has_authors else meta.authors

            tracking_db.mark_stage_done(
                id_pdf,
                stage=2,
                mission_program=final_program,
                experiment_year=final_year,
                authors=final_authors,
            )
            done_count += 1
            tqdm.write(
                f"[Stage 2] ({idx}/{total}) OK -> {md_filename} | program={final_program} | {title[:60]}"
            )
        except Exception as exc:
            tracking_db.mark_stage_error(id_pdf, stage=2, error_message=str(exc))
            error_count += 1
            tqdm.write(
                f"[Stage 2] ({idx}/{total}) ERREUR -> {md_filename} ({id_pdf}) : {exc}"
            )

    return {
        "processed": len(pending),
        "done": done_count,
        "error": error_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2: Ingest HTML/JSON docs and extract metadata via Phi-3.5."
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
    print(f"Stage 2 summary: {summary}")
    print(f"DB stats: {tracking_db.get_stats()}")


if __name__ == "__main__":
    main()
