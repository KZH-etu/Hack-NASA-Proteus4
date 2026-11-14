"""Source document discovery from catalog.csv and URL-based type deduction."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def deduce_source_type(url: str | None) -> str:
    """Deduce document source type ('ntrs', 'taskbook', 'psi', 'autres') from url."""
    normalized = (url or "").strip().lower()
    if "ntrs.nasa.gov" in normalized:
        return "ntrs"
    if "taskbook" in normalized:
        return "taskbook"
    if "psi.nasa.gov" in normalized:
        return "psi"
    return "autres"


def _parse_year(raw_year: str | None) -> int | None:
    text = (raw_year or "").strip()
    if text.isdigit():
        return int(text)
    return None


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Represents a raw document and its metadata from catalog.csv."""

    pdf_filename: str
    pdf_path: Path
    pdf_url: str
    experiment_url: str
    source_id: str = ""
    title: str = ""
    authors: str = ""
    experiment_year: int | None = None
    source_type: str = "autres"
    file_ext: str = ".pdf"


class SourceProvider(Protocol):
    """Contract for discovering source documents and their associated metadata."""

    def list_documents(self) -> list[SourceDocument]:
        """Return all available source documents."""
        ...


class CatalogSourceProvider:
    """Source of truth adapter reading data/raw/ntrs/catalog.csv."""

    def __init__(
        self,
        catalog_csv_path: Path,
        base_dir: Path | None = None,
        extensions: tuple[str, ...] = (".pdf", ".html", ".json"),
    ) -> None:
        self.catalog_csv_path = Path(catalog_csv_path)
        self.base_dir = Path(base_dir) if base_dir is not None else Path.cwd()
        self.extensions = tuple(ext.lower() for ext in extensions)

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return self.base_dir / candidate

    def list_documents(self) -> list[SourceDocument]:
        if not self.catalog_csv_path.exists():
            raise FileNotFoundError(f"Catalog CSV not found: {self.catalog_csv_path}")

        documents: list[SourceDocument] = []
        with self.catalog_csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_path = (row.get("pdf_path") or "").strip()
                if not raw_path:
                    continue
                ext = Path(raw_path).suffix.lower()
                if ext not in self.extensions:
                    continue

                resolved_path = self._resolve_path(raw_path)
                if not resolved_path.exists():
                    continue

                url = (row.get("url") or "").strip()
                pdf_url = (row.get("pdf_url") or "").strip() or url
                source_id = (row.get("id") or resolved_path.stem).strip()

                documents.append(
                    SourceDocument(
                        pdf_filename=resolved_path.name,
                        pdf_path=resolved_path,
                        pdf_url=pdf_url,
                        experiment_url=url,
                        source_id=source_id,
                        title=(row.get("title") or "").strip(),
                        authors=(row.get("authors") or "").strip(),
                        experiment_year=_parse_year(row.get("year")),
                        source_type=deduce_source_type(url),
                        file_ext=ext,
                    )
                )
        return documents


class PlaceholderSourceProvider:
    """Fallback adapter scanning a local PDF folder and optional JSON manifest."""

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
                    source_id=pdf_path.stem,
                    title=pdf_path.stem,
                    source_type=deduce_source_type(experiment_url),
                    file_ext=".pdf",
                )
            )
        return documents
