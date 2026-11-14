import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.llm_client import DocumentMetadata
from src.rag.stage2_metadata import run as run_stage2


class TestStage2Metadata(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            pdf_dir=self.root / "pdfs",
            md_dir=self.root / "markdown",
            tracking_db_path=self.root / "tracking.db",
            chroma_dir=self.root / "chroma_db",
            source_manifest_path=self.root / "source_manifest.json",
            metadata_char_limit=3000,
        )
        self.config.md_dir.mkdir(parents=True)
        self.db = TrackingDB(self.config.tracking_db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _seed_ocr_done(self, name: str, content: str | None) -> int:
        doc_id = self.db.upsert_source_document(
            f"{name}.pdf",
            f"https://nasa.gov/{name}.pdf",
            f"https://nasa.gov/exp/{name}",
        )
        md_name = f"{name}.md"
        if content is not None:
            (self.config.md_dir / md_name).write_text(content, encoding="utf-8")
        self.db.mark_stage_done(doc_id, stage=1, md_filename=md_name)
        return doc_id

    def test_truncates_markdown_to_3000_chars_and_saves_metadata(self) -> None:
        long_text = "A" * 5000
        doc_id = self._seed_ocr_done("long_doc", long_text)

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="Apollo", experiment_year=1972, authors="J. Doe"
        )

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client)
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        excerpt_sent = llm_client.extract_metadata_json.call_args.args[0]
        self.assertEqual(len(excerpt_sent), 3000)

        doc = self.db.get_document(doc_id)
        assert doc is not None
        self.assertEqual(doc["metadata_status"], "done")
        self.assertEqual(doc["mission_program"], "Apollo")
        self.assertEqual(doc["experiment_year"], 1972)
        self.assertEqual(doc["authors"], "J. Doe")

    def test_missing_markdown_file_marks_error_and_continues(self) -> None:
        id_missing = self._seed_ocr_done("missing_md", None)
        id_ok = self._seed_ocr_done("ok_md", "# Valid Markdown")

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="ISS", experiment_year=2020, authors="A. Smith"
        )

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client)
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        doc_missing = self.db.get_document(id_missing)
        doc_ok = self.db.get_document(id_ok)
        assert doc_missing is not None and doc_ok is not None
        self.assertEqual(doc_missing["metadata_status"], "error")
        self.assertEqual(doc_ok["metadata_status"], "done")

    def test_llm_error_marks_document_error_and_continues(self) -> None:
        id_bad = self._seed_ocr_done("bad_llm", "# Doc 1")
        id_ok = self._seed_ocr_done("ok_llm", "# Doc 2")

        llm_client = MagicMock()
        llm_client.extract_metadata_json.side_effect = [
            ValueError("Invalid JSON"),
            DocumentMetadata(mission_program="Skylab", experiment_year=1974, authors="B. Lee"),
        ]

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client)
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        self.assertEqual(self.db.get_document(id_bad)["metadata_status"], "error")  # type: ignore[index]
        self.assertEqual(self.db.get_document(id_ok)["metadata_status"], "done")  # type: ignore[index]

    def test_aborts_immediately_if_lm_studio_unreachable(self) -> None:
        self._seed_ocr_done("doc1", "# Doc")
        llm_client = MagicMock()
        llm_client.check_connection.side_effect = ConnectionError("LM Studio down")

        with self.assertRaises(ConnectionError):
            run_stage2(self.config, db=self.db, llm_client=llm_client)
        llm_client.extract_metadata_json.assert_not_called()

    def test_respects_limit(self) -> None:
        self._seed_ocr_done("d1", "# 1")
        self._seed_ocr_done("d2", "# 2")
        self._seed_ocr_done("d3", "# 3")
        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="ISS", experiment_year=2021, authors="X"
        )

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client, limit=2)
        self.assertEqual(summary, {"processed": 2, "done": 2, "error": 0})
        self.assertEqual(llm_client.extract_metadata_json.call_count, 2)


if __name__ == "__main__":
    unittest.main()
