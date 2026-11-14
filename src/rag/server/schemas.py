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


class RetrieveMetadata(BaseModel):
    """Document and chunk metadata associated with a retrieved passage."""

    id_pdf: str | None = Field(default=None, description="Identifiant interne du document PDF.")
    chunk_index: int | None = Field(default=None, description="Index du chunk central dans le document.")
    title: str | None = Field(default=None, description="Titre du document ou du rapport scientifique.")
    authors: str | None = Field(default=None, description="Auteurs du document.")
    experiment_year: int | None = Field(default=None, description="Année de rédaction ou d'expérience.")
    mission_program: str | None = Field(default=None, description="Programme ou mission NASA associé(e).")
    source_type: str | None = Field(default=None, description="Origine documentaire (ex. ntrs, psi).")
    headers_path: str | None = Field(default=None, description="Fil d'Ariane des sections Markdown.")
    pdf_url: str | None = Field(default=None, description="Lien direct vers le PDF source.")
    experiment_url: str | None = Field(default=None, description="Lien vers la fiche NASA / NTRS.")
    ntrs_id: str | None = Field(default=None, description="Identifiant NTRS extrait de l'URL si disponible.")
    page: int | None = Field(default=None, description="Numéro de page du chunk si disponible.")


class RetrieveResult(BaseModel):
    """Single retrieved passage containing merged text and full document metadata."""

    text: str = Field(..., description="Texte fusionné du chunk pertinent et de ses voisins.")
    context_block: str = Field(
        ...,
        description="Passage formaté avec en-tête documentaire prêt pour un prompt LLM.",
    )
    metadata: RetrieveMetadata = Field(
        default_factory=RetrieveMetadata,
        description="Métadonnées structurées du document source.",
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
