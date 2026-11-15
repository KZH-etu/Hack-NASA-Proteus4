"""python -m src.api [--host 127.0.0.1] [--port 8000] [--skip-sync] [--no-rag] [--rag-url URL]"""

import argparse
import logging
import os

import uvicorn


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lance le serveur HEPHAISTOS (interface, prédictions, chat).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--skip-sync", action="store_true", help="ne vérifie pas la release ChromaDB au démarrage")
    parser.add_argument("--no-rag", action="store_true", help="sans le chat (prédictions seulement)")
    parser.add_argument("--rag-url", help="utiliser un serveur RAG séparé (python -m src.rag.server) au lieu du RAG intégré")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    if args.skip_sync:
        os.environ["RAG_SKIP_CHROMA_SYNC"] = "1"

    from src.api.app import create_app
    app = create_app(with_rag=not args.no_rag, rag_server_url=args.rag_url)
    print(f"Interface : http://{args.host}:{args.port}/   (API : /api/...   documentation : /docs)")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
