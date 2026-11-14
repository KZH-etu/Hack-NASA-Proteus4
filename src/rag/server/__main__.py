"""Module entrypoint allowing `python -m src.rag.server`."""

from src.rag.server.app import main

if __name__ == "__main__":
    raise SystemExit(main())
