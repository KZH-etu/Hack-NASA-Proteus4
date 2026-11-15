# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONWARNINGS=ignore \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RAG_SKIP_CHROMA_SYNC=1

WORKDIR /app

# L'image ne contient que l'environnement Python et les dépendances pip (mises en cache) ;
# le code et les données (src, app, data, chroma_db) sont montés en bind mount via docker-compose.prod.yml.
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/models/status', timeout=3)" || exit 1

CMD ["python", "-m", "src.api", "--host", "0.0.0.0", "--port", "8000"]
