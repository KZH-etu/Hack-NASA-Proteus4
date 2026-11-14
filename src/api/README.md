# API HEPHAISTOS

L'application repose sur deux serveurs complémentaires :

```bash
# 1. Serveur RAG (ChromaDB + embeddings LM Studio) sur le port 8001
python -m src.rag.server --host 127.0.0.1 --port 8001

# 2. API principale HEPHAISTOS (/predict, /ask via Google Gemini, interface web) sur le port 8000
python -m src.api --host 127.0.0.1 --port 8000
```

| Route | Rôle | Code |
|---|---|---|
| `GET /` | interface HEPHAISTOS (`app/frontend_hephaistos/`) | `app.py` |
| `POST /predict` | prédiction au format de la page → `model_gp`, avec les essais NASA proches en sources | `predict.py` |
| `GET /models/status` | état des modèles ML, du serveur RAG distant (`:8001`) et de la config Gemini | `app.py` |
| `POST /ask` | chat : interroge `POST {RAG_SERVER_URL}/retrieve`, rédige avec `GEMINI_MODEL` (`gemini-3.8-flash`) et renvoie réponse + sources complètes | `ask.py` |

## Variables d'environnement (`.env`)

Voir [`.env.example`](../../.env.example) à la racine du dépôt :
- `GEMINI_API_KEY` : clé API Google AI Studio (obligatoire pour `/ask`).
- `GEMINI_MODEL` : modèle Gemini utilisé par `/ask` (défaut : `gemini-3.8-flash`).
- `RAG_SERVER_URL` : URL du serveur RAG (défaut : `http://127.0.0.1:8001`).
- `HEPHAISTOS_API_KEY` : clé facultative vérifiée sur l'en-tête `X-API-Key`.

Tests : `pytest src/api/tests`.
