"""Pydantic request/response schemas for the FastAPI RAG retrieval server."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    """Input payload for semantic chunk retrieval with adjacent context."""

    query: str = Field(..., min_length=1, description="Question ou requête sémantique.")
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Nombre de chunks pertinents recherchés dans ChromaDB.",
    )
    neighbors: int = Field(
        default=1,
        ge=0,
        le=5,
        description=(
            "Nombre de chunks collés à récupérer avant et après chaque hit "
            "(1 = 1 avant + 1 après, soit les 2 chunks collés)."
        ),
    )


class HealthResponse(BaseModel):
    """Health check payload returned by GET /health."""

    status: str = Field(..., description="État général du serveur ('ok').")
    sync_status: str = Field(
        ...,
        description=(
            "Résultat de la synchronisation ChromaDB "
            "('up_to_date', 'downloaded', 'local_fallback', 'skipped')."
        ),
    )
    release_tag: str | None = Field(
        default=None,
        description="Tag de la release GitHub ChromaDB active.",
    )
    collection: str = Field(..., description="Nom de la collection ChromaDB interrogée.")
    chunk_count: int = Field(..., description="Nombre total de chunks indexés dans la collection.")
