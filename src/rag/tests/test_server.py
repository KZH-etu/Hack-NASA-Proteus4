import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import chromadb
from fastapi.testclient import TestClient

from src.rag.config import RagConfig
from src.rag.server.app import _merge_adjacent_texts, create_app
from src.rag.storage.chroma_release import SyncResult


class TestRagServer(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            chroma_dir=self.root / "chroma_db",
            chroma_collection="nasa_scientific_reports",
        )
        self.chroma_client = chromadb.PersistentClient(path=str(self.config.chroma_dir))
        collection = self.chroma_client.get_or_create_collection(
            name=self.config.chroma_collection
        )
        base_meta = {
            "id_pdf": "uuid-1234",
            "title": "FLEX Droplet Report",
            "source_type": "ntrs",
            "headers_path": "Results > Extinction",
            "mission_program": "ISS",
            "experiment_year": 2015,
            "authors": "Alice Smith",
            "pdf_url": "https://ntrs.nasa.gov/1234.pdf",
            "experiment_url": "https://ntrs.nasa.gov/citations/1234",
        }
        overlap = "shared overlap sentence across chunk boundary"
        collection.add(
            ids=["c0", "c1", "c2", "c3", "other-doc"],
            documents=[
                f"Contexte : Intro\nTexte : Chunk zero before {overlap}",
                f"Contexte : Results > Extinction\nTexte : {overlap} hit chunk one middle.",
                "Contexte : Results > Extinction\nTexte : Chunk two right after hit.",
                "Contexte : Conclusion\nTexte : Chunk three far away.",
                "Contexte : Other\nTexte : Unrelated document chunk.",
            ],
            embeddings=[
                [0.1, 0.9, 0.0],
                [1.0, 0.0, 0.0],  # Exact match for query [1, 0, 0]
                [0.2, 0.8, 0.0],
                [0.0, 0.1, 0.9],
                [0.0, 0.0, 1.0],
            ],
            metadatas=[
                {**base_meta, "chunk_index": 0, "headers_path": "Intro"},
                {**base_meta, "chunk_index": 1},
                {**base_meta, "chunk_index": 2},
                {**base_meta, "chunk_index": 3, "headers_path": "Conclusion"},
                {
                    **base_meta,
                    "id_pdf": "uuid-other",
                    "title": "Other Paper",
                    "chunk_index": 0,
                },
            ],
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_merge_adjacent_texts_deduplicates_overlap(self) -> None:
        merged = _merge_adjacent_texts(
            [
                "Alpha beta gamma common overlap segment here.",
                "common overlap segment here. Delta epsilon.",
            ]
        )
        self.assertEqual(merged, "Alpha beta gamma common overlap segment here. Delta epsilon.")

    def test_lifespan_runs_sync_health_and_retrieve_returns_concatenated_strings(self) -> None:
        sync_calls: list[RagConfig] = []

        def fake_sync(cfg: RagConfig) -> SyncResult:
            sync_calls.append(cfg)
            return SyncResult(
                status="up_to_date",
                tag_name="chroma-db-v20261114-203450",
                chunk_count=5,
                chroma_dir=cfg.chroma_dir,
                message="OK",
            )

        llm_client = MagicMock()
        llm_client.embed_texts.return_value = [[1.0, 0.0, 0.0]]

        app = create_app(
            self.config,
            sync_fn=fake_sync,
            chroma_client=self.chroma_client,
            llm_client=llm_client,
            skip_sync=False,
        )

        with TestClient(app) as client:
            self.assertEqual(len(sync_calls), 1)

            health_resp = client.get("/health")
            self.assertEqual(health_resp.status_code, 200)
            health_data = health_resp.json()
            self.assertEqual(health_data["status"], "ok")
            self.assertEqual(health_data["sync_status"], "up_to_date")
            self.assertEqual(health_data["release_tag"], "chroma-db-v20261114-203450")
            self.assertEqual(health_data["chunk_count"], 5)

            # Default neighbors=1 -> fetches chunk 0 + chunk 1 + chunk 2 for hit c1
            ret_resp = client.post("/retrieve", json={"query": "droplet burning", "top_k": 1})
            self.assertEqual(ret_resp.status_code, 200)
            results = ret_resp.json()
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 1)
            hit = results[0]
            ctx = hit["context_block"]
            text = hit["text"]
            meta = hit["metadata"]
            self.assertIn("Document : FLEX Droplet Report", ctx)
            self.assertIn("Auteurs : Alice Smith | Mission : ISS | Année : 2015 | Source : ntrs", ctx)
            self.assertIn("Chunk zero before", text)
            self.assertIn("hit chunk one middle.", text)
            self.assertIn("Chunk two right after hit.", text)
            # Ensure overlap wasn't duplicated twice
            self.assertEqual(text.count("shared overlap sentence across chunk boundary"), 1)
            # Chunk 3 and other doc must NOT be included
            self.assertNotIn("Chunk three far away.", text)
            self.assertNotIn("Unrelated document chunk.", text)
            self.assertEqual(meta["title"], "FLEX Droplet Report")
            self.assertEqual(meta["authors"], "Alice Smith")
            self.assertEqual(meta["mission_program"], "ISS")
            self.assertEqual(meta["experiment_year"], 2015)
            self.assertEqual(meta["source_type"], "ntrs")
            self.assertEqual(meta["headers_path"], "Results > Extinction")
            self.assertEqual(meta["pdf_url"], "https://ntrs.nasa.gov/1234.pdf")
            self.assertEqual(meta["experiment_url"], "https://ntrs.nasa.gov/citations/1234")

            # neighbors=0 returns only hit chunk 1
            no_neighbor_resp = client.post(
                "/retrieve",
                json={"query": "droplet burning", "top_k": 1, "neighbors": 0},
            )
            self.assertEqual(no_neighbor_resp.status_code, 200)
            single_text = no_neighbor_resp.json()[0]["text"]
            self.assertIn("hit chunk one middle.", single_text)
            self.assertNotIn("Chunk zero before", single_text)
            self.assertNotIn("Chunk two right after hit.", single_text)

    def test_rag_config_separates_webapp_and_preprocessing_endpoints(self) -> None:
        env = {
            "QWEN3_EMBEDDING": "secret-bearer-token",
            "WEBAPP_EMBEDDING_BASE_URL": "https://ai.derveloy.eu/v1",
            "WEBAPP_EMBEDDING_MODEL": "qwen3-embedding:0.6b",
            "LM_STUDIO_BASE_URL": "http://localhost:1234/v1",
            "LM_STUDIO_API_KEY": "lm-studio",
            "RAG_EMBEDDING_MODEL": "text-embedding-qwen3-embedding-0.6b",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RagConfig.from_env()
        self.assertEqual(cfg.webapp_embedding_base_url, "https://ai.derveloy.eu/v1")
        self.assertEqual(cfg.webapp_embedding_api_key, "secret-bearer-token")
        self.assertEqual(cfg.webapp_embedding_model, "qwen3-embedding:0.6b")
        self.assertEqual(cfg.lm_studio_base_url, "http://localhost:1234/v1")
        self.assertEqual(cfg.lm_studio_api_key, "lm-studio")
        self.assertEqual(cfg.embedding_model, "text-embedding-qwen3-embedding-0.6b")

    def test_rag_server_uses_webapp_embedding_endpoint_not_lm_studio(self) -> None:
        cfg = RagConfig(
            chroma_dir=self.root / "chroma_db",
            chroma_collection="nasa_scientific_reports",
            lm_studio_base_url="http://localhost:1234/v1",
            lm_studio_api_key="lm-studio",
            embedding_model="text-embedding-qwen3-embedding-0.6b",
            webapp_embedding_base_url="https://ai.derveloy.eu/v1",
            webapp_embedding_api_key="test-token",
            webapp_embedding_model="qwen3-embedding:0.6b",
        )
        with patch("src.rag.server.app.LMStudioClient") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.embed_texts.return_value = [[1.0, 0.0, 0.0]]
            mock_client_cls.return_value = mock_instance

            app = create_app(cfg, chroma_client=self.chroma_client, skip_sync=True)
            with TestClient(app) as client:
                resp = client.post("/retrieve", json={"query": "droplet burning", "top_k": 1})
                self.assertEqual(resp.status_code, 200)

            mock_client_cls.assert_called_once_with(
                base_url="https://ai.derveloy.eu/v1",
                api_key="test-token",
                metadata_model=cfg.metadata_model,
                embedding_model="qwen3-embedding:0.6b",
                embedding_batch_size=cfg.embedding_batch_size,
            )

    def test_ingestion_stages_use_local_lm_studio_only(self) -> None:
        from src.rag.ingestion.db import TrackingDB
        from src.rag.ingestion.stage2_metadata import run as run_stage2
        from src.rag.ingestion.stage3_index import run as run_stage3

        cfg = RagConfig(
            catalog_csv_path=self.root / "missing.csv",
            pdf_dir=self.root / "pdfs",
            md_dir=self.root / "markdown",
            tracking_db_path=self.root / "tracking.db",
            chroma_dir=self.root / "chroma_db",
            source_manifest_path=self.root / "manifest.json",
            lm_studio_base_url="http://localhost:1234/v1",
            lm_studio_api_key="lm-studio",
            metadata_model="phi-3.5-mini-instruct",
            embedding_model="text-embedding-qwen3-embedding-0.6b",
            webapp_embedding_base_url="https://ai.derveloy.eu/v1",
            webapp_embedding_api_key="webapp-only-token",
            webapp_embedding_model="qwen3-embedding:0.6b",
        )
        db = TrackingDB(cfg.tracking_db_path)

        with patch("src.rag.ingestion.stage2_metadata.LMStudioClient") as mock_s2:
            run_stage2(cfg, db=db)
            mock_s2.assert_called_once_with(
                base_url="http://localhost:1234/v1",
                api_key="lm-studio",
                metadata_model="phi-3.5-mini-instruct",
                embedding_model="text-embedding-qwen3-embedding-0.6b",
                embedding_batch_size=cfg.embedding_batch_size,
            )

        with patch("src.rag.ingestion.stage3_index.LMStudioClient") as mock_s3:
            run_stage3(cfg, db=db, chroma_client=self.chroma_client)
            mock_s3.assert_called_once_with(
                base_url="http://localhost:1234/v1",
                api_key="lm-studio",
                metadata_model="phi-3.5-mini-instruct",
                embedding_model="text-embedding-qwen3-embedding-0.6b",
                embedding_batch_size=cfg.embedding_batch_size,
            )
