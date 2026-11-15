"""Tests du serveur HEPHAISTOS (src/api) : sans entraîner les modèles ni appeler Gemini ou LM Studio."""

from types import SimpleNamespace

import chromadb
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api import ask as ask_module
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

    def embed_texts(self, texts):
        return [[1.0, 0.0, 0.0]]


class FakeGeminiClient:
    def __init__(self, answer="La flamme s'éteint par rayonnement [1].", fail=False):
        self.calls = []
        outer = self

        class _Models:
            @staticmethod
            def generate_content(**kwargs):
                outer.calls.append(kwargs)
                if fail:
                    raise ConnectionError("Gemini indisponible")
                return SimpleNamespace(text=answer)

        self.models = _Models()


def make_collection():
    client = chromadb.EphemeralClient()
    name = RagConfig.from_env().chroma_collection
    try:
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - la collection n'existe pas encore
        pass
    col = client.create_collection(name)
    col.add(
        ids=[d[0] for d in DOCS],
        documents=[d[3] for d in DOCS],
        embeddings=[[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0]],
        metadatas=[
            {
                "id_pdf": d[1],
                "chunk_index": d[2],
                "title": "FLEX" if d[1] == "doc-1" else "BASS",
                "authors": "V. Nayagam, F. L. Dryer",
                "mission_program": "ISS",
                "headers_path": d[3].split("\n")[0].removeprefix("Contexte : "),
                "pdf_url": f"https://ntrs.nasa.gov/api/citations/2015000{i}/downloads/2015000{i}.pdf",
                "experiment_url": f"https://ntrs.nasa.gov/citations/2015000{i}",
                "experiment_year": 2015,
                "source_type": "ntrs",
            }
            for i, d in enumerate(DOCS)
        ],
    )
    return client


def client_with_rag(fake_embedder=None, fake_gemini=None):
    rag = create_rag_app(
        skip_sync=True,
        chroma_client=make_collection(),
        llm_client=fake_embedder or FakeLMStudio(),
    )
    return TestClient(
        create_app(
            rag_app=rag,
            warm_up=False,
            gemini_client=fake_gemini or FakeGeminiClient(),
        )
    )


def test_ask_returns_answer_and_enriched_sources_in_order(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    fake_gemini = FakeGeminiClient()
    with client_with_rag(fake_gemini=fake_gemini) as c:
        r = c.post(
            "/ask",
            json={
                "question": "Pourquoi la flamme s'éteint-elle ?",
                "history": [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Salut"}],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("La flamme")
    assert "Contexte :" not in body["answer"]
    assert body["model"] == "gemini-3.8-flash"
    src = body["sources"][0]
    assert src["index"] == 1
    assert src["title"] == "FLEX"
    assert src["authors"] == "V. Nayagam, F. L. Dryer"
    assert src["mission_program"] == "ISS"
    assert src["year"] == 2015
    assert src["page"] == 3
    assert src["ntrs_id"] == "20150000"
    assert src["pdf_url"].endswith(".pdf")
    assert src["experiment_url"] == "https://ntrs.nasa.gov/citations/20150000"
    assert len(src["excerpts"]) == 1
    assert "rayonnement" in src["excerpts"][0]
    assert "diamètre" in src["excerpts"][0]
    assert len(fake_gemini.calls) == 1
    assert fake_gemini.calls[0]["model"] == "gemini-3.8-flash"


def test_ask_deduplicates_sources_and_reindexes_citations_continuously(monkeypatch):
    def fake_post(url, json, timeout):
        return SimpleNamespace(
            status_code=200,
            text="",
            json=lambda: [
                {
                    "text": "Extrait A1 sur les gouttelettes.",
                    "context_block": "Extrait A1 sur les gouttelettes.",
                    "metadata": {"id_pdf": "pdf-A", "title": "Doc A", "page": 2},
                },
                {
                    "text": "Extrait A2 du même document.",
                    "context_block": "Extrait A2 du même document.",
                    "metadata": {"id_pdf": "pdf-A", "title": "Doc A", "page": 5},
                },
                {
                    "text": "Extrait B ignoré par le modèle.",
                    "context_block": "Extrait B ignoré par le modèle.",
                    "metadata": {"id_pdf": "pdf-B", "title": "Doc B", "page": 1},
                },
                {
                    "text": "Extrait C cité en deuxième.",
                    "context_block": "Extrait C cité en deuxième.",
                    "metadata": {"id_pdf": "pdf-C", "title": "Doc C", "page": 8},
                },
            ],
        )

    monkeypatch.setattr(ask_module.httpx, "post", fake_post)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout: SimpleNamespace(
            status_code=200,
            json=lambda: {"status": "ok", "chunk_count": 100, "release_tag": "v1", "sync_status": "up_to_date"},
        ),
    )

    fake_gemini = FakeGeminiClient(
        answer="Synthèse claire combinant le second document cité [3] et le premier [1, 3]."
    )
    with TestClient(
        create_app(
            rag_server_url="http://127.0.0.1:8001",
            warm_up=False,
            gemini_client=fake_gemini,
        )
    ) as c:
        r = c.post("/ask", json={"question": "Résume ?"})

    assert r.status_code == 200
    body = r.json()
    # [3] apparaît en premier -> devient [1] (Doc C), [1] apparaît ensuite -> devient [2] (Doc A)
    assert body["answer"] == "Synthèse claire combinant le second document cité [1] et le premier [2] [1]."
    assert [s["index"] for s in body["sources"]] == [1, 2]
    assert [s["title"] for s in body["sources"]] == ["Doc C", "Doc A"]
    assert body["sources"][0]["excerpts"] == ["Extrait C cité en deuxième."]
    assert body["sources"][1]["excerpts"] == [
        "Extrait A1 sur les gouttelettes.",
        "Extrait A2 du même document.",
    ]


def test_ask_keeps_closest_sources_when_llm_refuses_off_topic_question():
    refusal = (
        "Je n'ai pas trouvé d'information permettant de produire une réponse satisfaisante. "
        "Les ressources les plus proches sont :"
    )
    fake_gemini = FakeGeminiClient(answer=refusal)
    with client_with_rag(fake_gemini=fake_gemini) as c:
        r = c.post("/ask", json={"question": "azerty quelle est la recette des crepes ?"})

    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == refusal
    assert [s["index"] for s in body["sources"]] == [1, 2]
    assert [s["title"] for s in body["sources"]] == ["FLEX", "BASS"]
    assert "aucun sens" in fake_gemini.calls[0]["config"].system_instruction


def test_ask_calls_remote_rag_server_over_http(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return SimpleNamespace(
            status_code=200,
            text="",
            json=lambda: [
                {
                    "text": "Les flammes froides apparaissent après l'extinction radiative.",
                    "context_block": "Document : Cool Flames in FLEX\n---\nLes flammes froides apparaissent après l'extinction radiative.",
                    "metadata": {
                        "title": "Cool Flames in FLEX",
                        "authors": "F. A. Williams",
                        "experiment_year": 2018,
                        "mission_program": "ISS",
                        "source_type": "ntrs",
                        "headers_path": "Discussion > Cool Flames",
                        "pdf_url": "https://ntrs.nasa.gov/api/citations/20180001234/downloads/20180001234.pdf",
                        "experiment_url": "https://ntrs.nasa.gov/citations/20180001234",
                        "ntrs_id": "20180001234",
                        "page": 12,
                    },
                }
            ],
        )

    monkeypatch.setattr(ask_module.httpx, "post", fake_post)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout: SimpleNamespace(
            status_code=200,
            json=lambda: {"status": "ok", "chunk_count": 21374, "release_tag": "v1", "sync_status": "up_to_date"},
        ),
    )

    fake_gemini = FakeGeminiClient(answer="Les flammes froides surviennent après extinction [1].")
    with TestClient(
        create_app(
            rag_server_url="http://127.0.0.1:8001",
            warm_up=False,
            gemini_client=fake_gemini,
        )
    ) as c:
        status = c.get("/models/status").json()
        assert status["rag"]["status"] == "ready"
        assert status["rag"]["chunks"] == 21374
        assert status["llm"]["model"] == "gemini-3.8-flash"

        r = c.post("/ask", json={"question": "Qu'est-ce qu'une flamme froide ?"})

    assert r.status_code == 200
    assert captured["url"] == "http://127.0.0.1:8001/retrieve"
    body = r.json()
    assert body["sources"][0]["title"] == "Cool Flames in FLEX"
    assert body["sources"][0]["authors"] == "F. A. Williams"
    assert body["sources"][0]["year"] == 2018
    assert body["sources"][0]["page"] == 12
    assert body["sources"][0]["pdf_url"].endswith("20180001234.pdf")


def test_ask_without_gemini_returns_passages():
    with client_with_rag(fake_gemini=FakeGeminiClient(fail=True)) as c:
        body = c.post("/ask", json={"question": "extinction"}).json()
    assert "Gemini" in body["answer"]
    assert body["sources"]


def test_ask_falls_back_when_primary_gemini_model_is_overloaded(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite")

    tried = []

    class FlakyGemini:
        class _Models:
            @staticmethod
            def generate_content(**kwargs):
                tried.append(kwargs["model"])
                if kwargs["model"] == "gemini-3.8-flash":
                    raise RuntimeError("503 UNAVAILABLE")
                return SimpleNamespace(text="Réponse de secours [1].")

        models = _Models()

    with client_with_rag(fake_gemini=FlakyGemini()) as c:
        r = c.post("/ask", json={"question": "extinction"})
    assert r.status_code == 200
    body = r.json()
    assert tried == ["gemini-3.8-flash", "gemini-3.6-flash"]
    assert body["model"] == "gemini-3.6-flash"
    assert body["answer"] == "Réponse de secours [1]."


def test_ask_requires_gemini_key_when_missing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    rag = create_rag_app(skip_sync=True, chroma_client=make_collection(), llm_client=FakeLMStudio())
    with TestClient(create_app(rag_app=rag, warm_up=False)) as c:
        r = c.post("/ask", json={"question": "extinction"})
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["detail"]


def test_rag_routes_are_kept_and_status_reports_rag():
    with client_with_rag() as c:
        assert c.get("/health").json()["chunk_count"] == len(DOCS)
        assert c.post("/retrieve", json={"query": "x", "top_k": 1}).status_code == 200
        assert c.get("/models/status").json()["rag"]["status"] == "ready"


def test_ask_is_503_without_rag():
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        assert c.post("/ask", json={"question": "x"}).status_code == 503


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"fuel_type": "plasma"}, "fuel_type"),
        ({"fuel_type": "gas", "material": "propane", "o2_percent": 21}, "pressure_kpa"),
        ({"fuel_type": "solid", "o2_percent": 21, "flow_cm_s": 10}, "material"),
    ],
)
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
        r = c.post(
            "/predict",
            json={
                "fuel_type": "droplet",
                "material": "Methanol",
                "o2_percent": 21,
                "pressure_kpa": 101.3,
                "model": "model_flex",
            },
        )
    assert r.status_code == 200
    assert seen["fuel"] == "methanol" and seen["d0_mm"] == 3.0 and seen["co2_percent"] == 0.0
    assert r.json()["sources"] == []


def test_home_serves_the_interface():
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        r = c.get("/", follow_redirects=True)
    assert r.status_code == 200
    assert "HEPHAISTOS" in r.text


def test_dataset_summary_for_the_data_page():
    with TestClient(create_app(with_rag=False, warm_up=False)) as c:
        r = c.get("/dataset/summary")
    assert r.status_code == 200
    d = r.json()
    assert d["kpis"]["tests"] == sum(e["n"] for e in d["by_experiment"])
    assert sum(o["n"] for o in d["outcomes"]) == d["kpis"]["tests"]
    assert set(d["coverage"]) == set(d["families"])
    assert d["insights"]
