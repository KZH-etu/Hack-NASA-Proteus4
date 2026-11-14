"""Serveur unique de HEPHAISTOS : interface web + prédictions (model_gp) + RAG (src/rag), sur un seul port.

    python -m src.api                    # http://127.0.0.1:8000  (ouvre l'interface)
    python -m src.api --skip-sync        # sans vérifier la release ChromaDB au démarrage

Routes :
    GET  /                 interface HEPHAISTOS (app/frontend_hephaistos/)
    POST /predict          prédiction (format de la page)            -> src/api/predict.py
    GET  /models/status    état des modèles (prêt / chargement) et du RAG
    POST /ask              chat : réponse rédigée + sources          -> src/api/ask.py
    GET  /health, POST /retrieve   routes du serveur RAG (src/rag/server), inchangées

Le serveur RAG n'est pas modifié : son application est créée par src.rag.server.create_app(), son démarrage
(synchronisation de la base, ChromaDB, LM Studio) est exécuté tel quel, et ses routes sont reprises.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import AsyncExitStack, asynccontextmanager
from hmac import compare_digest
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api import ask as ask_module
from src.api import predict as predict_module

LOGGER = logging.getLogger("hephaistos")
ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "app" / "frontend_hephaistos"
FRONTEND_PAGE = "HEPHAISTOS_interface_v5_modeles.html"
RAG_ROUTES = {"/health", "/retrieve"}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)


def create_app(*, rag_app: FastAPI | None = None, with_rag: bool = True, warm_up: bool = True) -> FastAPI:
    """rag_app : application du serveur RAG (par défaut src.rag.server.create_app()) ; with_rag=False pour s'en passer."""
    rag_error = None
    if with_rag and rag_app is None:
        try:
            from src.rag.server import create_app as create_rag_app
            rag_app = create_rag_app()
        except Exception as exc:  # noqa: BLE001 - les prédictions restent disponibles
            LOGGER.exception("Serveur RAG non créé")
            rag_error = str(exc)
    if rag_app is not None:
        rag_status = {"status": "pending"}
    else:
        rag_status = {"status": "error", "error": rag_error} if rag_error else {"status": "disabled"}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal rag_status
        if warm_up:
            threading.Thread(target=predict_module.warm_up, name="warm-up", daemon=True).start()
        async with AsyncExitStack() as stack:
            if rag_app is not None:
                rag_status = {"status": "loading"}
                try:
                    await stack.enter_async_context(rag_app.router.lifespan_context(rag_app))
                    sync = getattr(rag_app.state, "sync_result", None)
                    rag_status = {"status": "ready", "chunks": int(rag_app.state.collection.count()),
                                  "release_tag": getattr(sync, "tag_name", None)}
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Démarrage du RAG impossible : le chat est désactivé")
                    rag_status = {"status": "error", "error": str(exc)}
            yield

    app = FastAPI(title="HEPHAISTOS API", version="1.0.0", lifespan=lifespan)
    # La page peut aussi être ouverte en local (file://) : on accepte toutes les origines, sans cookies.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])

    def check_key(request: Request):
        """Clé d'API facultative : si HEPHAISTOS_API_KEY est définie, l'en-tête X-API-Key est exigé."""
        key = os.getenv("HEPHAISTOS_API_KEY", "")
        if key and not compare_digest(request.headers.get("X-API-Key", ""), key):
            raise HTTPException(status_code=401, detail="Clé d'API invalide")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse(f"/ui/{FRONTEND_PAGE}")

    @app.get("/models/status")
    def models_status():
        return {"models": predict_module.STATUS, "rag": rag_status}

    @app.post("/predict")
    def predict(payload: dict[str, Any], request: Request):
        check_key(request)
        try:
            return predict_module.predict(payload)
        except predict_module.PredictionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Prédiction impossible")
            raise HTTPException(status_code=500, detail=f"Prédiction impossible : {exc}") from exc

    @app.post("/ask")
    def ask(payload: AskRequest, request: Request):
        check_key(request)
        if rag_app is None or rag_status.get("status") != "ready":
            raise HTTPException(status_code=503, detail=f"Le RAG n'est pas disponible ({rag_status.get('error') or rag_status['status']}).")
        try:
            return ask_module.ask(rag_app.state, payload.question, payload.history)
        except ask_module.AskUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if rag_app is not None:  # routes du serveur RAG, reprises telles quelles
        for route in rag_app.router.routes:
            if isinstance(route, APIRoute) and route.path in RAG_ROUTES:
                app.router.routes.append(route)

    if FRONTEND_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
    return app
