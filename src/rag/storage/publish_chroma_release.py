"""CLI script to compress local ChromaDB and publish it as a GitHub Release."""

from __future__ import annotations

import argparse
import logging
import sys

from src.rag.config import RagConfig
from src.rag.storage.chroma_release import publish_chroma_release


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, package ChromaDB, and publish a GitHub Release."""
    parser = argparse.ArgumentParser(
        description="Compresse data/rag/chroma_db/ et publie une GitHub Release via gh."
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Tag de release explicite (défaut: chroma-db-vYYYYMMDD-HHMMSS).",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Notes de release personnalisées.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compresse l'archive localement sans publier sur GitHub.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Ignore la lecture du nombre de chunks ChromaDB avant compression.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    config = RagConfig.from_env()

    try:
        manifest = publish_chroma_release(
            config,
            tag_name=args.tag,
            notes=args.notes,
            dry_run=args.dry_run,
            skip_verify=args.skip_verify,
        )
    except Exception as exc:
        print(f"[Erreur] {exc}", file=sys.stderr)
        return 1

    size_mb = manifest.size_bytes / (1024 * 1024)
    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}Release ChromaDB prête : tag={manifest.tag_name} | "
        f"chunks={manifest.chunk_count} | taille={size_mb:.2f} Mo | "
        f"sha256={manifest.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
