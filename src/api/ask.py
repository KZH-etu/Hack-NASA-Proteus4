"""Chat de l'interface HEPHAISTOS : question -> passages des documents NASA (RAG de src/rag) -> réponse citée.

Requête : {"question": "...", "history": [{"role": "user" | "assistant", "content": "..."}]}
Réponse : {"answer": "...", "sources": [{"title", "ntrs_id", "page", "url", "year", "source_type"}]}
Les sources sont dans l'ordre des extraits : [n] dans la réponse renvoie à la n-ième source.

La recherche réutilise le serveur RAG (src/rag/server) : sa collection ChromaDB, son client LM Studio
(embeddings) et sa fonction de contexte (morceau trouvé + morceaux voisins). La réponse est rédigée par le
modèle de chat de LM Studio (variable RAG_CHAT_MODEL, sinon le modèle de métadonnées du RAG).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

LOGGER = logging.getLogger("hephaistos.ask")

TOP_K = 5
NEIGHBORS = 1
MAX_HISTORY = 6
NO_SOURCE_ANSWER = "Je n'ai pas trouvé de document NASA sur ce point."
LLM_DOWN_ANSWER = ("Le modèle de langage local (LM Studio) ne répond pas : voici les passages des documents "
                   "NASA les plus proches de votre question.")

SYSTEM_PROMPT = (
    "Tu es l'assistant du projet HEPHAISTOS sur la combustion en microgravité et la sécurité incendie des "
    "missions spatiales. Réponds en français, de façon claire et concise, en t'appuyant UNIQUEMENT sur les "
    "extraits de documents NASA fournis. Cite tes sources avec leur numéro entre crochets, par exemple [1] ou "
    "[2]. Si les extraits ne permettent pas de répondre, dis-le simplement, sans inventer."
)


class AskUnavailable(RuntimeError):
    """La recherche est impossible (base absente, LM Studio injoignable pour les embeddings) : 503."""


def _page(meta):
    match = re.search(r"Page\s+(\d+)", str(meta.get("headers_path") or ""))
    return int(match.group(1)) if match else None


def _ntrs_id(url):
    match = re.search(r"citations/(\d+)", url or "")
    return match.group(1) if match else None


def _source(meta):
    url = str(meta.get("experiment_url") or meta.get("pdf_url") or "") or None
    source = {"title": meta.get("title") or None, "ntrs_id": _ntrs_id(url), "page": _page(meta), "url": url,
              "year": meta.get("experiment_year") or None, "source_type": meta.get("source_type") or None}
    return {k: v for k, v in source.items() if v is not None}


def ask(rag_state: Any, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    from src.rag.server.app import _retrieve_contexts

    collection, client = getattr(rag_state, "collection", None), getattr(rag_state, "llm_client", None)
    if collection is None or client is None:
        raise AskUnavailable("le RAG n'est pas chargé (voir /models/status)")
    if int(collection.count()) == 0:
        raise AskUnavailable("la base ChromaDB est vide : python -m src.rag.storage.download_chroma_release")
    try:
        vector = client.embed_texts([question])[0]
    except Exception as exc:  # noqa: BLE001
        raise AskUnavailable(f"LM Studio injoignable pour calculer l'embedding de la question : {exc}") from exc

    n = min(TOP_K, int(collection.count()))
    raw = collection.query(query_embeddings=[vector], n_results=n, include=["metadatas"])
    metas = [dict(m or {}) for m in (raw.get("metadatas") or [[]])[0]]
    contexts = _retrieve_contexts(collection=collection, query_vector=vector, top_k=n, neighbors=NEIGHBORS)
    if not contexts:
        return {"answer": NO_SOURCE_ANSWER, "sources": []}

    # Une source par passage, dans le même ordre que les extraits numérotés
    sources = [_source(m) for m in metas[:len(contexts)]]
    extracts = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(contexts, 1))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-MAX_HISTORY:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": str(turn["content"])})
    messages.append({"role": "user", "content": f"Extraits de documents NASA :\n\n{extracts}\n\nQuestion : {question}"})

    model = os.getenv("RAG_CHAT_MODEL") or getattr(client, "metadata_model", None)
    try:
        completion = client.client.chat.completions.create(model=model, messages=messages, temperature=0.2,
                                                           max_tokens=700)
        answer = (completion.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 - le chat reste utilisable avec les seuls passages
        LOGGER.warning("Génération impossible (%s) : renvoi des passages seuls", exc)
        return {"answer": LLM_DOWN_ANSWER, "sources": sources}

    return {"answer": answer or NO_SOURCE_ANSWER, "sources": sources}

