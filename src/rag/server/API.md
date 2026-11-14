# Documentation de l'API RAG (`src/rag/server`)

API REST **FastAPI + Uvicorn** dédiée au retrieval sémantique sur la base vectorielle ChromaDB des rapports NASA (`nasa_scientific_reports`).

## Lancement & Synchronisation au démarrage

```bash
python -m src.rag.server --host 127.0.0.1 --port 8000
# ou directement avec Uvicorn :
uvicorn src.rag.server:app --host 127.0.0.1 --port 8000
```

Avant d'accepter des requêtes (`lifespan`), le serveur :
1. Vérifie via `gh` que `data/rag/chroma_db/` est présent et aligné sur la dernière release GitHub (`chroma-db-*`).
2. Télécharge et décompresse automatiquement la dernière release si la base locale est absente ou obsolète (`RAG_SKIP_CHROMA_SYNC=1` ou `--skip-sync` pour désactiver).
3. Ouvre la collection ChromaDB (`nasa_scientific_reports`) et initialise le client d'embedding LM Studio (`text-embedding-qwen3-embedding-0.6b`).

- **URL de base par défaut :** `http://127.0.0.1:8000`
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

Calcule l'embedding dense de la requête via LM Studio (`text-embedding-qwen3-embedding-0.6b`) et retourne les `top_k` chunks les plus proches sémantiquement dans ChromaDB, accompagnés des métadonnées complètes du document d'origine.

#### Corps de la requête (`application/json`)

| Champ | Type | Requis | Défaut | Contraintes / Description |
|---|---|---|---|---|
| `query` | `string` | Oui | — | Question ou requête en langage naturel (`min_length=1`). |
| `top_k` | `integer` | Non | `5` | Nombre maximum de chunks à retourner (`1 <= top_k <= 50`). |
| `where` | `object \| null` | Non | `null` | Filtre optionnel ChromaDB sur les métadonnées (ex. `{"source_type": "ntrs"}` ou `{"mission_program": "ISS"}`). |

#### Réponse `200 OK` (`application/json`)

| Champ | Type | Description |
|---|---|---|
| `query` | `string` | Requête envoyée. |
| `count` | `integer` | Nombre effectif de chunks retournés. |
| `results` | `array<RetrieveChunk>` | Liste des chunks triés par pertinence (distance croissante). |

##### Structure d'un objet `RetrieveChunk`

| Champ | Type | Description |
|---|---|---|
| `id` | `string` | Identifiant UUID du chunk dans ChromaDB. |
| `document` | `string` | Contenu textuel du chunk (`Contexte : [Fil d'Ariane] \n Texte : [Contenu]`). |
| `distance` | `float \| null` | Distance vectorielle L2 calculée par ChromaDB (plus petite = plus pertinent). |
| `metadata` | `object` | Métadonnées complètes du document source copiées sur le chunk (voir tableau ci-dessous). |

##### Champs de `metadata` sur chaque chunk

| Clé | Type | Description |
|---|---|---|
| `id_pdf` | `string` | UUID4 unique du document dans `tracking.db`. |
| `title` | `string` | Titre du rapport ou de la ressource NASA. |
| `source_type` | `string` | Origine : `"ntrs"`, `"taskbook"`, `"psi"` ou `"autres"`. |
| `chunk_index` | `integer` | Position séquentielle du chunk dans le document (`0, 1, ...`). |
| `headers_path` | `string` | Fil d'Ariane hiérarchique des titres (ex. `"1. Introduction > 1.2 Objectives"`). |
| `mission_program` | `string` | Programme/mission NASA (ex. `"ISS"`, `"Shuttle"`, `"Apollo"`, `"Unknown"`). |
| `experiment_year` | `integer` | Année de l'expérience ou publication (`0` si inconnue). |
| `authors` | `string` | Auteur(s) séparés par des virgules (`"Unknown"` si inconnu). |
| `pdf_url` | `string` | URL directe vers le PDF source (chaîne vide si ressource HTML/JSON sans PDF). |
| `experiment_url` | `string` | URL de la fiche NASA / expérience d'origine. |

#### Codes d'erreur

| Code HTTP | Cas | Détail |
|---|---|---|
| `422 Unprocessable Entity` | Requête invalide | `query` vide/manquant ou `top_k` hors de `[1, 50]`. |
| `503 Service Unavailable` | LM Studio inaccessible | Impossible de générer l'embedding de la requête (`LMStudioClient.embed_texts` en échec). |

#### Exemple `curl`

```bash
curl -s -X POST http://127.0.0.1:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "query": "heptane droplet extinction diameter in microgravity",
    "top_k": 2,
    "where": {"source_type": "ntrs"}
  }'
```

#### Exemple de réponse `200 OK`

```json
{
  "query": "heptane droplet extinction diameter in microgravity",
  "count": 2,
  "results": [
    {
      "id": "8c1f2e7a-9b4d-4d6e-91c2-3f4a5b6c7d8e",
      "document": "Contexte : Results > Flame Extinction\nTexte : ...",
      "distance": 0.4128,
      "metadata": {
        "id_pdf": "0b8f4d91-...",
        "title": "Detailed Results From FLEX",
        "source_type": "ntrs",
        "chunk_index": 14,
        "headers_path": "Results > Flame Extinction",
        "mission_program": "ISS",
        "experiment_year": 2015,
        "authors": "F. L. Dryer, V. Nayagam",
        "pdf_url": "https://ntrs.nasa.gov/api/citations/20150023456/downloads/...",
        "experiment_url": "https://ntrs.nasa.gov/citations/20150023456"
      }
    }
  ]
}
```
