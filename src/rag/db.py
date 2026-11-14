"""SQLite3 tracking database for idempotent 3-stage RAG ingestion."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterator

_STAGE_STATUS_COL: dict[int, str] = {
    1: "ocr_status",
    2: "metadata_status",
    3: "index_status",
}

_STAGE_PREREQ: dict[int, str | None] = {
    1: None,
    2: "ocr_status = 'done'",
    3: "metadata_status = 'done'",
}


class TrackingDB:
    """Manages document state across OCR, metadata extraction, and indexing."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pdf_filename TEXT UNIQUE NOT NULL,
                    md_filename TEXT,
                    pdf_url TEXT,
                    experiment_url TEXT,
                    mission_program TEXT,
                    experiment_year INTEGER,
                    authors TEXT,
                    ocr_status TEXT NOT NULL DEFAULT 'pending',
                    metadata_status TEXT NOT NULL DEFAULT 'pending',
                    index_status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def upsert_source_document(
        self,
        pdf_filename: str,
        pdf_url: str,
        experiment_url: str,
    ) -> int:
        """Insert a new source PDF or update its URLs without resetting progress."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (pdf_filename, pdf_url, experiment_url)
                VALUES (?, ?, ?)
                ON CONFLICT(pdf_filename) DO UPDATE SET
                    pdf_url = excluded.pdf_url,
                    experiment_url = excluded.experiment_url,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (pdf_filename, pdf_url, experiment_url),
            )
            row = conn.execute(
                "SELECT document_id FROM documents WHERE pdf_filename = ?",
                (pdf_filename,),
            ).fetchone()
            conn.commit()
            return int(row["document_id"])

    def get_document(self, document_id: int) -> dict[str, Any] | None:
        """Fetch a single document row as a dict."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def get_pending_for_stage(
        self,
        stage: int,
        retry_errors: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return documents eligible for the given stage (1, 2, or 3)."""
        status_col = _validate_stage(stage)
        statuses = ("pending", "error") if retry_errors else ("pending",)
        placeholders = ", ".join("?" for _ in statuses)

        clauses = [f"{status_col} IN ({placeholders})"]
        prereq = _STAGE_PREREQ[stage]
        if prereq:
            clauses.append(prereq)

        query = f"SELECT * FROM documents WHERE {' AND '.join(clauses)} ORDER BY document_id ASC"
        params: list[Any] = list(statuses)
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def mark_stage_done(self, document_id: int, stage: int, **fields: Any) -> None:
        """Mark a stage as done, clear error_message, and update optional columns."""
        status_col = _validate_stage(stage)
        allowed_fields = {
            "md_filename",
            "mission_program",
            "experiment_year",
            "authors",
        }
        updates = [f"{status_col} = 'done'", "error_message = NULL", "updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed_fields:
                raise ValueError(f"Unsupported column update: {key}")
            updates.append(f"{key} = ?")
            params.append(value)

        params.append(document_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE documents SET {', '.join(updates)} WHERE document_id = ?",
                params,
            )
            conn.commit()

    def mark_stage_error(self, document_id: int, stage: int, error_message: str) -> None:
        """Mark a stage as failed and record the error message."""
        status_col = _validate_stage(stage)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE documents
                SET {status_col} = 'error',
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE document_id = ?
                """,
                (error_message, document_id),
            )
            conn.commit()

    def get_stats(self) -> dict[str, Any]:
        """Return document counts by status for each stage."""
        with self._connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
            stats: dict[str, Any] = {"total": total}
            for stage, col in _STAGE_STATUS_COL.items():
                counts = {"pending": 0, "done": 0, "error": 0}
                rows = conn.execute(
                    f"SELECT {col} AS status, COUNT(*) AS cnt FROM documents GROUP BY {col}"
                ).fetchall()
                for row in rows:
                    counts[str(row["status"])] = int(row["cnt"])
                stats[f"stage{stage}"] = counts
            return stats


def _validate_stage(stage: int) -> str:
    if stage not in _STAGE_STATUS_COL:
        raise ValueError(f"Invalid stage {stage}; expected 1, 2, or 3.")
    return _STAGE_STATUS_COL[stage]
