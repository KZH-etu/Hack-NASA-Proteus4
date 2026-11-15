"""Serveur principal HEPHAISTOS : interface web + prédictions (model_gp) + /ask (Gemini + RAG HTTP).

    python -m src.rag.server --port 8001   # serveur RAG (ChromaDB + embeddings LM Studio)
    python -m src.api --port 8000          # API principale + dashboard HEPHAISTOS

Routes :
    GET  /                 interface HEPHAISTOS (app/frontend_hephaistos/)
    POST /predict          prédiction (format de la page)            -> src/api/predict.py
    GET  /models/status    état des modèles, du RAG distant et de Gemini
    POST /ask              chat : RAG (:8001) + Gemini Flash         -> src/api/ask.py
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
FRONTEND_PAGE = "index.html"
RAG_ROUTES = {"/health", "/retrieve"}


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    history: list[dict[str, Any]] = Field(default_factory=list)


def _check_remote_rag_health(rag_url: str) -> dict[str, Any]:
    """Query the standalone RAG server /health endpoint without failing API startup."""
    try:
        response = httpx.get(f"{rag_url.rstrip('/')}/health", timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "ready",
                "url": rag_url,
                "chunks": data.get("chunk_count"),
                "release_tag": data.get("release_tag"),
                "sync_status": data.get("sync_status"),
            }
        return {"status": "error", "url": rag_url, "error": f"HTTP {response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unreachable", "url": rag_url, "error": str(exc)}


def create_app(
    *,
    rag_app: FastAPI | None = None,
    with_rag: bool = True,
    warm_up: bool = True,
    rag_server_url: str | None = None,
    gemini_client: Any | None = None,
) -> FastAPI:
    """Construit l'application FastAPI HEPHAISTOS.

    En mode normal (`with_rag=True`, `rag_app=None`), `/ask` interroge le serveur RAG sur `RAG_SERVER_URL`
    (défaut `http://127.0.0.1:8001`). Passer `rag_app` reste supporté pour les tests en mémoire.
    """
    load_dotenv()
    resolved_rag_url = (
        rag_server_url
        or os.getenv("RAG_SERVER_URL")
        or ask_module.DEFAULT_RAG_SERVER_URL
    ).rstrip("/")

    if not with_rag:
        rag_status: dict[str, Any] = {"status": "disabled"}
    elif rag_app is not None:
        rag_status = {"status": "pending"}
    else:
        rag_status = {"status": "remote", "url": resolved_rag_url}

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
                    rag_status = {
                        "status": "ready",
                        "chunks": int(rag_app.state.collection.count()),
                        "release_tag": getattr(sync, "tag_name", None),
                    }
                except Exception as exc:  # noqa: BLE001
                    LOGGER.exception("Démarrage du RAG impossible : le chat est désactivé")
                    rag_status = {"status": "error", "error": str(exc)}
            yield

    app = FastAPI(title="HEPHAISTOS API", version="1.0.0", lifespan=lifespan)
    # La page peut aussi être ouverte en local (file://) : on accepte toutes les origines, sans cookies.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

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
        load_dotenv()
        current_rag = rag_status
        if with_rag and rag_app is None:
            current_rag = _check_remote_rag_health(resolved_rag_url)
        gemini_model = (os.getenv("GEMINI_MODEL") or ask_module.DEFAULT_GEMINI_MODEL).strip()
        gemini_configured = bool(gemini_client is not None or os.getenv("GEMINI_API_KEY", "").strip())
        return {
            "models": predict_module.STATUS,
            "rag": current_rag,
            "llm": {
                "provider": "google-gemini",
                "model": gemini_model,
                "configured": gemini_configured,
            },
        }

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
        if not with_rag:
            raise HTTPException(status_code=503, detail="Le RAG est désactivé (with_rag=False).")
        if rag_app is not None and rag_status.get("status") != "ready":
            raise HTTPException(
                status_code=503,
                detail=f"Le RAG n'est pas disponible ({rag_status.get('error') or rag_status['status']}).",
            )
        try:
            rag_state = rag_app.state if rag_app is not None else None
            return ask_module.ask(
                rag_state,
                payload.question,
                payload.history,
                rag_server_url=resolved_rag_url,
                gemini_client=gemini_client,
            )
        except ask_module.AskUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    if rag_app is not None:  # routes du serveur RAG conservées lorsqu'une rag_app est injectée (tests)
        for route in rag_app.router.routes:
            if isinstance(route, APIRoute) and route.path in RAG_ROUTES:
                app.router.routes.append(route)

    if FRONTEND_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
    return app
