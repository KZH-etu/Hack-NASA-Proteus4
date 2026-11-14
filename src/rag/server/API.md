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

Calcule l'embedding dense de la requête via LM Studio (`text-embedding-qwen3-embedding-0.6b`), récupère les `top_k` chunks les plus proches dans ChromaDB, va chercher pour chaque hit ses chunks collés avant et après dans le même document (`chunk_index - neighbors .. chunk_index + neighbors`), concatène leurs textes (en fusionnant les chevauchements exacts) et renvoie directement une **liste de chaînes de caractères** prête à être injectée dans le prompt d'un LLM.

#### Corps de la requête (`application/json`)

| Champ | Type | Requis | Défaut | Contraintes / Description |
|---|---|---|---|---|
| `query` | `string` | Oui | — | Question ou requête en langage naturel (`min_length=1`). |
| `top_k` | `integer` | Non | `5` | Nombre de hits correspondants recherchés dans ChromaDB (`1 <= top_k <= 50`). |
| `neighbors` | `integer` | Non | `1` | Nombre de chunks adjacents récupérés **avant et après** chaque hit (`0 <= neighbors <= 5`). Par défaut `1` (1 avant + 1 après = les 2 chunks collés). |

#### Réponse `200 OK` (`application/json`)

Type : `array<string>` (`list[str]`).

Chaque élément de la liste correspond à un hit et contient :
- un en-tête avec les métadonnées du document source (`Document`, `Auteurs`, `Mission`, `Année`, `Source`, `Section`, `URL`),
- suivi du texte concaténé du chunk précédent, du chunk trouvé et du chunk suivant (`[chunk_index - neighbors .. chunk_index + neighbors]`).

#### Codes d'erreur

| Code HTTP | Cas | Détail |
|---|---|---|
| `422 Unprocessable Entity` | Requête invalide | `query` vide/manquant, `top_k` hors `[1, 50]` ou `neighbors` hors `[0, 5]`. |
| `503 Service Unavailable` | LM Studio inaccessible | Impossible de générer l'embedding de la requête (`LMStudioClient.embed_texts` en échec). |

#### Exemple `curl`

```bash
curl -s -X POST http://127.0.0.1:8000/retrieve \
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
  "Document : Detailed Results From FLEX\nAuteurs : F. L. Dryer, V. Nayagam | Mission : ISS | Année : 2015 | Source : ntrs\nSection : Results > Flame Extinction\nURL : https://ntrs.nasa.gov/citations/20150023456\n---\nTexte du chunk précédent... Texte du chunk correspondant... Texte du chunk suivant...",
  "Document : ..."
]
```
