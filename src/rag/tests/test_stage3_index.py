import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import chromadb

from src.rag.config import RagConfig
from src.rag.db import TrackingDB
from src.rag.stage3_index import build_chroma_metadata, chunk_markdown, run as run_stage3


class TestStage3Index(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            pdf_dir=self.root / "pdfs",
            md_dir=self.root / "markdown",
            tracking_db_path=self.root / "tracking.db",
            chroma_dir=self.root / "chroma_db",
            source_manifest_path=self.root / "source_manifest.json",
            chunk_size=1000,
            chunk_overlap=200,
        )
        self.config.md_dir.mkdir(parents=True)
        self.db = TrackingDB(self.config.tracking_db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _seed_ready_doc(
        self,
        name: str,
        md_content: str,
        mission_program: str | None = "ISS",
        experiment_year: int | None = 2020,
        authors: str | None = "Jane Doe",
    ) -> int:
        doc_id = self.db.upsert_source_document(
            f"{name}.pdf",
            f"https://nasa.gov/{name}.pdf",
            f"https://nasa.gov/exp/{name}",
        )
        (self.config.md_dir / f"{name}.md").write_text(md_content, encoding="utf-8")
        self.db.mark_stage_done(doc_id, stage=1, md_filename=f"{name}.md")
        self.db.mark_stage_done(
            doc_id,
            stage=2,
            mission_program=mission_program,
            experiment_year=experiment_year,
            authors=authors,
        )
        return doc_id

    def test_chunk_markdown_builds_breadcrumb_and_context_format(self) -> None:
        md = "# 1. Intro\n\n## 1.2 Objectifs\n\nEtude de flamme en microgravite."
        chunks = chunk_markdown(md, chunk_size=1000, chunk_overlap=200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["headers_path"], "1. Intro > 1.2 Objectifs")
        self.assertEqual(
            chunks[0]["document_text"],
            "Contexte : 1. Intro > 1.2 Objectifs\nTexte : Etude de flamme en microgravite.",
        )

    def test_chunk_markdown_without_headers_uses_document_fallback(self) -> None:
        md = "Paragraphe brut sans aucun titre markdown."
        chunks = chunk_markdown(md, chunk_size=1000, chunk_overlap=200)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["headers_path"], "Document")
        self.assertTrue(chunks[0]["document_text"].startswith("Contexte : Document\nTexte : "))

    def test_chunk_markdown_splits_long_section_with_overlap(self) -> None:
        words = " ".join(f"word{i}" for i in range(450))
        md = f"# Section Longue\n\n{words}"
        chunks = chunk_markdown(md, chunk_size=1000, chunk_overlap=200)
        self.assertGreater(len(chunks), 1)
        for ch in chunks:
            self.assertEqual(ch["headers_path"], "Section Longue")
            self.assertLessEqual(len(ch["content"]), 1000)

    def test_build_chroma_metadata_sanitizes_none_values(self) -> None:
        doc_row = {
            "document_id": 7,
            "mission_program": None,
            "experiment_year": None,
            "authors": None,
            "pdf_url": None,
            "experiment_url": "https://nasa.gov/exp/7",
        }
        meta = build_chroma_metadata(doc_row, chunk_index=0, headers_path="Intro")
        expected_keys = {
            "document_id",
            "chunk_index",
            "headers_path",
            "mission_program",
            "experiment_year",
            "authors",
            "pdf_url",
            "experiment_url",
        }
        self.assertEqual(set(meta.keys()), expected_keys)
        for val in meta.values():
            self.assertIsNotNone(val)
            self.assertIsInstance(val, (str, int, float, bool))

    def test_indexes_chunks_into_real_chromadb_with_uuid_and_metadata(self) -> None:
        doc_id = self._seed_ready_doc(
            "apollo_flame",
            "# 1. Intro\n\n## 1.1 Setup\n\nTexte un.\n\n## 1.2 Results\n\nTexte deux.",
            mission_program="Apollo",
            experiment_year=1971,
            authors="J. Doe",
        )

        llm_client = MagicMock()
        llm_client.embed_texts.side_effect = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
        chroma_client = chromadb.PersistentClient(path=str(self.config.chroma_dir))

        summary = run_stage3(
            self.config,
            db=self.db,
            llm_client=llm_client,
            chroma_client=chroma_client,
        )
        self.assertEqual(summary, {"processed": 1, "done": 1, "error": 0})

        collection = chroma_client.get_collection(self.config.chroma_collection)
        result = collection.get(include=["documents", "metadatas", "embeddings"])
        self.assertEqual(len(result["ids"]), 2)
        for cid in result["ids"]:
            uuid.UUID(cid)  # Must be valid UUID

        self.assertEqual(result["metadatas"][0]["document_id"], doc_id)
        self.assertEqual(result["metadatas"][0]["chunk_index"], 0)
        self.assertEqual(result["metadatas"][0]["headers_path"], "1. Intro > 1.1 Setup")
        self.assertEqual(result["metadatas"][1]["chunk_index"], 1)
        self.assertEqual(result["metadatas"][1]["headers_path"], "1. Intro > 1.2 Results")
        self.assertEqual(result["metadatas"][0]["mission_program"], "Apollo")
        self.assertEqual(result["metadatas"][0]["experiment_year"], 1971)
        self.assertEqual(self.db.get_document(doc_id)["index_status"], "done")  # type: ignore[index]

    def test_reindexing_same_document_replaces_old_chunks_without_duplicates(self) -> None:
        doc_id = self._seed_ready_doc("doc_reindex", "# Intro\n\nFirst version.")
        llm_client = MagicMock()
        llm_client.embed_texts.side_effect = lambda texts: [[0.5, 0.5] for _ in texts]
        chroma_client = chromadb.PersistentClient(path=str(self.config.chroma_dir))

        run_stage3(self.config, db=self.db, llm_client=llm_client, chroma_client=chroma_client)

        # Simulate error & retry on the same document with updated markdown
        self.db.mark_stage_error(doc_id, stage=3, error_message="Force reindex")
        (self.config.md_dir / "doc_reindex.md").write_text(
            "# Intro\n\nSecond version.", encoding="utf-8"
        )
        run_stage3(
            self.config,
            db=self.db,
            llm_client=llm_client,
            chroma_client=chroma_client,
            retry_errors=True,
        )

        collection = chroma_client.get_collection(self.config.chroma_collection)
        result = collection.get(where={"document_id": doc_id})
        self.assertEqual(len(result["ids"]), 1)
        self.assertIn("Second version.", result["documents"][0])

    def test_embedding_failure_marks_error_and_continues_batch(self) -> None:
        id_bad = self._seed_ready_doc("bad_embed", "# A\n\nText A")
        id_ok = self._seed_ready_doc("ok_embed", "# B\n\nText B")

        llm_client = MagicMock()
        llm_client.embed_texts.side_effect = [
            RuntimeError("Embedding API timeout"),
            [[0.1, 0.2]],
        ]
        chroma_client = chromadb.PersistentClient(path=str(self.config.chroma_dir))

        summary = run_stage3(
            self.config,
            db=self.db,
            llm_client=llm_client,
            chroma_client=chroma_client,
        )
        self.assertEqual(summary, {"processed": 2, "done": 1, "error": 1})
        self.assertEqual(self.db.get_document(id_bad)["index_status"], "error")  # type: ignore[index]
        self.assertEqual(self.db.get_document(id_ok)["index_status"], "done")  # type: ignore[index]

    def test_aborts_immediately_if_lm_studio_unreachable(self) -> None:
        self._seed_ready_doc("doc", "# A\n\nText")
        llm_client = MagicMock()
        llm_client.check_connection.side_effect = ConnectionError("LM Studio down")
        chroma_client = chromadb.PersistentClient(path=str(self.config.chroma_dir))

        with self.assertRaises(ConnectionError):
            run_stage3(
                self.config,
                db=self.db,
                llm_client=llm_client,
                chroma_client=chroma_client,
            )
        llm_client.embed_texts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
