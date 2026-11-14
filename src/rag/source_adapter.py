"""Source document discovery and placeholder metadata adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Represents a raw PDF and its origin URLs from the source database."""

    pdf_filename: str
    pdf_path: Path
    pdf_url: str
    experiment_url: str


class SourceProvider(Protocol):
    """Contract for discovering PDFs and their associated source URLs."""

    def list_documents(self) -> list[SourceDocument]:
        """Return all available source documents."""
        ...


class PlaceholderSourceProvider:
    """Placeholder adapter scanning a local PDF folder and optional JSON manifest.

    Replace or supplement this class with a real database adapter once the
    NASA PDF repository and metadata database are available.
    """

    def __init__(self, pdf_dir: Path, manifest_path: Path | None = None) -> None:
        self.pdf_dir = Path(pdf_dir)
        self.manifest_path = Path(manifest_path) if manifest_path is not None else None

    def _load_manifest(self) -> dict[str, dict[str, str]]:
        if self.manifest_path is None or not self.manifest_path.exists():
            return {}
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in source manifest {self.manifest_path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ValueError(
                f"Source manifest {self.manifest_path} must be a JSON object mapping filename -> URLs."
            )
        return raw

    def list_documents(self) -> list[SourceDocument]:
        if not self.pdf_dir.exists() or not self.pdf_dir.is_dir():
            return []

        manifest = self._load_manifest()
        pdf_files = sorted(
            (p for p in self.pdf_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
            key=lambda p: p.name.lower(),
        )

        documents: list[SourceDocument] = []
        for pdf_path in pdf_files:
            entry = manifest.get(pdf_path.name, {})
            pdf_url = entry.get(
                "pdf_url",
                f"https://placeholder.nasa.gov/pdfs/{pdf_path.name}",
            )
            experiment_url = entry.get(
                "experiment_url",
                f"https://placeholder.nasa.gov/experiments/{pdf_path.stem}",
            )
            documents.append(
                SourceDocument(
                    pdf_filename=pdf_path.name,
                    pdf_path=pdf_path,
                    pdf_url=pdf_url,
                    experiment_url=experiment_url,
                )
            )
        return documents
