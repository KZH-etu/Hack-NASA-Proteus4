import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from src.rag.config import RagConfig
from src.rag.ingestion.db import TrackingDB
from src.rag.ingestion.source_adapter import PlaceholderSourceProvider, SourceDocument
from src.rag.ingestion.stage1_ocr import run as run_stage1


class TestStage1OCR(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            catalog_csv_path=self.root / "catalog.csv",
            pdf_dir=self.root / "pdfs",
            md_dir=self.root / "markdown",
            tracking_db_path=self.root / "tracking.db",
            chroma_dir=self.root / "chroma_db",
            source_manifest_path=self.root / "source_manifest.json",
        )
        self.config.pdf_dir.mkdir(parents=True)
        self.db = TrackingDB(self.config.tracking_db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_renames_pdfs_to_uuid_converts_to_markdown_and_keeps_metadata(self) -> None:
        raw_dir = self.root / "raw"
        raw_dir.mkdir()
        raw_pdf = raw_dir / "20150023456.pdf"
        raw_pdf.write_bytes(b"%PDF-1.4")

        provider = MagicMock()
        provider.list_documents.return_value = [
            SourceDocument(
                pdf_filename="20150023456.pdf",
                pdf_path=raw_pdf,
                pdf_url="https://ntrs.nasa.gov/20150023456.pdf",
                experiment_url="https://ntrs.nasa.gov/citations/20150023456",
                source_id="20150023456",
                title="FLEX Summary Report",
                authors="Dietrich, D.",
                experiment_year=2015,
                source_type="ntrs",
            )
        ]

        converter = MagicMock(side_effect=lambda p: f"# Converted {p.name}\n\nBody")
        summary = run_stage1(
            self.config,
            source_provider=provider,
            db=self.db,
            converter=converter,
        )

        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 1)
        pending_s2 = self.db.get_pending_for_stage(2)
        doc = pending_s2[0]
        id_pdf = doc["id_pdf"]
        uuid.UUID(id_pdf)

        self.assertEqual(doc["pdf_filename"], f"{id_pdf}.pdf")
        self.assertEqual(doc["md_filename"], f"{id_pdf}.md")
        self.assertEqual(doc["title"], "FLEX Summary Report")
        self.assertEqual(doc["source_type"], "ntrs")
        self.assertEqual(doc["authors"], "Dietrich, D.")
        self.assertEqual(doc["experiment_year"], 2015)

        self.assertTrue((self.config.pdf_dir / f"{id_pdf}.pdf").exists())
        self.assertTrue((self.config.md_dir / f"{id_pdf}.md").exists())
        self.assertTrue(raw_pdf.exists())

    def test_fallback_uses_pages_jsonl_when_marker_fails(self) -> None:
        pages_dir = self.root / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "20210011385.jsonl").write_text(
            json.dumps({"page": 1, "label": "1", "text": "Fallback page text"}) + "\n",
            encoding="utf-8",
        )
        raw_pdf = self.root / "20210011385.pdf"
        raw_pdf.write_bytes(b"%PDF-1.4")

        provider = MagicMock()
        provider.list_documents.return_value = [
            SourceDocument(
                pdf_filename="20210011385.pdf",
                pdf_path=raw_pdf,
                pdf_url="https://ntrs.nasa.gov/20210011385.pdf",
                experiment_url="https://ntrs.nasa.gov/citations/20210011385",
                source_id="20210011385",
                title="BASS-II Report",
                source_type="ntrs",
            )
        ]

        converter = MagicMock(side_effect=RuntimeError("'NoneType' object is not iterable"))
        summary = run_stage1(
            self.config,
            source_provider=provider,
            db=self.db,
            converter=converter,
            fallback_on_error=True,
        )
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        doc = self.db.get_pending_for_stage(2)[0]
        md_content = (self.config.md_dir / doc["md_filename"]).read_text(encoding="utf-8")
        self.assertIn("Fallback page text", md_content)

    def test_idempotent_skips_already_done_documents(self) -> None:
        (self.config.pdf_dir / "doc1.pdf").write_bytes(b"%PDF-1.4")
        converter = MagicMock(return_value="# Content")

        run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=converter,
        )
        summary2 = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=converter,
        )
        self.assertEqual(converter.call_count, 1)
        self.assertEqual(summary2, {"processed": 0, "done": 0, "error": 0})

    def test_error_isolation_continues_batch_on_failure(self) -> None:
        (self.config.pdf_dir / "a_bad.pdf").write_bytes(b"%PDF-1.4")
        (self.config.pdf_dir / "b_good.pdf").write_bytes(b"%PDF-1.4")

        call_index = {"n": 0}

        def fake_convert(path: Path) -> str:
            call_index["n"] += 1
            if call_index["n"] == 1:
                raise RuntimeError("Marker crash")
            return "# Good PDF"

        summary = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=fake_convert,
            fallback_on_error=False,
        )
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        self.assertEqual(len(list(self.config.md_dir.glob("*.md"))), 1)

    def test_retry_errors_reprocesses_failed_documents(self) -> None:
        (self.config.pdf_dir / "retry.pdf").write_bytes(b"%PDF-1.4")
        fail_converter = MagicMock(side_effect=RuntimeError("Transient OOM"))
        run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=fail_converter,
            fallback_on_error=False,
        )

        ok_converter = MagicMock(return_value="# Recovered")
        summary = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=ok_converter,
            retry_errors=True,
        )
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        stats = self.db.get_stats()
        self.assertEqual(stats["stage1"], {"pending": 0, "done": 1, "error": 0})

    def test_respects_limit(self) -> None:
        for i in range(3):
            (self.config.pdf_dir / f"doc{i}.pdf").write_bytes(b"%PDF-1.4")

        converter = MagicMock(return_value="# OK")
        summary = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=converter,
            limit=2,
        )
        self.assertEqual(summary, {"processed": 2, "done": 2, "error": 0})
        self.assertEqual(converter.call_count, 2)


if __name__ == "__main__":
    unittest.main()
