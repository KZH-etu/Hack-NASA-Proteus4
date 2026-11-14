import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from src.rag.db import TrackingDB


class TestTrackingDB(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "nested" / "tracking.db"
        self.db = TrackingDB(self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_creates_db_file_and_documents_schema(self) -> None:
        self.assertTrue(self.db_path.exists())
        with closing(sqlite3.connect(self.db_path)) as conn:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(documents)").fetchall()
            }
        expected_cols = {
            "document_id",
            "pdf_filename",
            "md_filename",
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

    def test_upsert_source_document_initial_insert(self) -> None:
        doc_id = self.db.upsert_source_document(
            pdf_filename="apollo11_fire.pdf",
            pdf_url="https://nasa.gov/apollo11_fire.pdf",
            experiment_url="https://nasa.gov/exp/1",
        )
        doc = self.db.get_document(doc_id)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(doc["pdf_filename"], "apollo11_fire.pdf")
        self.assertEqual(doc["ocr_status"], "pending")
        self.assertEqual(doc["metadata_status"], "pending")
        self.assertEqual(doc["index_status"], "pending")

    def test_upsert_source_document_is_idempotent_and_preserves_status(self) -> None:
        doc_id1 = self.db.upsert_source_document(
            pdf_filename="doc1.pdf",
            pdf_url="https://old/doc1.pdf",
            experiment_url="https://old/exp1",
        )
        self.db.mark_stage_done(doc_id1, stage=1, md_filename="doc1.md")

        doc_id2 = self.db.upsert_source_document(
            pdf_filename="doc1.pdf",
            pdf_url="https://new/doc1.pdf",
            experiment_url="https://new/exp1",
        )
        self.assertEqual(doc_id1, doc_id2)
        doc = self.db.get_document(doc_id1)
        assert doc is not None
        self.assertEqual(doc["ocr_status"], "done")
        self.assertEqual(doc["md_filename"], "doc1.md")
        self.assertEqual(doc["pdf_url"], "https://new/doc1.pdf")
        self.assertEqual(doc["experiment_url"], "https://new/exp1")

    def test_get_pending_for_stage1_excludes_done_and_error(self) -> None:
        id_pending = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_done = self.db.upsert_source_document("b.pdf", "u2", "e2")
        id_err = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_done, stage=1, md_filename="b.md")
        self.db.mark_stage_error(id_err, stage=1, error_message="OCR failed")

        pending = self.db.get_pending_for_stage(1)
        self.assertEqual([d["document_id"] for d in pending], [id_pending])

    def test_get_pending_for_stage1_retry_errors_includes_error(self) -> None:
        id_pending = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_err = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_error(id_err, stage=1, error_message="OCR failed")

        pending = self.db.get_pending_for_stage(1, retry_errors=True)
        self.assertEqual([d["document_id"] for d in pending], [id_pending, id_err])

    def test_get_pending_for_stage2_requires_ocr_done(self) -> None:
        id_no_ocr = self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_ready = self.db.upsert_source_document("b.pdf", "u2", "e2")
        id_already = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_ready, stage=1, md_filename="b.md")
        self.db.mark_stage_done(id_already, stage=1, md_filename="c.md")
        self.db.mark_stage_done(
            id_already,
            stage=2,
            mission_program="ISS",
            experiment_year=2020,
            authors="Jane Doe",
        )

        pending = self.db.get_pending_for_stage(2)
        self.assertEqual([d["document_id"] for d in pending], [id_ready])
        self.assertNotIn(id_no_ocr, [d["document_id"] for d in pending])

    def test_get_pending_for_stage3_requires_metadata_done(self) -> None:
        self.db.upsert_source_document("a.pdf", "u1", "e1")
        id_ocr_only = self.db.upsert_source_document("b.pdf", "u2", "e2")
        self.db.mark_stage_done(id_ocr_only, stage=1, md_filename="b.md")

        id_ready = self.db.upsert_source_document("c.pdf", "u3", "e3")
        self.db.mark_stage_done(id_ready, stage=1, md_filename="c.md")
        self.db.mark_stage_done(
            id_ready,
            stage=2,
            mission_program="Skylab",
            experiment_year=1973,
            authors="A. Smith",
        )

        pending = self.db.get_pending_for_stage(3)
        self.assertEqual([d["document_id"] for d in pending], [id_ready])

    def test_get_pending_respects_limit(self) -> None:
        for i in range(5):
            self.db.upsert_source_document(f"doc{i}.pdf", f"u{i}", f"e{i}")
        pending = self.db.get_pending_for_stage(1, limit=2)
        self.assertEqual(len(pending), 2)

    def test_mark_stage_done_clears_previous_error_and_saves_fields(self) -> None:
        doc_id = self.db.upsert_source_document("doc.pdf", "u", "e")
        self.db.mark_stage_error(doc_id, stage=1, error_message="Temporary error")
        self.db.mark_stage_done(doc_id, stage=1, md_filename="doc.md")

        doc = self.db.get_document(doc_id)
        assert doc is not None
        self.assertEqual(doc["ocr_status"], "done")
        self.assertEqual(doc["md_filename"], "doc.md")
        self.assertIsNone(doc["error_message"])

        self.db.mark_stage_done(
            doc_id,
            stage=2,
            mission_program="Apollo",
            experiment_year=1969,
            authors="N. Armstrong",
        )
        doc = self.db.get_document(doc_id)
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
        id3 = self.db.upsert_source_document("d3.pdf", "u3", "e3")
        self.db.mark_stage_done(id1, stage=1, md_filename="d1.md")
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
        self.assertEqual(id3, 3)


if __name__ == "__main__":
    unittest.main()
