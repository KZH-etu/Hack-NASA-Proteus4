import json
import tempfile
import unittest
from pathlib import Path

from src.rag.source_adapter import PlaceholderSourceProvider


class TestPlaceholderSourceProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.pdf_dir = self.root / "pdfs"
        self.manifest_path = self.root / "source_manifest.json"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_nonexistent_pdf_dir_returns_empty_list(self) -> None:
        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        self.assertEqual(provider.list_documents(), [])

    def test_empty_pdf_dir_returns_empty_list(self) -> None:
        self.pdf_dir.mkdir(parents=True)
        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        self.assertEqual(provider.list_documents(), [])

    def test_filters_only_pdf_files_sorted(self) -> None:
        self.pdf_dir.mkdir(parents=True)
        (self.pdf_dir / "b_report.pdf").write_bytes(b"%PDF-1.4")
        (self.pdf_dir / "a_report.pdf").write_bytes(b"%PDF-1.4")
        (self.pdf_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
        (self.pdf_dir / "readme.md").write_text("# ignore", encoding="utf-8")
        (self.pdf_dir / "subdir").mkdir()

        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        docs = provider.list_documents()
        self.assertEqual([d.pdf_filename for d in docs], ["a_report.pdf", "b_report.pdf"])

    def test_without_manifest_generates_deterministic_placeholder_urls(self) -> None:
        self.pdf_dir.mkdir(parents=True)
        (self.pdf_dir / "apollo_test.pdf").write_bytes(b"%PDF-1.4")

        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        docs = provider.list_documents()
        self.assertEqual(len(docs), 1)
        self.assertEqual(
            docs[0].pdf_url, "https://placeholder.nasa.gov/pdfs/apollo_test.pdf"
        )
        self.assertEqual(
            docs[0].experiment_url,
            "https://placeholder.nasa.gov/experiments/apollo_test",
        )

    def test_with_partial_manifest_merges_real_and_placeholder_urls(self) -> None:
        self.pdf_dir.mkdir(parents=True)
        (self.pdf_dir / "known.pdf").write_bytes(b"%PDF-1.4")
        (self.pdf_dir / "unknown.pdf").write_bytes(b"%PDF-1.4")
        self.manifest_path.write_text(
            json.dumps(
                {
                    "known.pdf": {
                        "pdf_url": "https://ntrs.nasa.gov/citations/1999001",
                        "experiment_url": "https://psi.nasa.gov/exp/42",
                    }
                }
            ),
            encoding="utf-8",
        )

        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        docs = {d.pdf_filename: d for d in provider.list_documents()}
        self.assertEqual(
            docs["known.pdf"].pdf_url, "https://ntrs.nasa.gov/citations/1999001"
        )
        self.assertEqual(
            docs["known.pdf"].experiment_url, "https://psi.nasa.gov/exp/42"
        )
        self.assertEqual(
            docs["unknown.pdf"].pdf_url,
            "https://placeholder.nasa.gov/pdfs/unknown.pdf",
        )

    def test_invalid_manifest_json_raises_value_error(self) -> None:
        self.pdf_dir.mkdir(parents=True)
        (self.pdf_dir / "doc.pdf").write_bytes(b"%PDF-1.4")
        self.manifest_path.write_text("{not valid json", encoding="utf-8")

        provider = PlaceholderSourceProvider(self.pdf_dir, self.manifest_path)
        with self.assertRaises(ValueError):
            provider.list_documents()


if __name__ == "__main__":
    unittest.main()
