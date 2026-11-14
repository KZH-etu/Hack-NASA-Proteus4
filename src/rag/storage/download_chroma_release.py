"""CLI script to check, download, and extract the latest ChromaDB GitHub Release."""

from __future__ import annotations

import argparse
import logging
import sys

from src.rag.config import RagConfig
from src.rag.storage.chroma_release import ensure_chroma_db_up_to_date


def main(argv: list[str] | None = None) -> int:
    """Ensure local ChromaDB is synchronized with the latest GitHub Release."""
    parser = argparse.ArgumentParser(
        description="Télécharge et décompresse la dernière release ChromaDB depuis GitHub."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force le re-téléchargement même si la base locale est déjà à jour.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Vérifie uniquement si une mise à jour est disponible sans télécharger.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    config = RagConfig.from_env()

    try:
        result = ensure_chroma_db_up_to_date(
            config,
            force=args.force,
            check_only=args.check_only,
        )
    except Exception as exc:
        print(f"[Erreur] {exc}", file=sys.stderr)
        return 1

    print(
        f"[{result.status}] {result.message} "
        f"(dossier={result.chroma_dir}, chunks={result.chunk_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
