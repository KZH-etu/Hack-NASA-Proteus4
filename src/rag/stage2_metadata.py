"""Phase 2: Extract structured JSON metadata from Markdown via Phi-3.5-mini."""

from __future__ import annotations

import argparse

from tqdm import tqdm

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.llm_client import LMStudioClient


def run(
    config: RagConfig,
    db: TrackingDB | None = None,
    llm_client: LMStudioClient | None = None,
    limit: int | None = None,
    retry_errors: bool = False,
) -> dict[str, int]:
    """Run Phase 2: extract mission_program, experiment_year, and authors."""
    tracking_db = db or TrackingDB(config.tracking_db_path)
    client = llm_client or LMStudioClient(
        base_url=config.lm_studio_base_url,
        api_key=config.lm_studio_api_key,
        metadata_model=config.metadata_model,
        embedding_model=config.embedding_model,
        embedding_batch_size=config.embedding_batch_size,
    )
    client.check_connection()

    pending = tracking_db.get_pending_for_stage(
        stage=2, retry_errors=retry_errors, limit=limit
    )
    if not pending:
        return {"processed": 0, "done": 0, "error": 0}

    done_count = 0
    error_count = 0

    for row in tqdm(pending, desc="Stage 2 - Metadata", unit="doc"):
        doc_id = int(row["document_id"])
        md_filename = row.get("md_filename")
        try:
            if not md_filename:
                raise FileNotFoundError(f"Missing md_filename for document_id={doc_id}")
            md_path = config.md_dir / str(md_filename)
            if not md_path.exists():
                raise FileNotFoundError(f"Markdown file not found: {md_path}")

            excerpt = md_path.read_text(encoding="utf-8")[: config.metadata_char_limit]
            meta = client.extract_metadata_json(excerpt)
            tracking_db.mark_stage_done(
                doc_id,
                stage=2,
                mission_program=meta.mission_program,
                experiment_year=meta.experiment_year,
                authors=meta.authors,
            )
            done_count += 1
        except Exception as exc:
            tracking_db.mark_stage_error(doc_id, stage=2, error_message=str(exc))
            error_count += 1

    return {
        "processed": len(pending),
        "done": done_count,
        "error": error_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2: Extract JSON metadata from Markdown using Phi-3.5 via LM Studio."
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
