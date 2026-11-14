"""Phase 1: OCR PDFs into Markdown via Marker and initialize tracking.db."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from tqdm import tqdm

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.source_adapter import PlaceholderSourceProvider, SourceProvider

PdfConverterFn = Callable[[Path], str]


def convert_pdf_to_markdown(
    pdf_path: Path,
    converter: PdfConverterFn | None = None,
) -> str:
    """Convert a single PDF file to Markdown text."""
    if converter is not None:
        return converter(pdf_path)

    default_fn = _build_marker_converter()
    return default_fn(pdf_path)


def _build_marker_converter() -> PdfConverterFn:
    """Lazily load Marker in Balanced mode so memory stays free until Phase 1 runs."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered
    except ImportError as exc:
        raise ImportError(
            "marker-pdf is required for Phase 1 OCR. Install it with: pip install marker-pdf"
        ) from exc

    pdf_converter = PdfConverter(artifact_dict=create_model_dict())

    def _convert(pdf_path: Path) -> str:
        rendered = pdf_converter(str(pdf_path))
        markdown_text, _, _ = text_from_rendered(rendered)
        return markdown_text

    return _convert


def run(
    config: RagConfig,
    source_provider: SourceProvider | None = None,
    db: TrackingDB | None = None,
    converter: PdfConverterFn | None = None,
    limit: int | None = None,
    retry_errors: bool = False,
) -> dict[str, int]:
    """Run Phase 1: sync source PDFs and convert pending ones to Markdown."""
    provider = source_provider or PlaceholderSourceProvider(
        config.pdf_dir, config.source_manifest_path
    )
    tracking_db = db or TrackingDB(config.tracking_db_path)
    config.md_dir.mkdir(parents=True, exist_ok=True)

    source_docs = provider.list_documents()
    path_by_filename: dict[str, Path] = {}
    for src in source_docs:
        tracking_db.upsert_source_document(
            pdf_filename=src.pdf_filename,
            pdf_url=src.pdf_url,
            experiment_url=src.experiment_url,
        )
        path_by_filename[src.pdf_filename] = src.pdf_path

    pending = tracking_db.get_pending_for_stage(
        stage=1, retry_errors=retry_errors, limit=limit
    )
    if not pending:
        return {"processed": 0, "done": 0, "error": 0}

    active_converter = converter or _build_marker_converter()
    done_count = 0
    error_count = 0

    for row in tqdm(pending, desc="Stage 1 - OCR", unit="pdf"):
        doc_id = int(row["document_id"])
        pdf_filename = str(row["pdf_filename"])
        pdf_path = path_by_filename.get(pdf_filename, config.pdf_dir / pdf_filename)
        try:
            markdown_text = convert_pdf_to_markdown(pdf_path, converter=active_converter)
            md_filename = f"{Path(pdf_filename).stem}.md"
            (config.md_dir / md_filename).write_text(markdown_text, encoding="utf-8")
            tracking_db.mark_stage_done(doc_id, stage=1, md_filename=md_filename)
            done_count += 1
        except Exception as exc:
            tracking_db.mark_stage_error(doc_id, stage=1, error_message=str(exc))
            error_count += 1

    return {
        "processed": len(pending),
        "done": done_count,
        "error": error_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1: Convert NASA PDFs to Markdown using Marker."
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
    print(f"Stage 1 summary: {summary}")
    print(f"DB stats: {tracking_db.get_stats()}")


if __name__ == "__main__":
    main()
