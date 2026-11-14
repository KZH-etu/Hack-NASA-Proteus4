import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.source_adapter import PlaceholderSourceProvider
from src.rag.stage1_ocr import run as run_stage1


class TestStage1OCR(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
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

    def test_converts_pdfs_to_markdown_and_updates_db(self) -> None:
        (self.config.pdf_dir / "doc1.pdf").write_bytes(b"%PDF-1.4")
        (self.config.pdf_dir / "doc2.pdf").write_bytes(b"%PDF-1.4")

        converter = MagicMock(side_effect=lambda p: f"# Converted {p.name}\n\nBody")
        summary = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=converter,
        )

        self.assertEqual(summary, {"processed": 2, "done": 2, "error": 0})
        self.assertTrue((self.config.md_dir / "doc1.md").exists())
        self.assertTrue((self.config.md_dir / "doc2.md").exists())
        self.assertEqual(
            (self.config.md_dir / "doc1.md").read_text(encoding="utf-8"),
            "# Converted doc1.pdf\n\nBody",
        )
        stats = self.db.get_stats()
        self.assertEqual(stats["stage1"], {"pending": 0, "done": 2, "error": 0})

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

        def fake_convert(path: Path) -> str:
            if path.name == "a_bad.pdf":
                raise RuntimeError("Marker crash")
            return "# Good PDF"

        summary = run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=fake_convert,
        )
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        self.assertFalse((self.config.md_dir / "a_bad.md").exists())
        self.assertTrue((self.config.md_dir / "b_good.md").exists())

    def test_retry_errors_reprocesses_failed_documents(self) -> None:
        (self.config.pdf_dir / "retry.pdf").write_bytes(b"%PDF-1.4")
        fail_converter = MagicMock(side_effect=RuntimeError("Transient OOM"))
        run_stage1(
            self.config,
            source_provider=PlaceholderSourceProvider(self.config.pdf_dir),
            db=self.db,
            converter=fail_converter,
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
