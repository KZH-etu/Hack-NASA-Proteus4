# 🚀 NASA Scientific RAG - Pipeline d'Ingestion Asynchrone

## 📋 Présentation
Ce projet implémente la phase d'ingestion d'un système RAG (Retrieval-Augmented Generation) spécialisé dans les rapports scientifiques de la NASA.

Le défi principal de ce projet est de traiter des documents complexes (tableaux, hiérarchies de titres, jargon scientifique) **entièrement en local**, sur des machines grand public ayant une mémoire vidéo (VRAM) limitée.

Pour y parvenir, l'architecture repose sur un pipeline en **3 étapes asynchrones (Batch Processing)**. Cela permet de décharger la mémoire entre chaque tâche lourde et de garantir une reprise automatique en cas d'erreur lors du traitement d'un lot de PDFs.

---

## 🛠️ Stack Technique

- **OCR Structuré :** `Marker` (Mode Balanced) pour convertir les PDFs en Markdown (préservation des tableaux et titres).
- **LLM d'Extraction :** `Phi-3.5-mini-instruct GGUF` (Microsoft). Ultra-léger, il lit le début des documents pour extraire les métadonnées en JSON pur.
- **Modèle d'Embedding :** `Qwen3-Embedding 0.6B`. Modèle dense hautement performant pour la recherche sémantique.
- **Serveur d'Inférence :** `LM Studio`. Remplace Docker. Fournit une API locale standard (type OpenAI) pour faire tourner Phi-3.5 puis Qwen3.
- **Base Vectorielle :** `ChromaDB` (Persistent Mode). Base de données 100% Python ("Serverless") pour une portabilité maximale chez l'évaluateur.
- **Base de Suivi :** `SQLite3` (Standard Python). Fait le pont entre les fichiers bruts et ChromaDB.

---

## 🏗️ Architecture du Pipeline en 3 Étapes

### 🟢 Étape 1 : OCR & Initialisation de la Table de Suivi
*   **Action :** Le script parcourt le dossier de PDFs bruts et utilise Marker pour générer les fichiers Markdown (`.md`).
*   **Tracking :** Création d'une base SQLite intermédiaire (`tracking.db`) liant les fichiers locaux aux URL d'origine.
*   **Schéma SQLite (Fin de l'Étape 1) :**
    *   `document_id` (Integer Auto-incrémenté)
    *   `pdf_filename` (String) / `md_filename` (String)
    *   `pdf_url` (URL du site de la NASA)
    *   `experiment_url` (URL de l'expérience)

### 🟡 Étape 2 : Extraction des Métadonnées (LLM)
*   **Action :** Le script lit les ~3000 premiers caractères de chaque fichier Markdown et interroge **Phi-3.5-mini** (via LM Studio) avec un prompt strict pour générer un JSON.
*   **Mise à jour SQLite :** La table est enrichie avec les données déduites :
    *   `mission_program` (String - ex: Apollo, Skylab, ISS)
    *   `experiment_year` (Integer)
    *   `authors` (String)

### 🔴 Étape 3 : Double Chunking & Indexation Vectorielle
*   **Action :** Le script découpe le texte pour le modèle **Qwen3-Embedding** en deux passes via LangChain :
    1.  `MarkdownHeaderTextSplitter` : Sépare le texte par sections logiques (`#`, `##`).
    2.  `RecursiveCharacterTextSplitter` : Limite la taille des paragraphes (~1000 caractères, chevauchement de 200).
*   **Astuce de contexte (Fil d'Ariane) :** Les niveaux de titres sont fusionnés en une seule chaîne (ex: `"1. Intro > 1.2 Objectifs"`) puis réinjectés dans le texte brut avant l'embedding pour maximiser la compréhension mathématique de Qwen3.
*   **Schéma ChromaDB final par chunk :**
    *   `ids` : `chunk_id` (UUID)
    *   `documents` : `Contexte : [Fil d'Ariane] \n Texte : [Contenu du chunk]`
    *   `embeddings` : `dense_vector` (Généré par Qwen3)
    *   `metadatas` :
        *   `document_id` (Int) / `chunk_index` (Int)
        *   `headers_path` (String - Le fil d'Ariane complet)
        *   `mission_program` (String)
        *   `experiment_year` (Int)
        *   `authors` (String)
        *   `pdf_url` (String) / `experiment_url` (String)

*(Note : L'approche par vecteur creux/sparse vector a été écartée pour se concentrer sur la densité sémantique via Qwen3).*

---