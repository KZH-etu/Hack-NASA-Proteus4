"""FastAPI web server package for NASA RAG retrieval."""

from src.rag.server.app import app, create_app, main

__all__ = ["app", "create_app", "main"]
