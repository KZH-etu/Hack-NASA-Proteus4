# Flame in Freefall — Hack-NASA-Proteus4

> NASA Space Apps Challenge 2026 (Paris) — challenge « Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data ».

**Pitch :** un dashboard qui cartographie des décennies d'essais NASA de combustion en microgravité, prédit le comportement d'une flamme avec son incertitude, et recommande la prochaine expérience ISS la plus utile pour un scénario de mission Lune/Mars, en citant ses sources.

## Démo

_À venir (lien Streamlit Community Cloud + vidéo)._

## Installation

_À compléter._

## Architecture

_À compléter._

## Base vectorielle RAG (ChromaDB)

### Comment elle est stockée

La base vectorielle locale (`data/rag/chroma_db/`) est **exclue de Git** (`.gitignore`) afin d'éviter de stocker des fichiers binaires volumineux dans l'historique du dépôt. Elle est compressée au format `.tar.gz` (`chroma_db.tar.gz`) accompagnée d'un manifeste SHA-256 (`chroma_db_manifest.json`) et publiée sous forme de **GitHub Release** avec un tag `chroma-db-v*`.

### Comment la récupérer

> **Prérequis :** le dépôt étant privé, le CLI GitHub [`gh`](https://cli.github.com/) doit être installé et authentifié (`gh auth login`).

1. **Téléchargement manuel (recommandé avant usage hors ligne) :**
   ```bash
   python -m src.rag.storage.download_chroma_release
   ```
   Le script récupère la dernière release `chroma-db-*`, vérifie son empreinte SHA-256, la décompresse et l'installe dans `data/rag/chroma_db/` (un fichier `.release_manifest.json` y mémorise la version locale).
   - Vérifier si une mise à jour est disponible sans télécharger : `python -m src.rag.storage.download_chroma_release --check-only`
   - Forcer le re-téléchargement : `python -m src.rag.storage.download_chroma_release --force`

2. **Récupération automatique au lancement de HEPHAISTOS (`FastAPI` + `Uvicorn`) :**
   ```bash
   python -m src.api          # interface, prédictions et chat sur http://127.0.0.1:8000
   ```
   Le RAG est intégré à ce serveur (routes `/api/rag/health` et `/api/rag/retrieve`). Il peut aussi tourner seul : `python -m src.rag.server --port 8001`.
   Au démarrage, le serveur vérifie automatiquement que `data/rag/chroma_db/` est présent et à jour par rapport à la dernière release GitHub, et le télécharge si nécessaire avant d'exposer `GET /health` et `POST /retrieve` (voir [`src/rag/server/API.md`](src/rag/server/API.md)).

3. **Publier une nouvelle version (après ré-indexation) :**
   ```bash
   python -m src.rag.storage.publish_chroma_release
   ```
   *(Plus de détails sur l'organisation de `src/rag/` dans [`src/rag/README.md`](src/rag/README.md).)*

## Sources

_Voir [`data/SOURCES.md`](data/SOURCES.md)._

## Équipe

_À compléter._
