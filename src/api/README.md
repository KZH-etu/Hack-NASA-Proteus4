# API HEPHAISTOS

Un seul serveur FastAPI pour l'interface, les prédictions, l'étude des données et le chat :

```bash
python -m src.api                 # http://127.0.0.1:8000   (documentation interactive : /docs)
python -m src.api --no-rag        # sans le chat (prédictions seulement, sans ChromaDB ni LM Studio)
python -m src.api --skip-sync     # sans vérifier la release ChromaDB au démarrage
```

| Route | Rôle | Code |
|---|---|---|
| `GET /` | interface HEPHAISTOS (`app/frontend_hephaistos/index.html`) ; `GET /assets/...` : images, Chart.js | `app.py` |
| `POST /api/predict` | prédiction au format de la page → `model_gp`, avec les essais NASA proches en sources | `predict.py` |
| `GET /api/dataset/summary` | chiffres et séries de la page « Étude des données » | `dataset.py` |
| `GET /api/models/status` | état des modèles ML, du RAG et de la configuration Gemini | `app.py` |
| `POST /api/ask` | chat : passages du RAG, réponse rédigée par `GEMINI_MODEL` (`gemini-3.8-flash`), sources complètes | `ask.py` |
| `GET /api/rag/health`, `POST /api/rag/retrieve` | routes du serveur RAG (`src/rag/server`), reprises telles quelles | `src/rag/server` |

**RAG intégré :** au démarrage, `app.py` crée l'application du RAG avec `src.rag.server.create_app()` et exécute son démarrage (base ChromaDB, client d'embedding OpenAI-compatible pour la webapp) dans le même processus. Pour un **serveur RAG séparé** (par exemple sur une autre machine) : `python -m src.rag.server --port 8001` d'un côté, puis `python -m src.api --rag-url http://<machine>:8001` (ou `RAG_SERVER_URL` dans `.env`).

## Variables d'environnement (`.env`)

Voir [`.env.example`](../../.env.example) à la racine du dépôt :
- `GEMINI_API_KEY` : clé API Google AI Studio (obligatoire pour `/api/ask`).
- `GEMINI_MODEL` : modèle Gemini utilisé par `/api/ask` (défaut : `gemini-3.8-flash`).
- `QWEN3_EMBEDDING` : jeton Bearer pour le serveur d'embedding de la webapp (`WEBAPP_EMBEDDING_BASE_URL`, défaut `https://ai.derveloy.eu/v1`, modèle `WEBAPP_EMBEDDING_MODEL` défaut `qwen3-embedding:0.6b`).
- `RAG_SERVER_URL` : vide par défaut (RAG intégré) ; sinon URL d'un serveur RAG séparé.
- `HEPHAISTOS_API_KEY` : clé facultative vérifiée sur l'en-tête `X-API-Key`.

Tests : `pytest src/api/tests`.

## Fabriquer une archive à envoyer

```bash
python -m src.api.package                 # dist/HEPHAISTOS_demo.zip  (~1 Mo)  : interface + prédictions
python -m src.api.package --with-chat     # dist/HEPHAISTOS_chat.zip  (~150 Mo) : + chat (RAG + Gemini)
```

Le destinataire dézippe puis double-clique sur `lancer.bat` (Windows) ou lance `bash lancer.sh` (macOS, Linux) : environnement Python créé, dépendances installées, serveur(s) démarré(s), navigateur ouvert. Prérequis : Python 3.10+ ; pour le chat, en plus, un `.env` avec sa propre `GEMINI_API_KEY` et `QWEN3_EMBEDDING` (copié depuis `.env.example`).

- Seuls les fichiers suivis par git sont copiés. **Le `.env` n'est jamais inclus** (la clé reste chez soi).
- `--with-chat` inclut la base ChromaDB si elle est présente localement (`python -m src.rag.storage.download_chroma_release`) ; sinon (ou avec `--no-db`) elle est téléchargée au premier lancement, ce qui demande `gh auth login`.
- À refaire après chaque mise à jour des modèles ou de l'interface.
