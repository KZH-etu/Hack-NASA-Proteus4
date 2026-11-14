"""Phase 1: Rename PDFs to {uuid}.pdf, deduce source_type, and run Marker OCR."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from src.rag.config import RagConfig
from src.rag.ingestion.db import TrackingDB
from src.rag.ingestion.source_adapter import CatalogSourceProvider, SourceProvider

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


def prepare_uuid_pdf(src_path: Path, pdf_dir: Path, id_pdf: str) -> Path:
    """Ensure the PDF exists in pdf_dir under the name '{id_pdf}.pdf'.

    If src_path is already inside pdf_dir, it is renamed in place.
    Otherwise it is copied into pdf_dir so data/raw/ stays intact.
    """
    pdf_dir.mkdir(parents=True, exist_ok=True)
    target_path = pdf_dir / f"{id_pdf}.pdf"
    if target_path.exists():
        return target_path
    if not src_path.exists():
        raise FileNotFoundError(f"Source PDF not found: {src_path}")

    if src_path.resolve().parent == pdf_dir.resolve():
        src_path.rename(target_path)
    else:
        shutil.copy2(src_path, target_path)
    return target_path


def _fallback_pdf_to_markdown(
    pdf_path: Path,
    source_id: str | None,
    title: str,
    catalog_csv_path: Path,
) -> str:
    """Fallback text extraction via pages/<source_id>.jsonl or PyMuPDF if Marker fails."""
    if source_id:
        jsonl_path = catalog_csv_path.parent / "pages" / f"{source_id}.jsonl"
        if jsonl_path.exists():
            pages_text: list[str] = []
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                txt = (item.get("text") or "").strip()
                if txt:
                    pages_text.append(f"## Page {item.get('page', '')}\n\n{txt}")
            if pages_text:
                header = f"# {title}\n\n" if title else ""
                return header + "\n\n".join(pages_text)

    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        pages_text = []
        for idx, page in enumerate(doc, start=1):
            txt = page.get_text().strip()
            if txt:
                pages_text.append(f"## Page {idx}\n\n{txt}")
    finally:
        doc.close()

    if not pages_text:
        raise ValueError(f"No extractable text found in {pdf_path.name}")
    header = f"# {title}\n\n" if title else ""
    return header + "\n\n".join(pages_text)


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
    fallback_on_error: bool = True,
) -> dict[str, int]:
    """Run Phase 1: sync catalog.csv PDFs, rename to {uuid}.pdf, and OCR to Markdown."""
    provider = source_provider or CatalogSourceProvider(
        config.catalog_csv_path, extensions=(".pdf",)
    )
    tracking_db = db or TrackingDB(config.tracking_db_path)
    config.pdf_dir.mkdir(parents=True, exist_ok=True)
    config.md_dir.mkdir(parents=True, exist_ok=True)

    source_docs = provider.list_documents()
    path_by_id_pdf: dict[str, Path] = {}
    for src in source_docs:
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
        path_by_id_pdf[id_pdf] = src.pdf_path

    pending = tracking_db.get_pending_for_stage(
        stage=1, retry_errors=retry_errors, limit=limit
    )
    if not pending:
        tqdm.write("[Stage 1] Aucun document PDF en attente.")
        return {"processed": 0, "done": 0, "error": 0}

    tqdm.write(f"[Stage 1] {len(pending)} document(s) PDF à convertir avec Marker...")
    active_converter = converter or _build_marker_converter()
    done_count = 0
    error_count = 0
    total = len(pending)

    for idx, row in enumerate(tqdm(pending, desc="Stage 1 - OCR", unit="pdf"), start=1):
        id_pdf = str(row["id_pdf"])
        pdf_filename = str(row["pdf_filename"])
        title = str(row.get("title") or pdf_filename)
        src_path = path_by_id_pdf.get(id_pdf, config.pdf_dir / pdf_filename)
        try:
            uuid_pdf_path = prepare_uuid_pdf(src_path, config.pdf_dir, id_pdf)
            used_fallback = False
            try:
                markdown_text = convert_pdf_to_markdown(
                    uuid_pdf_path, converter=active_converter
                )
            except Exception as marker_exc:
                if not fallback_on_error:
                    raise marker_exc
                markdown_text = _fallback_pdf_to_markdown(
                    uuid_pdf_path,
                    source_id=row.get("source_id"),
                    title=title,
                    catalog_csv_path=config.catalog_csv_path,
                )
                used_fallback = True

            md_filename = f"{id_pdf}.md"
            (config.md_dir / md_filename).write_text(markdown_text, encoding="utf-8")
            tracking_db.mark_stage_done(
                id_pdf,
                stage=1,
                pdf_filename=uuid_pdf_path.name,
                md_filename=md_filename,
            )
            done_count += 1
            mode = "OK (fallback)" if used_fallback else "OK"
            tqdm.write(
                f"[Stage 1] ({idx}/{total}) {mode} -> {md_filename} | {title[:65]}"
            )
        except Exception as exc:
            tracking_db.mark_stage_error(id_pdf, stage=1, error_message=str(exc))
            error_count += 1
            tqdm.write(
                f"[Stage 1] ({idx}/{total}) ERREUR -> {pdf_filename} ({id_pdf}) : {exc}"
            )

    return {
        "processed": len(pending),
        "done": done_count,
        "error": error_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1: Rename PDFs to {uuid}.pdf from catalog.csv and run Marker OCR."
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
