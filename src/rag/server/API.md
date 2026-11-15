# Documentation de l'API RAG (`src/rag/server`)

API REST **FastAPI + Uvicorn** dédiée au retrieval sémantique sur la base vectorielle ChromaDB des rapports NASA (`nasa_scientific_reports`).

> Dans le serveur HEPHAISTOS (`python -m src.api`), ces routes sont intégrées sous `/api/rag/health` et `/api/rag/retrieve`. Lancé seul, ce serveur les expose à la racine (ci-dessous).

## Lancement & Synchronisation au démarrage

```bash
python -m src.rag.server --host 127.0.0.1 --port 8001
# ou directement avec Uvicorn :
uvicorn src.rag.server:app --host 127.0.0.1 --port 8001
```

Avant d'accepter des requêtes (`lifespan`), le serveur :
1. Vérifie via `gh` que `data/rag/chroma_db/` est présent et aligné sur la dernière release GitHub (`chroma-db-*`).
2. Télécharge et décompresse automatiquement la dernière release si la base locale est absente ou obsolète (`RAG_SKIP_CHROMA_SYNC=1` ou `--skip-sync` pour désactiver).
3. Ouvre la collection ChromaDB (`nasa_scientific_reports`) et initialise le client d'embedding OpenAI-compatible de la webapp (`https://ai.derveloy.eu/v1`, modèle `qwen3-embedding:0.6b`, configurable via `WEBAPP_EMBEDDING_BASE_URL` / `WEBAPP_EMBEDDING_MODEL` / `QWEN3_EMBEDDING`).

- **URL de base par défaut :** `http://127.0.0.1:8001`
- **Documentation interactive Swagger / OpenAPI :** `GET /docs` et `GET /openapi.json`
- **CORS :** activé (`Access-Control-Allow-Origin: *`)

---

## Endpoints

### 1. `GET /health`

Vérifie que le serveur est opérationnel, retourne l'état de la synchronisation ChromaDB au démarrage ainsi que le nombre total de chunks disponibles.

#### Paramètres
Aucun.

#### Réponse `200 OK` (`application/json`)

| Champ | Type | Description |
|---|---|---|
| `status` | `string` | État général du serveur (`"ok"`). |
| `sync_status` | `string` | Résultat du check ChromaDB au démarrage : `"up_to_date"`, `"downloaded"`, `"local_fallback"` ou `"skipped"`. |
| `release_tag` | `string \| null` | Tag GitHub Release actif (ex. `"chroma-db-v20261114-203450"`), ou `null` si inconnu/ignoré. |
| `collection` | `string` | Nom de la collection ChromaDB interrogée (`"nasa_scientific_reports"`). |
| `chunk_count` | `integer` | Nombre total de chunks indexés dans la collection. |

#### Exemple

```bash
curl -s http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "sync_status": "up_to_date",
  "release_tag": "chroma-db-v20261114-203450",
  "collection": "nasa_scientific_reports",
  "chunk_count": 21374
}
```

---

### 2. `POST /retrieve`

Calcule l'embedding dense de la requête via le endpoint OpenAI-compatible de la webapp (`WEBAPP_EMBEDDING_MODEL`, défaut `qwen3-embedding:0.6b` sur `https://ai.derveloy.eu/v1`), récupère les `top_k` chunks les plus proches dans ChromaDB, va chercher pour chaque hit ses chunks collés avant et après dans le même document (`chunk_index - neighbors .. chunk_index + neighbors`), concatène leurs textes (en fusionnant les chevauchements exacts) et renvoie une **liste d'objets structurés** (`RetrieveResult`) contenant le texte extrait, le bloc formaté LLM et les métadonnées documentaires (titre, auteurs, année, mission, lien PDF, lien NASA...).

#### Corps de la requête (`application/json`)

| Champ | Type | Requis | Défaut | Contraintes / Description |
|---|---|---|---|---|
| `query` | `string` | Oui | — | Question ou requête en langage naturel (`min_length=1`). |
| `top_k` | `integer` | Non | `5` | Nombre de hits correspondants recherchés dans ChromaDB (`1 <= top_k <= 50`). |
| `neighbors` | `integer` | Non | `1` | Nombre de chunks adjacents récupérés **avant et après** chaque hit (`0 <= neighbors <= 5`). Par défaut `1` (1 avant + 1 après = les 2 chunks collés). |

#### Réponse `200 OK` (`application/json`)

Type : `array<RetrieveResult>` (`list[RetrieveResult]`).

| Champ | Type | Description |
|---|---|---|
| `text` | `string` | Texte fusionné du chunk pertinent et de ses voisins (`[chunk_index - neighbors .. chunk_index + neighbors]`). |
| `context_block` | `string` | Passage complet préfixé d'un en-tête documentaire prêt à être injecté dans un prompt LLM. |
| `metadata` | `object` | Métadonnées structurées issues de ChromaDB (`id_pdf`, `chunk_index`, `title`, `authors`, `experiment_year`, `mission_program`, `source_type`, `headers_path`, `pdf_url`, `experiment_url`, `ntrs_id`, `page`). |

#### Codes d'erreur

| Code HTTP | Cas | Détail |
|---|---|---|
| `422 Unprocessable Entity` | Requête invalide | `query` vide/manquant, `top_k` hors `[1, 50]` ou `neighbors` hors `[0, 5]`. |
| `503 Service Unavailable` | Serveur d'embedding inaccessible | Impossible de générer l'embedding de la requête (`LMStudioClient.embed_texts` en échec). |

#### Exemple `curl`

```bash
curl -s -X POST http://127.0.0.1:8001/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "heptane droplet extinction diameter in microgravity",
    "top_k": 3,
    "neighbors": 1
  }'
```

#### Exemple de réponse `200 OK`

```json
[
  {
    "text": "Texte du chunk précédent... Texte du chunk correspondant... Texte du chunk suivant...",
    "context_block": "Document : Detailed Results From FLEX\nAuteurs : F. L. Dryer, V. Nayagam | Mission : ISS | Année : 2015 | Source : ntrs\nSection : Results > Flame Extinction\nURL : https://ntrs.nasa.gov/citations/20150023456\n---\nTexte du chunk précédent... Texte du chunk correspondant... Texte du chunk suivant...",
    "metadata": {
      "id_pdf": "doc-123",
      "chunk_index": 4,
      "title": "Detailed Results From FLEX",
      "authors": "F. L. Dryer, V. Nayagam",
      "experiment_year": 2015,
      "mission_program": "ISS",
      "source_type": "ntrs",
      "headers_path": "Results > Flame Extinction",
      "pdf_url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/20150023456.pdf",
      "experiment_url": "https://ntrs.nasa.gov/citations/20150023456",
      "ntrs_id": "20150023456",
      "page": null
    }
  }
]
```
