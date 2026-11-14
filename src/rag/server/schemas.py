"""Pydantic request/response schemas for the FastAPI RAG retrieval server."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    """Input payload for semantic chunk retrieval."""

    query: str = Field(..., min_length=1, description="Question ou requête sémantique.")
    top_k: int = Field(default=5, ge=1, le=50, description="Nombre de chunks à retourner.")
    where: dict[str, Any] | None = Field(
        default=None,
        description="Filtre optionnel sur les métadonnées ChromaDB.",
    )


class RetrieveChunk(BaseModel):
    """Single retrieved chunk with document metadata."""

    id: str = Field(..., description="Identifiant unique du chunk dans ChromaDB.")
    document: str = Field(..., description="Texte du chunk préfixé par son fil d'Ariane.")
    distance: float | None = Field(
        default=None,
        description="Distance vectorielle ChromaDB (plus elle est faible, plus le chunk est proche).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées du document source copiées sur le chunk.",
    )


class RetrieveResponse(BaseModel):
    """Response payload returned by POST /retrieve."""

    query: str = Field(..., description="Requête initiale envoyée par le client.")
    count: int = Field(..., description="Nombre effectif de chunks retournés.")
    results: list[RetrieveChunk] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check payload returned by GET /health."""

    status: str = Field(..., description="État général du serveur ('ok').")
    sync_status: str = Field(
        ...,
        description="Résultat de la synchronisation ChromaDB ('up_to_date', 'downloaded', 'local_fallback', 'skipped').",
    )
    release_tag: str | None = Field(
        default=None,
        description="Tag de la release GitHub ChromaDB active.",
    )
    collection: str = Field(..., description="Nom de la collection ChromaDB interrogée.")
    chunk_count: int = Field(..., description="Nombre total de chunks indexés dans la collection.")
