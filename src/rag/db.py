"""SQLite3 tracking database for idempotent 3-stage RAG ingestion."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
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

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id_pdf TEXT PRIMARY KEY,
    source_id TEXT UNIQUE,
    pdf_filename TEXT UNIQUE NOT NULL,
    md_filename TEXT,
    title TEXT,
    source_type TEXT,
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
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
            if not existing_cols:
                conn.execute(_CREATE_TABLE_SQL)
                return

            if "document_id" in existing_cols:
                # Migrate legacy schema (document_id PK -> id_pdf TEXT PRIMARY KEY)
                conn.execute("DROP TABLE IF EXISTS documents_new")
                conn.execute(_CREATE_TABLE_SQL.replace("CREATE TABLE IF NOT EXISTS documents", "CREATE TABLE documents_new"))
                conn.execute(
                    """
                    INSERT INTO documents_new (
                        id_pdf, source_id, pdf_filename, md_filename, title, source_type,
                        pdf_url, experiment_url, mission_program, experiment_year, authors,
                        ocr_status, metadata_status, index_status, error_message, updated_at
                    )
                    SELECT
                        COALESCE(NULLIF(id_pdf, ''), CAST(document_id AS TEXT)),
                        source_id,
                        CASE
                            WHEN id_pdf IS NOT NULL AND id_pdf != '' AND pdf_filename NOT LIKE id_pdf || '.%'
                            THEN id_pdf || '.pdf'
                            ELSE pdf_filename
                        END,
                        md_filename,
                        title,
                        source_type,
                        pdf_url,
                        experiment_url,
                        mission_program,
                        experiment_year,
                        authors,
                        ocr_status,
                        metadata_status,
                        index_status,
                        error_message,
                        updated_at
                    FROM documents
                    """
                )
                conn.execute("DROP TABLE documents")
                conn.execute("ALTER TABLE documents_new RENAME TO documents")

    def upsert_source_document(
        self,
        pdf_filename: str,
        pdf_url: str,
        experiment_url: str,
        *,
        source_id: str | None = None,
        title: str | None = None,
        source_type: str | None = None,
        authors: str | None = None,
        experiment_year: int | None = None,
        id_pdf: str | None = None,
        file_ext: str | None = None,
    ) -> str:
        """Insert a new source document with a UUID id_pdf or update catalog metadata."""
        ext = file_ext or Path(pdf_filename).suffix.lower() or ".pdf"
        with self._connect() as conn:
            existing = None
            if source_id:
                existing = conn.execute(
                    "SELECT id_pdf, pdf_filename FROM documents WHERE source_id = ? OR id_pdf = ?",
                    (source_id, source_id),
                ).fetchone()
            if existing is None:
                existing = conn.execute(
                    "SELECT id_pdf, pdf_filename FROM documents WHERE pdf_filename = ?",
                    (pdf_filename,),
                ).fetchone()

            if existing is not None:
                existing_uuid = str(existing["id_pdf"])
                canonical_filename = f"{existing_uuid}{ext}"
                conn.execute(
                    """
                    UPDATE documents SET
                        source_id = COALESCE(?, source_id),
                        pdf_filename = ?,
                        pdf_url = ?,
                        experiment_url = ?,
                        title = COALESCE(NULLIF(?, ''), title),
                        source_type = COALESCE(NULLIF(?, ''), source_type),
                        authors = COALESCE(NULLIF(?, ''), authors),
                        experiment_year = COALESCE(?, experiment_year),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id_pdf = ?
                    """,
                    (
                        source_id,
                        canonical_filename,
                        pdf_url,
                        experiment_url,
                        title or "",
                        source_type or "",
                        authors or "",
                        experiment_year,
                        existing_uuid,
                    ),
                )
                return existing_uuid

            assigned_uuid = id_pdf or str(uuid.uuid4())
            canonical_filename = f"{assigned_uuid}{ext}"
            conn.execute(
                """
                INSERT INTO documents (
                    id_pdf, source_id, pdf_filename, pdf_url, experiment_url,
                    title, source_type, authors, experiment_year
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assigned_uuid,
                    source_id,
                    canonical_filename,
                    pdf_url,
                    experiment_url,
                    title,
                    source_type,
                    authors,
                    experiment_year,
                ),
            )
            return assigned_uuid

    def get_document(self, id_pdf: str) -> dict[str, Any] | None:
        """Fetch a single document row as a dict."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id_pdf = ?",
                (id_pdf,),
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

        query = f"SELECT * FROM documents WHERE {' AND '.join(clauses)} ORDER BY rowid ASC"
        params: list[Any] = list(statuses)
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def mark_stage_done(self, id_pdf: str, stage: int, **fields: Any) -> None:
        """Mark a stage as done, clear error_message, and update optional columns."""
        status_col = _validate_stage(stage)
        allowed_fields = {
            "md_filename",
            "pdf_filename",
            "mission_program",
            "experiment_year",
            "authors",
            "title",
            "source_type",
        }
        updates = [
            f"{status_col} = 'done'",
            "error_message = NULL",
            "updated_at = CURRENT_TIMESTAMP",
        ]
        params: list[Any] = []
        for key, value in fields.items():
            if key not in allowed_fields:
                raise ValueError(f"Unsupported column update: {key}")
            updates.append(f"{key} = ?")
            params.append(value)

        params.append(id_pdf)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE documents SET {', '.join(updates)} WHERE id_pdf = ?",
                params,
            )

    def mark_stage_error(self, id_pdf: str, stage: int, error_message: str) -> None:
        """Mark a stage as failed and record the error message."""
        status_col = _validate_stage(stage)
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE documents
                SET {status_col} = 'error',
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id_pdf = ?
                """,
                (error_message, id_pdf),
            )

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
