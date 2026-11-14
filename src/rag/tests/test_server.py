import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import chromadb
from fastapi.testclient import TestClient

from src.rag.chroma_release import SyncResult
from src.rag.config import RagConfig
from src.rag.server import create_app


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
        collection.add(
            ids=["chunk-1"],
            documents=["Contexte : Intro\nTexte : Microgravity droplet burning rate."],
            embeddings=[[1.0, 0.0, 0.0]],
            metadatas=[
                {
                    "id_pdf": "uuid-1234",
                    "title": "FLEX Droplet Report",
                    "source_type": "ntrs",
                    "chunk_index": 0,
                    "headers_path": "Intro",
                    "mission_program": "ISS",
                    "experiment_year": 2015,
                    "authors": "Alice Smith",
                    "pdf_url": "https://ntrs.nasa.gov/1234.pdf",
                    "experiment_url": "https://ntrs.nasa.gov/citations/1234",
                }
            ],
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_lifespan_runs_sync_and_endpoints_return_chunks(self) -> None:
        sync_calls: list[RagConfig] = []

        def fake_sync(cfg: RagConfig) -> SyncResult:
            sync_calls.append(cfg)
            return SyncResult(
                status="up_to_date",
                tag_name="chroma-db-v20261114-213500",
                chunk_count=1,
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
            self.assertEqual(health_data["release_tag"], "chroma-db-v20261114-213500")
            self.assertEqual(health_data["chunk_count"], 1)

            ret_resp = client.post("/retrieve", json={"query": "droplet burning", "top_k": 3})
            self.assertEqual(ret_resp.status_code, 200)
            ret_data = ret_resp.json()
            self.assertEqual(ret_data["count"], 1)
            chunk = ret_data["results"][0]
            self.assertEqual(chunk["id"], "chunk-1")
            self.assertEqual(chunk["metadata"]["id_pdf"], "uuid-1234")
            self.assertEqual(chunk["metadata"]["mission_program"], "ISS")
            self.assertEqual(chunk["metadata"]["authors"], "Alice Smith")
            llm_client.embed_texts.assert_called_once_with(["droplet burning"])
