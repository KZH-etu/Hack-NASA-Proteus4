# 🚀 NASA Scientific RAG - Pipeline d'Ingestion Asynchrone

## 📋 Présentation
Ce projet implémente la phase d'ingestion d'un système RAG (Retrieval-Augmented Generation) spécialisé dans les rapports scientifiques et ressources web de la NASA.

Le défi principal de ce projet est de traiter des documents complexes (tableaux, hiérarchies de titres, jargon scientifique) **entièrement en local**, sur des machines grand public ayant une mémoire vidéo (VRAM) limitée.

Pour y parvenir, l'architecture repose sur un pipeline en **3 étapes asynchrones (Batch Processing)** pilotées par des scripts CLI autonomes (`ingestion/stage1_ocr.py`, `ingestion/stage2_metadata.py`, `ingestion/stage3_index.py`). Cela permet de décharger la mémoire entre chaque tâche lourde et de garantir une reprise automatique en cas d'erreur lors du traitement d'un lot de documents.

## 📁 Organisation de `src/rag/`

```text
src/rag/
├── config.py                     # Configuration centrale (RagConfig)
├── llm_client.py                 # Client LM Studio (Phi-3.5 & Qwen3 embeddings)
├── ingestion/                    # Pipeline d'ingestion et préparation des données
│   ├── fetch_ntrs.py             # Téléchargement du catalogue NTRS / Taskbook / PSI
│   ├── source_adapter.py         # Lecture de catalog.csv & déduction source_type
│   ├── db.py                     # Suivi SQLite (tracking.db)
│   ├── text_utils.py             # Nettoyage HTML -> Markdown structuré
│   ├── stage1_ocr.py
│   ├── stage2_metadata.py
│   └── stage3_index.py
├── storage/                      # Distribution de ChromaDB via GitHub Releases
│   ├── chroma_release.py
│   ├── publish_chroma_release.py
│   └── download_chroma_release.py
├── server/                       # Serveur Web FastAPI + Uvicorn
│   ├── app.py
│   ├── schemas.py
│   └── API.md                    # Descriptif détaillé des endpoints
└── tests/                        # Suite de tests unitaires
```

---

## 🛠️ Stack Technique

- **Source de vérité :** `data/raw/ntrs/catalog.csv` (généré par `fetch_ntrs.py`).
- **OCR Structuré :** `Marker` (Mode Balanced, avec fallback `pages/<id>.jsonl` / PyMuPDF) pour convertir les PDFs en Markdown.
- **LLM d'Extraction :** `Phi-3.5-mini-instruct GGUF` (Microsoft). Ultra-léger, il lit le début des documents (sans balises HTML) pour compléter les métadonnées manquantes en JSON pur.
- **Modèle d'Embedding :** `text-embedding-qwen3-embedding-0.6b`. Modèle dense hautement performant pour la recherche sémantique.
- **Serveur d'Inférence :** `LM Studio`. Fournit une API locale standard (type OpenAI) pour faire tourner Phi-3.5 puis Qwen3.
- **Base Vectorielle :** `ChromaDB` (Persistent Mode dans `data/rag/chroma_db`). Base de données 100% Python ("Serverless") pour une portabilité maximale.
- **Base de Suivi :** `SQLite3` (`data/rag/tracking.db`). Fait le pont entre `catalog.csv`, les fichiers bruts et ChromaDB via l'identifiant UUID `id_pdf`.

---

## 🏗️ Architecture du Pipeline en 3 Étapes

### 🟢 Étape 1 : Normalisation UUID, Déduction du Type & OCR PDF (`python -m src.rag.ingestion.stage1_ocr`)
*   **Action :** Le script lit les documents `.pdf` de `data/raw/ntrs/catalog.csv`, attribue un **UUID** (`id_pdf`) comme clé primaire unique, copie/renomme le fichier en `{id_pdf}.pdf` dans `data/rag/pdfs/`, puis utilise **Marker** pour générer `{id_pdf}.md` dans `data/rag/markdown/` (avec fallback sur `data/raw/ntrs/pages/<source_id>.jsonl` si Marker échoue).
*   **Déduction du type (`source_type`) :** Déduit automatiquement à partir du champ `url` du catalogue :
    *   `ntrs` (`ntrs.nasa.gov`)
    *   `taskbook` (`taskbook`)
    *   `psi` (`psi.nasa.gov`)
    *   `autres` (tout autre domaine)
*   **Schéma SQLite (`tracking.db`) :**
    *   `id_pdf` (String UUID — `PRIMARY KEY`)
    *   `source_id` (String — `id` d'origine dans `catalog.csv`)
    *   `pdf_filename` (`{id_pdf}.pdf` / `{id_pdf}.html` / `{id_pdf}.json`) / `md_filename` (`{id_pdf}.md`)
    *   `title` (String — titre issu du catalogue)
    *   `source_type` (String — `ntrs` | `taskbook` | `psi` | `autres`)
    *   `pdf_url` (URL du PDF) / `experiment_url` (champ `url` du catalogue)
    *   `authors` (String) / `experiment_year` (Integer) / `mission_program` (String)
    *   `ocr_status`, `metadata_status`, `index_status`, `error_message`, `updated_at`

### 🟡 Étape 2 : Intégration HTML/JSON & Enrichissement des Métadonnées (`python -m src.rag.ingestion.stage2_metadata`)
*   **Intégration pré-extraction :** Juste avant l'appel LLM, les pages `.html` (`WEB_PAGE`, `TASK_BOOK`) et fiches `.json` (`PSI_INVESTIGATION`) de `catalog.csv` sont intégrées dans `tracking.db` avec leur UUID `id_pdf`. Les balises HTML sont supprimées tout en conservant la structure des titres (`<h1>`, `<h2>`, `<h3>` → `#`, `##`, `###`) dans `{id_pdf}.md`.
*   **Action LLM :** Le script lit les ~3000 premiers caractères nettoyés (sans aucune balise HTML) et interroge **Phi-3.5-mini** (via LM Studio) pour compléter uniquement les champs manquants (`mission_program`, et `experiment_year`/`authors` si absents du catalogue) sans écraser les données déjà renseignées.

### 🔴 Étape 3 : Double Chunking & Indexation Vectorielle (`python -m src.rag.ingestion.stage3_index`)
*   **Action :** Le script supprime toute éventuelle balise HTML résiduelle, puis découpe le texte pour **Qwen3-Embedding** en deux passes via LangChain :
    1.  `MarkdownHeaderTextSplitter` : Sépare le texte par sections logiques (`#`, `##`, `###`), y compris celles issues des titres HTML.
    2.  `RecursiveCharacterTextSplitter` : Limite la taille des paragraphes (~1000 caractères, chevauchement de 200).
*   **Astuce de contexte (Fil d'Ariane) :** Les niveaux de titres sont fusionnés en une seule chaîne (ex: `"1. Intro > 1.2 Objectifs"`) puis réinjectés dans le texte brut avant l'embedding pour maximiser la compréhension sémantique de Qwen3.
*   **Schéma ChromaDB final par chunk :**
    *   `ids` : `chunk_id` (UUID)
    *   `documents` : `Contexte : [Fil d'Ariane] \n Texte : [Contenu du chunk]`
    *   `embeddings` : `dense_vector` (Généré par Qwen3)
    *   `metadatas` :
        *   `id_pdf` (String — UUID du document)
        *   `title` (String — titre du document)
        *   `source_type` (String — `ntrs` | `taskbook` | `psi` | `autres`)
        *   `chunk_index` (Int)
        *   `headers_path` (String — Le fil d'Ariane complet)
        *   `mission_program` (String)
        *   `experiment_year` (Int)
        *   `authors` (String)
        *   `pdf_url` (String) / `experiment_url` (String)

*(Note : L'approche par vecteur creux/sparse vector a été écartée pour se concentrer sur la densité sémantique via Qwen3).*

---

## 📦 Stockage & Synchronisation ChromaDB (GitHub Releases)

La base vectorielle `data/rag/chroma_db/` est exclue de Git (`.gitignore`) et distribuée sous forme d'archive `.tar.gz` avec manifeste SHA-256 via **GitHub Releases** (en utilisant le CLI `gh` authentifié) :

- **Compresser et publier une nouvelle snapshot :**
  ```bash
  python -m src.rag.storage.publish_chroma_release
  # Option test sans upload :
  python -m src.rag.storage.publish_chroma_release --dry-run
  ```
- **Télécharger et décompresser la dernière release dans `data/rag/chroma_db/` :**
  ```bash
  python -m src.rag.storage.download_chroma_release
  # Option vérification seule :
  python -m src.rag.storage.download_chroma_release --check-only
  ```

## 🌐 Serveur Web RAG (`FastAPI` + `Uvicorn`)

Au démarrage (`lifespan`), le serveur vérifie automatiquement si `data/rag/chroma_db/` est présent et à jour par rapport à la dernière release GitHub (`chroma-db-*`), et la télécharge si nécessaire avant d'exposer l'API :

```bash
python -m src.rag.server --host 127.0.0.1 --port 8000
# ou
uvicorn src.rag.server:app --host 127.0.0.1 --port 8000
```

La spécification complète de chaque endpoint (`GET /health`, `POST /retrieve`, schémas JSON et métadonnées) est détaillée dans [`src/rag/server/API.md`](server/API.md).
