"""Serveur HEPHAISTOS : un seul FastAPI pour l'interface, les prédictions, l'étude des données et le chat.

    python -m src.api                      # http://127.0.0.1:8000
    python -m src.api --no-rag             # sans le chat (prédictions seulement)

Routes :
    GET  /                       interface HEPHAISTOS (app/frontend_hephaistos/index.html)
    GET  /assets/...             images, Chart.js
    POST /api/predict            prédiction (format de la page)            -> src/api/predict.py
    GET  /api/dataset/summary    chiffres de la page « Étude des données »  -> src/api/dataset.py
    GET  /api/models/status      état des modèles, du RAG et de Gemini
    POST /api/ask                chat : RAG + Gemini                        -> src/api/ask.py
    GET  /api/rag/health         routes du serveur RAG (src/rag/server), reprises telles quelles
    POST /api/rag/retrieve

Le RAG tourne dans le même processus : son application est créée par src.rag.server.create_app() et son
démarrage (base ChromaDB, client d'embedding OpenAI-compatible de la webapp) est exécuté au lancement. Pour utiliser un serveur RAG séparé
(python -m src.rag.server, par exemple sur une autre machine), définir RAG_SERVER_URL.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import AsyncExitStack, asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api import ask as ask_module
from src.api import dataset as dataset_module
from src.api import predict as predict_module

LOGGER = logging.getLogger("hephaistos")
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "app" / "frontend_hephaistos"
FRONTEND_PAGE = FRONTEND_DIR / "index.html"
RAG_ROUTES = {"/health", "/retrieve"}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)


def _check_remote_rag_health(rag_url: str) -> dict[str, Any]:
    """Interroge /health d'un serveur RAG séparé, sans bloquer le démarrage."""
    try:
        response = httpx.get(f"{rag_url.rstrip('/')}/health", timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            return {"status": "ready", "mode": "remote", "url": rag_url, "chunks": data.get("chunk_count"),
                    "release_tag": data.get("release_tag"), "sync_status": data.get("sync_status")}
        return {"status": "error", "mode": "remote", "url": rag_url, "error": f"HTTP {response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "mode": "remote", "url": rag_url, "error": str(exc)}


def create_app(
    *,
    rag_app: FastAPI | None = None,
    with_rag: bool = True,
    warm_up: bool = True,
    rag_server_url: str | None = None,
    gemini_client: Any | None = None,
) -> FastAPI:
    """Construit l'application HEPHAISTOS.

    Chat : sans réglage, le RAG est chargé dans ce serveur ; avec rag_server_url (ou RAG_SERVER_URL), il est
    interrogé par HTTP sur un serveur séparé ; with_rag=False le désactive. rag_app : RAG injecté (tests).
    """
    load_dotenv()
    remote_url = (rag_server_url or os.getenv("RAG_SERVER_URL") or "").strip().rstrip("/")
    rag_error = None
    if with_rag and rag_app is None and not remote_url:
        try:
            from src.rag.server import create_app as create_rag_app
            rag_app = create_rag_app()
        except Exception as exc:  # noqa: BLE001 - les prédictions restent disponibles
            LOGGER.exception("RAG non créé : le chat est désactivé")
            rag_error = str(exc)

    if not with_rag:
        rag_status: dict[str, Any] = {"status": "disabled"}
    elif rag_app is not None:
        rag_status = {"status": "pending", "mode": "in-process"}
    elif remote_url:
        rag_status = {"status": "remote", "mode": "remote", "url": remote_url}
    else:
        rag_status = {"status": "error", "error": rag_error}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal rag_status
        if warm_up:
            threading.Thread(target=predict_module.warm_up, name="warm-up", daemon=True).start()
        async with AsyncExitStack() as stack:
            if rag_app is not None:
                rag_status = {"status": "loading", "mode": "in-process"}
                try:
                    await stack.enter_async_context(rag_app.router.lifespan_context(rag_app))
                    sync = getattr(rag_app.state, "sync_result", None)
                    rag_status = {"status": "ready", "mode": "in-process",
                                  "chunks": int(rag_app.state.collection.count()),
                                  "release_tag": getattr(sync, "tag_name", None)}
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Démarrage du RAG impossible : le chat est désactivé")
                    rag_status = {"status": "error", "mode": "in-process", "error": str(exc)}
            yield

    app = FastAPI(title="HEPHAISTOS", version="2.0.0", lifespan=lifespan)
    # La page peut aussi être ouverte en local (file://) : on accepte toutes les origines, sans cookies.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])

    def check_key(request: Request):
        """Clé d'API facultative : si HEPHAISTOS_API_KEY est définie, l'en-tête X-API-Key est exigé."""
        key = os.getenv("HEPHAISTOS_API_KEY", "")
        if key and not compare_digest(request.headers.get("X-API-Key", ""), key):
            raise HTTPException(status_code=401, detail="Clé d'API invalide")

    # ---------- Interface ----------

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(FRONTEND_PAGE)

    if (FRONTEND_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    # ---------- API ----------

    api = APIRouter(prefix="/api")

    @api.get("/dataset/summary")
    def dataset_summary():
        """Chiffres et séries de la page « Étude des données »."""
        return dataset_module.summary()

    @api.get("/models/status")
    def models_status():
        load_dotenv()
        remote = with_rag and rag_app is None and remote_url
        current_rag = _check_remote_rag_health(remote_url) if remote else rag_status
        gemini_model = (os.getenv("GEMINI_MODEL") or ask_module.DEFAULT_GEMINI_MODEL).strip()
        gemini_configured = bool(gemini_client is not None or os.getenv("GEMINI_API_KEY", "").strip())
        return {"models": predict_module.STATUS, "rag": current_rag,
                "llm": {"provider": "google-gemini", "model": gemini_model, "configured": gemini_configured}}

    @api.post("/predict")
    def predict(payload: dict[str, Any], request: Request):
        check_key(request)
        try:
            return predict_module.predict(payload)
        except predict_module.PredictionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Prédiction impossible")
            raise HTTPException(status_code=500, detail=f"Prédiction impossible : {exc}") from exc

    @api.post("/ask")
    def ask(payload: AskRequest, request: Request):
        check_key(request)
        if not with_rag:
            raise HTTPException(status_code=503, detail="Le chat est désactivé (serveur lancé avec --no-rag).")
        if rag_app is None and not remote_url:
            raise HTTPException(status_code=503, detail=f"Le RAG n'a pas pu être créé ({rag_error}).")
        if rag_app is not None and rag_status.get("status") != "ready":
            raise HTTPException(status_code=503,
                                detail=f"Le RAG n'est pas disponible ({rag_status.get('error') or rag_status['status']}).")
        try:
            return ask_module.ask(rag_app.state if rag_app is not None else None, payload.question, payload.history,
                                  rag_server_url=remote_url or None, gemini_client=gemini_client)
        except ask_module.AskUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if rag_app is not None:  # routes du serveur RAG, reprises telles quelles sous /api/rag
        for route in rag_app.router.routes:
            if isinstance(route, APIRoute) and route.path in RAG_ROUTES:
                api.add_api_route(f"/rag{route.path}", route.endpoint, methods=list(route.methods),
                                  response_model=route.response_model, summary=route.summary, tags=["rag"])

    app.include_router(api)
    return app
