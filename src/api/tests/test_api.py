"""Tests du serveur HEPHAISTOS (src/api) : sans entraîner les modèles ni appeler LM Studio."""

from types import SimpleNamespace

import chromadb
import pytest
from fastapi.testclient import TestClient

from src.api import predict as predict_module
from src.api.app import create_app
from src.rag.config import RagConfig
from src.rag.server import create_app as create_rag_app

DOCS = [
    ("a", "doc-1", 0, "Contexte : FLEX > Page 3\nTexte : La flamme de la gouttelette s'éteint par rayonnement."),
    ("b", "doc-1", 1, "Contexte : FLEX > Page 4\nTexte : L'extinction radiative dépend du diamètre."),
    ("c", "doc-2", 0, "Contexte : BASS > Page 1\nTexte : Les solides brûlent plus lentement en microgravité."),
]


class FakeLMStudio:
    metadata_model = "chat-model"

    def __init__(self, answer="La flamme s'éteint par rayonnement [1].", fail_chat=False):
        def create(**kwargs):
            if fail_chat:
                raise ConnectionError("LM Studio arrêté")
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.0]]


def make_collection():
    client = chromadb.EphemeralClient()
    name = RagConfig.from_env().chroma_collection
    try:
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - la collection n'existe pas encore
        pass
    col = client.create_collection(name)
    col.add(ids=[d[0] for d in DOCS], documents=[d[3] for d in DOCS],
            embeddings=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0]],
            metadatas=[{"id_pdf": d[1], "chunk_index": d[2], "title": "FLEX" if d[1] == "doc-1" else "BASS",
                        "headers_path": d[3].split("\n")[0].removeprefix("Contexte : "),
                        "experiment_url": f"https://ntrs.nasa.gov/citations/2015000{i}", "experiment_year": 2015,
                        "source_type": "ntrs"} for i, d in enumerate(DOCS)])
    return client


def client_with_rag(fake):
    rag = create_rag_app(skip_sync=True, chroma_client=make_collection(), llm_client=fake)
    return TestClient(create_app(rag_app=rag, warm_up=False))


def test_ask_returns_answer_and_sources_in_extract_order():
    with client_with_rag(FakeLMStudio()) as c:
        r = c.post("/ask", json={"question": "Pourquoi la flamme s'éteint-elle ?", "history": []})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("La flamme")
    assert body["sources"][0]["title"] == "FLEX"
    assert body["sources"][0]["page"] == 3
    assert body["sources"][0]["ntrs_id"] == "20150000"


def test_ask_without_llm_returns_passages():
    with client_with_rag(FakeLMStudio(fail_chat=True)) as c:
        body = c.post("/ask", json={"question": "extinction"}).json()
    assert "LM Studio" in body["answer"]
    assert body["sources"]


def test_rag_routes_are_kept_and_status_reports_rag():
    with client_with_rag(FakeLMStudio()) as c:
        assert c.get("/health").json()["chunk_count"] == len(DOCS)
        assert c.post("/retrieve", json={"query": "x", "top_k": 1}).status_code == 200
        assert c.get("/models/status").json()["rag"]["status"] == "ready"


def test_ask_is_503_without_rag():
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        assert c.post("/ask", json={"question": "x"}).status_code == 503


@pytest.mark.parametrize("payload, message", [
    ({"fuel_type": "plasma"}, "fuel_type"),
    ({"fuel_type": "gas", "material": "propane", "o2_percent": 21}, "pressure_kpa"),
    ({"fuel_type": "solid", "o2_percent": 21, "flow_cm_s": 10}, "material"),
])
def test_predict_rejects_incomplete_requests(payload, message):
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        r = c.post("/predict", json=payload)
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_predict_maps_material_to_fuel(monkeypatch):
    seen = {}

    class FakeFlex:
        @staticmethod
        def predict(conditions):
            seen.update(conditions)
            return {"p_extinction": 0.5, "warnings": []}

        @staticmethod
        def conditions_to_row(conditions):
            import numpy as np
            return np.array([[0.0, 0.21, 101.3, 0.0, 0.0, 3.0]])

        @staticmethod
        def trained_model():
            return None

    monkeypatch.setattr(predict_module, "ensure_loaded", lambda family: None)
    monkeypatch.setattr(predict_module, "_family_module", lambda family: FakeFlex)
    monkeypatch.setattr("src.models.model_gp.flex.recommend.nearest_tests", lambda *a, **k: [])
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        r = c.post("/predict", json={"fuel_type": "droplet", "material": "Methanol", "o2_percent": 21,
                                     "pressure_kpa": 101.3, "model": "model_flex"})
    assert r.status_code == 200
    assert seen["fuel"] == "methanol" and seen["d0_mm"] == 3.0 and seen["co2_percent"] == 0.0
    assert r.json()["sources"] == []


def test_home_serves_the_interface():
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        r = c.get("/", follow_redirects=True)
    assert r.status_code == 200
    assert "HEPHAISTOS" in r.text
