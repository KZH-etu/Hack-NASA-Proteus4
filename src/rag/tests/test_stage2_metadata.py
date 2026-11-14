import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.rag.config import RagConfig
from src.rag.ingestion.db import TrackingDB
from src.rag.ingestion.source_adapter import SourceDocument
from src.rag.ingestion.stage2_metadata import run as run_stage2
from src.rag.ingestion.text_utils import html_to_clean_markdown, strip_html_tags
from src.rag.llm_client import DocumentMetadata


class TestStage2Metadata(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            catalog_csv_path=self.root / "missing_catalog.csv",
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

    def _seed_ocr_done(self, name: str, content: str | None) -> str:
        id_pdf = self.db.upsert_source_document(
            f"{name}.pdf",
            f"https://nasa.gov/{name}.pdf",
            f"https://nasa.gov/exp/{name}",
            source_id=name,
        )
        md_name = f"{id_pdf}.md"
        if content is not None:
            (self.config.md_dir / md_name).write_text(content, encoding="utf-8")
        self.db.mark_stage_done(id_pdf, stage=1, md_filename=md_name)
        return id_pdf

    def test_html_to_clean_markdown_preserves_headings_and_removes_all_tags(self) -> None:
        raw_html = """
        <html><head><script>alert(1)</script><style>body{}</style></head>
        <body>
          <nav>Menu</nav>
          <main>
            <h1>1. Intro</h1>
            <p>Hello <b>world</b> &amp; microgravity.</p>
            <h2>1.2 Objectifs</h2>
            <ul><li>Item A</li><li>Item B</li></ul>
          </main>
        </body></html>
        """
        md = html_to_clean_markdown(raw_html)
        self.assertIn("# 1. Intro", md)
        self.assertIn("## 1.2 Objectifs", md)
        self.assertIn("- Item A", md)
        self.assertNotIn("<", md)
        self.assertNotIn(">", md)
        self.assertNotIn("alert(1)", md)
        self.assertNotIn("Menu", md)

    def test_ingests_html_before_metadata_and_strips_tags_for_llm(self) -> None:
        html_path = self.root / "web-apollo.html"
        html_path.write_text(
            "<html><body><main><h1>Apollo 1</h1><p>Fire <em>safety</em> report.</p></main></body></html>",
            encoding="utf-8",
        )
        non_pdf_provider = MagicMock()
        non_pdf_provider.list_documents.return_value = [
            SourceDocument(
                pdf_filename="web-apollo.html",
                pdf_path=html_path,
                pdf_url="https://sma.nasa.gov/apollo-1",
                experiment_url="https://sma.nasa.gov/apollo-1",
                source_id="web-apollo",
                title="Apollo 1",
                source_type="autres",
                file_ext=".html",
            )
        ]

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="Apollo", experiment_year=1967, authors="NASA"
        )

        summary = run_stage2(
            self.config,
            db=self.db,
            llm_client=llm_client,
            non_pdf_provider=non_pdf_provider,
        )
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        sent_excerpt = llm_client.extract_metadata_json.call_args.args[0]
        self.assertNotIn("<", sent_excerpt)
        self.assertIn("# Apollo 1", sent_excerpt)
        self.assertIn("Fire safety report.", sent_excerpt)

    def test_truncates_markdown_to_3000_chars_and_saves_metadata(self) -> None:
        long_text = "A" * 5000
        id_pdf = self._seed_ocr_done("long_doc", long_text)

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="Apollo", experiment_year=1972, authors="J. Doe"
        )

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client)
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})
        excerpt_sent = llm_client.extract_metadata_json.call_args.args[0]
        self.assertEqual(len(excerpt_sent), 3000)

        doc = self.db.get_document(id_pdf)
        assert doc is not None
        self.assertEqual(doc["metadata_status"], "done")
        self.assertEqual(doc["mission_program"], "Apollo")
        self.assertEqual(doc["experiment_year"], 1972)
        self.assertEqual(doc["authors"], "J. Doe")

    def test_preserves_existing_db_metadata_over_llm_output(self) -> None:
        id_pdf = self.db.upsert_source_document(
            "cat.pdf",
            "https://ntrs.nasa.gov/cat.pdf",
            "https://ntrs.nasa.gov/citations/1",
            source_id="1",
            title="Catalog Title",
            source_type="ntrs",
            authors="Catalog Author",
            experiment_year=2015,
        )
        (self.config.md_dir / f"{id_pdf}.md").write_text("# Report", encoding="utf-8")
        self.db.mark_stage_done(id_pdf, stage=1, md_filename=f"{id_pdf}.md")

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="ISS", experiment_year=1999, authors="Wrong LLM Author"
        )
        run_stage2(self.config, db=self.db, llm_client=llm_client)

        doc = self.db.get_document(id_pdf)
        assert doc is not None
        self.assertEqual(doc["mission_program"], "ISS")
        self.assertEqual(doc["experiment_year"], 2015)
        self.assertEqual(doc["authors"], "Catalog Author")

    def test_missing_markdown_file_marks_error_and_continues(self) -> None:
        id_missing = self._seed_ocr_done("missing_md", None)
        id_ok = self._seed_ocr_done("ok_md", "# Valid Markdown")

        llm_client = MagicMock()
        llm_client.extract_metadata_json.return_value = DocumentMetadata(
            mission_program="ISS", experiment_year=2020, authors="A. Smith"
        )

        summary = run_stage2(self.config, db=self.db, llm_client=llm_client)
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        self.assertEqual(self.db.get_document(id_missing)["metadata_status"], "error")  # type: ignore[index]
        self.assertEqual(self.db.get_document(id_ok)["metadata_status"], "done")  # type: ignore[index]

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

    def test_strip_html_tags_helper(self) -> None:
        self.assertEqual(strip_html_tags("<p>Hello <b>NASA</b></p>"), "Hello NASA")


if __name__ == "__main__":
    unittest.main()
