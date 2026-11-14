import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from src.rag.ingestion.db import TrackingDB


class TestTrackingDB(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "nested" / "tracking.db"
        self.db = TrackingDB(self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_creates_db_file_and_documents_schema_without_document_id(self) -> None:
        self.assertTrue(self.db_path.exists())
        with closing(sqlite3.connect(self.db_path)) as conn:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
        expected_cols = {
            "id_pdf",
            "source_id",
            "pdf_filename",
            "md_filename",
            "title",
            "source_type",
            "pdf_url",
            "experiment_url",
            "mission_program",
            "experiment_year",
            "authors",
            "ocr_status",
            "metadata_status",
            "index_status",
            "error_message",
            "updated_at",
        }
        self.assertTrue(expected_cols.issubset(cols))
        self.assertNotIn("document_id", cols)

    def test_migrates_legacy_schema_with_document_id(self) -> None:
        legacy_path = Path(self.tmp_dir.name) / "legacy.db"
        with closing(sqlite3.connect(legacy_path)) as conn:
            conn.execute(
                """
                CREATE TABLE documents (
                    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_pdf TEXT UNIQUE,
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
                    ocr_status TEXT DEFAULT 'pending',
                    metadata_status TEXT DEFAULT 'pending',
                    index_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    updated_at TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                INSERT INTO documents (id_pdf, source_id, pdf_filename, md_filename, ocr_status)
                VALUES ('uuid-123', '2015001', '2015001.pdf', 'uuid-123.md', 'done')
                """
            )
            conn.commit()

        migrated = TrackingDB(legacy_path)
        doc = migrated.get_document("uuid-123")
        assert doc is not None
        self.assertNotIn("document_id", doc)
        self.assertEqual(doc["pdf_filename"], "uuid-123.pdf")
        self.assertEqual(doc["ocr_status"], "done")

    def test_upsert_source_document_initial_insert_uses_uuid_filename(self) -> None:
        id_pdf = self.db.upsert_source_document(
            pdf_filename="apollo11_fire.pdf",
            pdf_url="https://nasa.gov/apollo11_fire.pdf",
            experiment_url="https://nasa.gov/exp/1",
        )
        uuid.UUID(id_pdf)
        doc = self.db.get_document(id_pdf)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(doc["pdf_filename"], f"{id_pdf}.pdf")
        self.assertEqual(doc["ocr_status"], "pending")
        self.assertEqual(doc["metadata_status"], "pending")
        self.assertEqual(doc["index_status"], "pending")

    def test_upsert_source_document_is_idempotent_and_preserves_status(self) -> None:
        id1 = self.db.upsert_source_document(
            pdf_filename="doc1.pdf",
            pdf_url="https://old/doc1.pdf",
            experiment_url="https://old/exp1",
            source_id="src1",
        )
        self.db.mark_stage_done(id1, stage=1, md_filename=f"{id1}.md")

        id2 = self.db.upsert_source_document(
            pdf_filename="doc1.pdf",
            pdf_url="https://new/doc1.pdf",
            experiment_url="https://new/exp1",
            source_id="src1",
        )
        self.assertEqual(id1, id2)
        doc = self.db.get_document(id1)
        assert doc is not None
        self.assertEqual(doc["ocr_status"], "done")
        self.assertEqual(doc["md_filename"], f"{id1}.md")
        self.assertEqual(doc["pdf_url"], "https://new/doc1.pdf")
        self.assertEqual(doc["experiment_url"], "https://new/exp1")

    def test_get_pending_for_stage1_excludes_done_and_error(self) -> None:
        id_pending = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_done = self.db.upsert_source_document("b.pdf", "u2", "e2")
        id_err = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_done, stage=1, md_filename=f"{id_done}.md")
        self.db.mark_stage_error(id_err, stage=1, error_message="OCR failed")

        pending = self.db.get_pending_for_stage(1)
        self.assertEqual([d["id_pdf"] for d in pending], [id_pending])

    def test_get_pending_for_stage1_retry_errors_includes_error(self) -> None:
        id_pending = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_err = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_error(id_err, stage=1, error_message="OCR failed")

        pending = self.db.get_pending_for_stage(1, retry_errors=True)
        self.assertEqual([d["id_pdf"] for d in pending], [id_pending, id_err])

    def test_get_pending_for_stage2_requires_ocr_done(self) -> None:
        id_no_ocr = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_ready = self.db.upsert_source_document("b.pdf", "u2", "e2")
        id_already = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_ready, stage=1, md_filename=f"{id_ready}.md")
        self.db.mark_stage_done(id_already, stage=1, md_filename=f"{id_already}.md")
        self.db.mark_stage_done(
            id_already,
            stage=2,
            mission_program="ISS",
            experiment_year=2020,
            authors="Jane Doe",
        )

        pending = self.db.get_pending_for_stage(2)
        self.assertEqual([d["id_pdf"] for d in pending], [id_ready])
        self.assertNotIn(id_no_ocr, [d["id_pdf"] for d in pending])

    def test_get_pending_for_stage3_requires_metadata_done(self) -> None:
        self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_ocr_only = self.db.upsert_source_document("b.pdf", "u2", "e2")
        self.db.mark_stage_done(id_ocr_only, stage=1, md_filename=f"{id_ocr_only}.md")

        id_ready = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_ready, stage=1, md_filename=f"{id_ready}.md")
        self.db.mark_stage_done(
            id_ready,
            stage=2,
            mission_program="Skylab",
            experiment_year=1973,
            authors="A. Smith",
        )

        pending = self.db.get_pending_for_stage(3)
        self.assertEqual([d["id_pdf"] for d in pending], [id_ready])

    def test_get_pending_respects_limit(self) -> None:
        for i in range(5):
            self.db.upsert_source_document(f"doc{i}.pdf", f"u{i}", f"e{i}")
        pending = self.db.get_pending_for_stage(1, limit=2)
        self.assertEqual(len(pending), 2)

    def test_mark_stage_done_clears_previous_error_and_saves_fields(self) -> None:
        id_pdf = self.db.upsert_source_document("doc.pdf", "u", "e")
        self.db.mark_stage_error(id_pdf, stage=1, error_message="Temporary error")
        self.db.mark_stage_done(id_pdf, stage=1, md_filename=f"{id_pdf}.md")

        doc = self.db.get_document(id_pdf)
        assert doc is not None
        self.assertEqual(doc["ocr_status"], "done")
        self.assertEqual(doc["md_filename"], f"{id_pdf}.md")
        self.assertIsNone(doc["error_message"])

        self.db.mark_stage_done(
            id_pdf,
            stage=2,
            mission_program="Apollo",
            experiment_year=1969,
            authors="N. Armstrong",
        )
        doc = self.db.get_document(id_pdf)
        assert doc is not None
        self.assertEqual(doc["metadata_status"], "done")
        self.assertEqual(doc["mission_program"], "Apollo")
        self.assertEqual(doc["experiment_year"], 1969)
        self.assertEqual(doc["authors"], "N. Armstrong")

    def test_mark_stage_error_does_not_affect_other_documents(self) -> None:
        id1 = self.db.upsert_source_document("d1.pdf", "u1", "e1")
        id2 = self.db.upsert_source_document("d2.pdf", "u2", "e2")
        self.db.mark_stage_error(id1, stage=1, error_message="Corrupt PDF")

        doc1 = self.db.get_document(id1)
        doc2 = self.db.get_document(id2)
        assert doc1 is not None and doc2 is not None
        self.assertEqual(doc1["ocr_status"], "error")
        self.assertEqual(doc1["error_message"], "Corrupt PDF")
        self.assertEqual(doc2["ocr_status"], "pending")
        self.assertIsNone(doc2["error_message"])

    def test_get_stats_returns_exact_counts(self) -> None:
        id1 = self.db.upsert_source_document("d1.pdf", "u1", "e1")
        id2 = self.db.upsert_source_document("d2.pdf", "u2", "e2")
        self.db.upsert_source_document("d3.pdf", "u3", "e3")
        self.db.mark_stage_done(id1, stage=1, md_filename=f"{id1}.md")
        self.db.mark_stage_done(
            id1, stage=2, mission_program="ISS", experiment_year=2021, authors="X"
        )
        self.db.mark_stage_done(id1, stage=3)
        self.db.mark_stage_error(id2, stage=1, error_message="fail")

        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["stage1"], {"pending": 1, "done": 1, "error": 1})
        self.assertEqual(stats["stage2"], {"pending": 2, "done": 1, "error": 0})
        self.assertEqual(stats["stage3"], {"pending": 2, "done": 1, "error": 0})


if __name__ == "__main__":
    unittest.main()
