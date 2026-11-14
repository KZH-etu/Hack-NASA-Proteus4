import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.rag.source_adapter import (
    CatalogSourceProvider,
    PlaceholderSourceProvider,
    deduce_source_type,
)


class TestDeduceSourceType(unittest.TestCase):
    def test_deduces_ntrs_taskbook_psi_and_autres(self) -> None:
        self.assertEqual(
            deduce_source_type("https://ntrs.nasa.gov/citations/20150023456"), "ntrs"
        )
        self.assertEqual(
            deduce_source_type("https://taskbook.nasaprs.com/tbp/index.cfm?TASKID=123"),
            "taskbook",
        )
        self.assertEqual(
            deduce_source_type("https://psi.nasa.gov/physci/repo/data/investigations/PSI-25"),
            "psi",
        )
        self.assertEqual(
            deduce_source_type("https://www.nasa.gov/glenn/combustion-science/"),
            "autres",
        )
        self.assertEqual(deduce_source_type(None), "autres")


class TestCatalogSourceProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.catalog_path = self.root / "catalog.csv"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_reads_valid_pdfs_and_deduces_source_type(self) -> None:
        pdf1 = self.root / "data" / "raw" / "ntrs" / "pdf" / "20150023456.pdf"
        pdf2 = self.root / "data" / "raw" / "psi" / "PSI-25" / "doc.pdf"
        html1 = self.root / "data" / "raw" / "ntrs" / "web" / "page.html"
        for p in (pdf1, pdf2, html1):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"%PDF-1.4")

        with self.catalog_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["id", "title", "authors", "year", "url", "pdf_url", "pdf_path"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "id": "20150023456",
                    "title": "FLEX Report",
                    "authors": "Dietrich, D.",
                    "year": "2015",
                    "url": "https://ntrs.nasa.gov/citations/20150023456",
                    "pdf_url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf",
                    "pdf_path": "data/raw/ntrs/pdf/20150023456.pdf",
                }
            )
            writer.writerow(
                {
                    "id": "psi-PSI-25-0001",
                    "title": "BASS-II PMMA",
                    "authors": "Olson, S.",
                    "year": "2018",
                    "url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25",
                    "pdf_url": "",
                    "pdf_path": "data/raw/psi/PSI-25/doc.pdf",
                }
            )
            writer.writerow(
                {
                    "id": "web-1",
                    "title": "Web Page",
                    "authors": "NASA",
                    "year": "2022",
                    "url": "https://www.nasa.gov/page",
                    "pdf_url": "",
                    "pdf_path": "data/raw/ntrs/web/page.html",
                }
            )
            writer.writerow(
                {
                    "id": "missing-pdf",
                    "title": "Missing",
                    "authors": "",
                    "year": "",
                    "url": "https://ntrs.nasa.gov/citations/999",
                    "pdf_url": "",
                    "pdf_path": "data/raw/ntrs/pdf/missing.pdf",
                }
            )

        provider_all = CatalogSourceProvider(self.catalog_path, base_dir=self.root)
        docs = provider_all.list_documents()
        self.assertEqual(len(docs), 3)

        provider_pdfs = CatalogSourceProvider(
            self.catalog_path, base_dir=self.root, extensions=(".pdf",)
        )
        docs = provider_pdfs.list_documents()
        self.assertEqual(len(docs), 2)

        self.assertEqual(docs[0].source_id, "20150023456")
        self.assertEqual(docs[0].title, "FLEX Report")
        self.assertEqual(docs[0].authors, "Dietrich, D.")
        self.assertEqual(docs[0].experiment_year, 2015)
        self.assertEqual(docs[0].source_type, "ntrs")

        self.assertEqual(docs[1].source_id, "psi-PSI-25-0001")
        self.assertEqual(docs[1].source_type, "psi")
        self.assertEqual(
            docs[1].pdf_url,
            "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25",
        )

    def test_missing_catalog_raises_file_not_found(self) -> None:
        provider = CatalogSourceProvider(self.catalog_path, base_dir=self.root)
        with self.assertRaises(FileNotFoundError):
            provider.list_documents()


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
