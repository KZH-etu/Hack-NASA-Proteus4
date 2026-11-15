# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONWARNINGS=ignore \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RAG_SKIP_CHROMA_SYNC=1

WORKDIR /app

# 1. Dépendances Python d'abord : cette couche reste en cache tant que requirements-prod.txt ne change pas
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# 2. Données prétraitées et catalogue NTRS (changent rarement)
COPY data/processed ./data/processed
COPY data/raw/ntrs/catalog.csv data/raw/ntrs/catalog.jsonl ./data/raw/ntrs/

# 3. Base vectorielle ChromaDB (téléchargée dans data/rag/chroma_db avant le build)
#    data/rag/.gitkeep garantit que COPY reste valide même si chroma_db est monté via volume
COPY data/rag ./data/rag

# 4. Interface et code applicatif en dernier pour des rebuilds rapides
COPY app ./app
COPY src ./src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/models/status', timeout=3)" || exit 1

CMD ["python", "-m", "src.api", "--host", "0.0.0.0", "--port", "8000"]
