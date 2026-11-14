# API HEPHAISTOS

Un seul serveur pour l'interface, les prédictions et le chat :

```bash
python -m src.api            # http://127.0.0.1:8000  (documentation interactive : /docs)
```

| Route | Rôle | Code |
|---|---|---|
| `GET /` | interface HEPHAISTOS (`app/frontend_hephaistos/`) | `app.py` |
| `POST /predict` | prédiction au format de la page → `model_gp`, avec les essais NASA proches en sources | `predict.py` |
| `GET /models/status` | état des modèles (préchauffés au démarrage) et du RAG | `app.py` |
| `POST /ask` | chat : passages du RAG puis réponse rédigée par le LLM de LM Studio, avec sources | `ask.py` |
| `GET /health`, `POST /retrieve` | routes du serveur RAG (`src/rag/server`), reprises sans modification | `src/rag/server` |

Le serveur RAG de `src/rag/server` n'est pas modifié : `app.py` crée son application avec `create_app()`, exécute son démarrage (base ChromaDB, LM Studio) et reprend ses routes. Si le RAG ne démarre pas, les prédictions restent disponibles et `/models/status` donne la raison.

Variables utiles : `RAG_CHAT_MODEL` (modèle de chat de LM Studio), `HEPHAISTOS_API_KEY` (clé facultative, en-tête `X-API-Key`), et celles du RAG (`src/rag/config.py`).

Format des requêtes et réponses, et ce que la page doit afficher : `docs/guide_dashboard.md`. Tests : `pytest src/api/tests`.
