"""Chat de l'interface HEPHAISTOS : question -> RAG (src/rag/server) -> Google Gemini Flash -> réponse citée.

Requête : {"question": "...", "history": [{"role": "user" | "assistant", "content": "..."}]}
Réponse : {"answer": "...", "model": "...", "sources": [{"index", "title", "authors", "year", ...}]}
Les sources suivent l'ordre des extraits retournés par le RAG : [n] dans la réponse renvoie à la n-ième source.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

LOGGER = logging.getLogger("hephaistos.ask")

TOP_K = 5
NEIGHBORS = 1
MAX_HISTORY = 6
DEFAULT_RAG_SERVER_URL = "http://127.0.0.1:8001"
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GEMINI_FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.7-flash")
GEMINI_TIMEOUT_MS = 10_000

NO_SOURCE_ANSWER = "I could not find any NASA document on this topic."
LLM_DOWN_ANSWER = (
    "The Gemini model is not responding right now: no summary was generated, but you can "
    "browse the relevant NASA sources and their excerpts below."
)

SYSTEM_PROMPT = (
    "You are the assistant of the HEPHAISTOS project on microgravity combustion and spacecraft fire "
    "safety. Answer in English, clearly, naturally, concisely and in a structured way, relying ONLY on "
    "the NASA document excerpts provided. Never copy the raw excerpts verbatim. Cite every fact with the "
    "number of its source in square brackets, for example [1] or [2] (separate several sources like this: "
    "[1] [2], never [1, 2]). "
    "If the question makes no sense, is off-topic, or is unrelated to the excerpts provided, so that no "
    "satisfactory answer is possible, do not invent anything and answer exactly with this sentence, "
    "without citation: \"I could not find information to produce a satisfactory answer. The closest "
    "resources are:\" "
    "If only some aspects are missing from the excerpts, answer what is documented and state explicitly "
    "what is missing, without ever inventing values or results."
)


class AskUnavailable(RuntimeError):
    """Recherche RAG ou configuration Gemini indisponible -> HTTP 503."""


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    return text


def _clean_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_from_headers(meta: dict[str, Any]) -> int | None:
    match = re.search(r"Page\s+(\d+)", str(meta.get("headers_path") or ""))
    return int(match.group(1)) if match else None


def _ntrs_id(meta: dict[str, Any], *urls: str | None) -> str | None:
    explicit = _clean_text(meta.get("ntrs_id"))
    if explicit:
        return explicit
    for url in urls:
        if not url:
            continue
        match = re.search(r"citations/(\d+)|(\d{7,})", url)
        if match:
            return match.group(1) or match.group(2)
    return None


def _source(meta: dict[str, Any], index: int, *, excerpts: list[str] | None = None) -> dict[str, Any]:
    """Build an enriched, UI-ready source dictionary from RAG chunk metadata."""
    pdf_url = _clean_text(meta.get("pdf_url"))
    experiment_url = _clean_text(meta.get("experiment_url"))
    primary_url = experiment_url or pdf_url
    page = _clean_int(meta.get("page")) or _page_from_headers(meta)

    source: dict[str, Any] = {
        "index": index,
        "title": _clean_text(meta.get("title")),
        "authors": _clean_text(meta.get("authors")),
        "year": _clean_int(meta.get("experiment_year") or meta.get("year")),
        "mission_program": _clean_text(meta.get("mission_program")),
        "source_type": _clean_text(meta.get("source_type")),
        "headers_path": _clean_text(meta.get("headers_path")),
        "ntrs_id": _ntrs_id(meta, experiment_url, pdf_url),
        "page": page,
        "pdf_url": pdf_url,
        "experiment_url": experiment_url,
        "url": primary_url,
        "excerpts": list(excerpts or []),
    }
    return {k: v for k, v in source.items() if v is not None}


def _extract_excerpt(item: dict[str, Any]) -> str:
    """Return the exact non-empty retrieved passage excerpt for a RAG item."""
    raw = str(item.get("text") or item.get("context_block") or "").strip()
    return raw


def _source_dedup_key(meta: dict[str, Any], fallback_pos: int) -> tuple[Any, ...]:
    """Identify a unique document so multiple retrieved chunks share one source entry."""
    id_pdf = _clean_text(meta.get("id_pdf"))
    if id_pdf:
        return ("id_pdf", id_pdf)

    pdf_url = _clean_text(meta.get("pdf_url"))
    experiment_url = _clean_text(meta.get("experiment_url"))
    ntrs_id = _ntrs_id(meta, experiment_url, pdf_url)
    if ntrs_id:
        return ("ntrs_id", ntrs_id)
    if pdf_url or experiment_url:
        return ("url", pdf_url or "", experiment_url or "")

    title = _clean_text(meta.get("title"))
    if title:
        year = _clean_int(meta.get("experiment_year") or meta.get("year"))
        return ("title", title, year or "")

    return ("chunk", fallback_pos)


def _group_retrieved_by_source(retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate retrieved chunks by unique document, preserving order and exact excerpts."""
    grouped: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}

    for pos, item in enumerate(retrieved):
        meta = dict(item.get("metadata") or {})
        key = _source_dedup_key(meta, pos)
        excerpt = _extract_excerpt(item)
        context_block = str(item.get("context_block") or item.get("text") or "").strip()

        if key not in by_key:
            source_dict = _source(meta, len(grouped) + 1, excerpts=[excerpt] if excerpt else [])
            entry = {
                "source": source_dict,
                "excerpts": source_dict["excerpts"],
                "seen_excerpts": {" ".join(excerpt.split())} if excerpt else set(),
                "contexts": [context_block] if context_block else [],
                "seen_contexts": {" ".join(context_block.split())} if context_block else set(),
            }
            by_key[key] = entry
            grouped.append(entry)
            continue

        entry = by_key[key]
        # Compléter les champs manquants si un autre chunk du même document porte plus de métadonnées.
        extra_source = _source(meta, entry["source"]["index"])
        for field, value in extra_source.items():
            if field not in ("index", "excerpts") and field not in entry["source"] and value is not None:
                entry["source"][field] = value

        if excerpt:
            norm_excerpt = " ".join(excerpt.split())
            if norm_excerpt not in entry["seen_excerpts"]:
                entry["seen_excerpts"].add(norm_excerpt)
                entry["excerpts"].append(excerpt)

        if context_block:
            norm_context = " ".join(context_block.split())
            if norm_context not in entry["seen_contexts"]:
                entry["seen_contexts"].add(norm_context)
                entry["contexts"].append(context_block)

    for entry in grouped:
        entry["context_block"] = "\n---\n".join(entry["contexts"])
    return grouped


def _normalize_and_align_citations(
    answer: str,
    sources: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Expand grouped citations (`[1, 2]` -> `[1] [2]`) and re-index continuously with cited sources."""
    if not answer or not sources:
        return answer, sources

    # Sépare d'abord les citations multiples du type "[1, 2]" ou "[1; 3]" en "[1] [2]".
    def _expand_group(match: re.Match[str]) -> str:
        nums = re.findall(r"\d+", match.group(0))
        return " ".join(f"[{n}]" for n in nums)

    expanded = re.sub(r"\[\s*\d+(?:\s*[,;]\s*\d+)+\s*\]", _expand_group, answer)

    # Renumérotation continue [1]..[m] par ordre d'apparition dans la réponse.
    old_to_new: dict[int, int] = {}
    max_index = len(sources)

    drop_marker = "\x00DROP_CITE\x00"

    def _remap(match: re.Match[str]) -> str:
        old_idx = int(match.group(1))
        if old_idx < 1 or old_idx > max_index:
            return drop_marker
        if old_idx not in old_to_new:
            old_to_new[old_idx] = len(old_to_new) + 1
        return f"[{old_to_new[old_idx]}]"

    reindexed_answer = re.sub(r"\[(\d+)\]", _remap, expanded)
    if drop_marker in reindexed_answer:
        reindexed_answer = re.sub(
            rf"[ \t]*{re.escape(drop_marker)}[ \t]*(?=[.,;:!?])", "", reindexed_answer
        )
        reindexed_answer = re.sub(rf"[ \t]*{re.escape(drop_marker)}", "", reindexed_answer)
    reindexed_answer = reindexed_answer.strip()

    if not old_to_new:
        return reindexed_answer, sources

    aligned_sources: list[dict[str, Any]] = []
    for old_idx, new_idx in old_to_new.items():
        src = dict(sources[old_idx - 1])
        src["index"] = new_idx
        aligned_sources.append(src)
    return reindexed_answer, aligned_sources


def _retrieve_via_http(question: str, rag_server_url: str, top_k: int = TOP_K, neighbors: int = NEIGHBORS) -> list[dict[str, Any]]:
    """Query the standalone RAG server over HTTP (`POST /retrieve`)."""
    endpoint = f"{rag_server_url.rstrip('/')}/retrieve"
    try:
        response = httpx.post(
            endpoint,
            json={"query": question, "top_k": top_k, "neighbors": neighbors},
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        raise AskUnavailable(
            f"RAG server unreachable at {rag_server_url}: {exc}. "
            "Start it with: python -m src.rag.server --port 8001"
        ) from exc

    if response.status_code >= 400:
        detail = response.text
        try:
            detail = response.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise AskUnavailable(f"RAG server error ({response.status_code}): {detail}")

    payload = response.json()
    if not isinstance(payload, list):
        raise AskUnavailable("Unexpected response from the RAG server (/retrieve).")

    normalized: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, str):
            normalized.append({"text": item, "context_block": item, "metadata": {}})
    return normalized


def _retrieve_in_process(rag_state: Any, question: str, top_k: int = TOP_K, neighbors: int = NEIGHBORS) -> list[dict[str, Any]]:
    """Retrieve passages directly from an injected in-process rag_app.state (used in tests)."""
    from src.rag.server.app import _retrieve_results

    collection = getattr(rag_state, "collection", None)
    embedder = getattr(rag_state, "llm_client", None)
    if collection is None or embedder is None:
        raise AskUnavailable("the RAG is not loaded (see /api/models/status)")
    if int(collection.count()) == 0:
        raise AskUnavailable("the ChromaDB database is empty: python -m src.rag.storage.download_chroma_release")
    try:
        vector = embedder.embed_texts([question])[0]
    except Exception as exc:  # noqa: BLE001
        raise AskUnavailable(f"Could not compute the embedding of the question: {exc}") from exc

    results = _retrieve_results(
        collection=collection,
        query_vector=vector,
        top_k=min(top_k, int(collection.count())),
        neighbors=neighbors,
    )
    return [item.model_dump() for item in results]


def _build_gemini_contents(
    question: str,
    retrieved: list[dict[str, Any]],
    history: list[dict[str, str]] | None,
) -> list[Any]:
    """Format conversation history and numbered unique-source extracts for Gemini `generate_content`."""
    from google.genai import types

    blocks: list[str] = []
    for i, item in enumerate(retrieved, 1):
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        title = _clean_text(source.get("title")) if source else None
        header = f"[{i}] ({title})" if title else f"[{i}]"
        body = str(item.get("context_block") or item.get("text") or "").strip()
        blocks.append(f"{header}\n{body}" if body else header)
    extracts = "\n\n".join(blocks)

    contents: list[Any] = []
    for turn in (history or [])[-MAX_HISTORY:]:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()
        if not content or role not in ("user", "assistant", "model"):
            continue
        gemini_role = "model" if role in ("assistant", "model") else "user"
        contents.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=content)]))

    prompt = (
        f"NASA document excerpts:\n\n{extracts}\n\n"
        f"User question: {question}\n"
        "Write a concise answer in English (without copying the raw excerpts), "
        "citing each source used with its number in square brackets: [1], [2], etc."
    )
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
    return contents


def _candidate_gemini_models() -> list[str]:
    """Return ordered list of Gemini model IDs (primary + optional fallbacks)."""
    primary = (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
    raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS")
    if raw_fallbacks is None:
        fallbacks = list(DEFAULT_GEMINI_FALLBACK_MODELS)
    else:
        fallbacks = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]

    candidates: list[str] = []
    for name in [primary, *fallbacks]:
        if name and name not in candidates:
            candidates.append(name)
    return candidates


def _generate_with_gemini(
    question: str,
    retrieved: list[dict[str, Any]],
    history: list[dict[str, str]] | None,
    *,
    gemini_client: Any | None = None,
) -> tuple[str, str]:
    """Call Google Gemini Flash using GEMINI_API_KEY (with fallback on transient overload) and return `(answer, model_name)`."""
    from google import genai
    from google.genai import types

    load_dotenv()
    candidates = _candidate_gemini_models()
    client = gemini_client
    if client is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise AskUnavailable(
                "Google API key missing: set GEMINI_API_KEY in the .env file at the project root."
            )
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
        )

    contents = _build_gemini_contents(question, retrieved, history)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=1024,
    )

    last_exc: Exception | None = None
    for model_name in candidates:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            answer = (getattr(response, "text", None) or "").strip()
            return answer, model_name
        except Exception as exc:  # noqa: BLE001 - essaie le modèle de secours suivant en cas de surcharge/503
            last_exc = exc
            LOGGER.warning("Échec Gemini avec '%s' (%s), essai suivant si disponible.", model_name, exc)

    assert last_exc is not None
    raise last_exc


def ask(
    rag_state: Any | None,
    question: str,
    history: list[dict[str, str]] | None = None,
    *,
    rag_server_url: str | None = None,
    gemini_client: Any | None = None,
) -> dict[str, Any]:
    """Retrieve relevant NASA document passages from the RAG server and synthesize an answer with Gemini."""
    if rag_state is not None:
        retrieved = _retrieve_in_process(rag_state, question)
    else:
        resolved_rag_url = (
            rag_server_url
            or os.getenv("RAG_SERVER_URL")
            or DEFAULT_RAG_SERVER_URL
        ).strip()
        retrieved = _retrieve_via_http(question, resolved_rag_url)

    if not retrieved:
        return {
            "answer": NO_SOURCE_ANSWER,
            "sources": [],
            "model": (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
        }

    grouped = _group_retrieved_by_source(retrieved)
    sources = [entry["source"] for entry in grouped]

    try:
        answer, model_name = _generate_with_gemini(
            question,
            grouped,
            history,
            gemini_client=gemini_client,
        )
    except AskUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - le chat reste utilisable avec les seuls passages
        LOGGER.warning("Génération Gemini impossible (%s) : renvoi des sources seules", exc)
        return {
            "answer": LLM_DOWN_ANSWER,
            "sources": sources,
            "model": (os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip(),
        }

    if not answer:
        return {
            "answer": NO_SOURCE_ANSWER,
            "sources": [],
            "model": model_name,
        }

    aligned_answer, aligned_sources = _normalize_and_align_citations(answer, sources)
    return {
        "answer": aligned_answer,
        "sources": aligned_sources,
        "model": model_name,
    }
