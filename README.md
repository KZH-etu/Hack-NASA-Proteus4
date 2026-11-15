# HEPHAISTOS — Flame in Freefall

> NASA Space Apps Challenge 2026 (Paris), team Proteus. Challenge: *Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data*.

HEPHAISTOS turns decades of NASA microgravity combustion tests into a fire-safety tool for future missions. It predicts how a flame behaves in given conditions (ISS cabin, lunar habitat, low-oxygen atmosphere…) **with an uncertainty range and the closest real NASA tests as evidence**, shows where NASA has and has not tested, and answers questions from NASA reports with cited sources.

## What the app does

| Page | What you get |
|---|---|
| **Prediction** | Pick a fuel state (solid, gas, droplet), a material and the conditions (O₂, pressure, air flow…). The app returns the probability that the flame goes out or is sustained, a 90% interval, a reliability badge, warnings when the conditions are outside what NASA tested, and the closest NASA tests with links to their source. Four mission presets: ISS cabin, lunar habitat, low-O₂ atmosphere, cabin material. |
| **Data study** | The NASA tests in numbers and charts: tests per experiment, outcomes, oxygen levels tested, an O₂ × pressure map with the ISS cabin and lunar habitat, data completeness, campaigns, and findings recomputed from the tables (for example: no droplet test below 70 kPa, so a 55 kPa lunar habitat is outside the measured data). |
| **Chat** | Questions in plain language about NASA combustion documents. Answers are written by Google Gemini **only from retrieved passages of NASA documents** and cite them, with the exact excerpt and a link to the PDF. |

Key figures: **1,720 tests** from **10 experiments** (12 NASA PSI campaigns), 99.5% in microgravity; **399 NASA documents** catalogued for the chat, 21,374 passages indexed.

## Quick start

Prerequisite: Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS / Linux: source .venv/bin/activate)
pip install -r requirements.txt

python -m src.api --no-rag        # Prediction + Data study on http://127.0.0.1:8000
python -m src.api                 # + Chat
```

The chat also needs:
1. a `.env` file (copy [`.env.example`](.env.example)) with your own `GEMINI_API_KEY` (Google AI Studio);
2. [LM Studio](https://lmstudio.ai/) running with the embedding model `text-embedding-qwen3-embedding-0.6b`;
3. the vector database. It is downloaded automatically at start-up from the GitHub release (the repository is private: run `gh auth login` first), or manually with `python -m src.rag.storage.download_chroma_release`.

Interactive API documentation: http://127.0.0.1:8000/docs. Options: `--skip-sync` (do not check the database release), `--rag-url <url>` (use a separate RAG server).

### Archive to share

```bash
python -m src.api.package               # dist/HEPHAISTOS_demo.zip (~1 MB): Prediction + Data study
python -m src.api.package --with-chat   # dist/HEPHAISTOS_chat.zip (~150 MB): + Chat
```

The recipient unzips it and double-clicks `lancer.bat` (Windows) or runs `bash lancer.sh` (macOS, Linux): the environment is created, dependencies installed, the server started and the browser opened. The `.env` file (API key) is never included.

## Architecture

```
NASA PSI (test tables)  ──► src/data ──► data/processed (1,720 tests, 1 table per fuel family)
                                              │
                                              ├──► src/models/model_gp  (Gaussian processes) ──┐
                                              └──► src/api/dataset.py   (Data study figures) ──┤
                                                                                               ├──► src/api  (one FastAPI server)
NASA NTRS / PSI (PDF reports) ──► src/rag/ingestion ──► ChromaDB ──► src/rag/server ──────────┤        │
                                  OCR, metadata, chunks, embeddings     retrieval              │        ▼
                                                                         Google Gemini ◄───────┘   app/frontend_hephaistos
                                                                                                   (HTML, CSS, JS, Chart.js)
```

One server (`python -m src.api`) serves the page and the API:

| Route | Role |
|---|---|
| `GET /` | the HEPHAISTOS interface |
| `POST /api/predict` | prediction for a fuel state and conditions |
| `GET /api/dataset/summary` | figures and series of the Data study page |
| `GET /api/models/status` | status of the models, the RAG and Gemini |
| `POST /api/ask` | chat: retrieval + Gemini answer + sources |
| `GET /api/rag/health`, `POST /api/rag/retrieve` | RAG server routes |

Details: [`src/api/README.md`](src/api/README.md).

## Data

- **Source:** NASA [Physical Sciences Informatics (PSI)](https://psi.nasa.gov/) test tables for FLEX, CFI, ACME CFI-G, ACME Flame Design, SPICE, BASS, BASS-II and Saffire. Each file and its link are listed in [`data/SOURCES.md`](data/SOURCES.md).
- **Pipeline:** `python -m src.data.download_psi` downloads the raw files, then `python -m src.data.build_unified` builds `data/processed/unified.parquet` and one modelling table per family (`droplets`, `gas`, `solids`, `aerosols`).
- **Rules:**
  - no invented value: a missing measurement stays empty, and every interpreted value is flagged in the `qc_flags` column ([`docs/regles_valeurs_manquantes.md`](docs/regles_valeurs_manquantes.md));
  - normal-gravity (1g) and microgravity tests are never mixed;
  - columns are described in [`data/processed/data_dictionary.md`](data/processed/data_dictionary.md), quality checks in [`data/processed/qc_report.md`](data/processed/qc_report.md), and the data study in [`docs/etude_donnees.md`](docs/etude_donnees.md).

## Models

The app uses **Gaussian processes** (`src/models/model_gp`), one per fuel family. They give a probability with an interval, and they say when the conditions are far from any NASA test.

Every model is validated **on test days never seen in training** (all the tests of a day are held out together), and compared with a naive baseline. The scores are reported as they are, including when they are weak; the app shows them as a reliability badge.

| Family (experiment) | Prediction | Validation | Reliability shown |
|---|---|---|---|
| Droplets (FLEX, 261 tests) | flame goes out on its own; burning rate K | AUC 0.91; K: R² 0.68, 95% interval covers 95% of tests | good |
| Gases (ACME CFI-G) | self-extinction; ignition | AUC 0.76; AUC 0.66 | medium; low |
| Solids (BASS, BASS-II) | flame sustained | AUC 0.59 | low: indication only |

Three other approaches were built and compared on the same folds (random forests, CatBoost, a thermo-physical gradient boosting model): see [`src/models/comparaison.md`](src/models/comparaison.md) and [`src/models/README.md`](src/models/README.md). Each model folder has its own `validation.md`.

## Chat (RAG)

1. **Corpus:** NASA documents from NTRS and PSI (`python -m src.rag.ingestion.fetch_ntrs`), with personal contact details removed.
2. **Ingestion**, fully local, in three resumable stages: OCR of the PDFs with Marker, missing metadata (title, authors, year, mission) completed by Phi-3.5-mini, then chunks of 1,000 characters (200 overlap) keeping the section path, embedded with Qwen3-Embedding through LM Studio and stored in ChromaDB.
3. **Answer:** the question is embedded, the 5 closest passages (and their neighbours) are retrieved, and Gemini writes an answer citing them as [1], [2]… If nothing relevant is found, it says so instead of guessing.

The database (`data/rag/chroma_db/`) is not stored in Git. It is published as a GitHub release (`chroma-db-v*`, `.tar.gz` archive with a SHA-256 manifest):

```bash
python -m src.rag.storage.download_chroma_release              # download and install the latest release
python -m src.rag.storage.download_chroma_release --check-only # check for an update
python -m src.rag.storage.publish_chroma_release               # publish a new release after re-indexing
python -m src.rag.server --port 8001                           # run the RAG server on its own
```

Details: [`src/rag/README.md`](src/rag/README.md) and [`src/rag/server/API.md`](src/rag/server/API.md).

## Tests

```bash
pytest src/api/tests src/rag/tests
```

## Repository layout

```
app/frontend_hephaistos/   interface (single HTML page, Chart.js)
src/data/                  download and cleaning of the NASA test tables
src/models/                prediction models and their validation reports
src/rag/                   chat corpus: ingestion, ChromaDB storage, retrieval server
src/api/                   FastAPI server, prediction, Data study, chat, packaging
data/                      sources, processed tables (raw files are not versioned)
docs/                      data study, missing-value rules, interface guide
eval/                      evaluation questions for the chat
```

## Limits and future work

- **Gaps in NASA data:** no droplet test below 70 kPa (a lunar habitat at 55 kPa is an extrapolation); solids tested at 22.7% O₂ at most in microgravity, while exploration atmospheres target about 34%. The app flags these cases instead of hiding them.
- **Solid-fuel model:** too few tests for a reliable prediction (AUC 0.59); it is shown as an indication only.
- **More data:** BRE test conditions exist only on scanned handwritten sheets (manual transcription needed), and PSI only has the FLEX-2 design matrix, not the tests actually run.
- **Interactive Data study:** cross-filtering like a BI tool (filter by family, click an experiment, O₂ range).
- **Online hosting:** the app runs locally; hosting it (Railway, Render) would require computing the embeddings inside the server instead of LM Studio.

## Use of AI tools

As required by the NASA Space Apps Challenge rules, here is where and how AI tools were used.

**Code and documentation.** Part of the code (data extraction scripts, models, API, interface) and of the documentation was written with the help of an AI coding assistant (Claude, Anthropic). The team set the goals and rules (no invented data, validation on unseen test days, uncertainty always shown), reviewed the code, and checked it with automated tests and validation reports (`src/models/*/validation.md`, `src/models/comparaison.md`).

**Data.** All test values come from NASA files (PSI, NTRS); none is generated by AI. Every interpreted value is flagged in the `qc_flags` column. In the chat index, missing document metadata (title, authors, year, mission) was completed by a local language model (Phi-3.5-mini) and may contain approximations.

**In the app.** Chat answers are written by an AI model (Google Gemini), only from passages of NASA documents found by semantic search (Qwen3-Embedding embeddings), and cite their sources. The interface says so below the chat input.

**NASA brand.** The project uses no NASA logo or graphic element; experiment names (FLEX, ACME, BASS…) are only used to cite the data sources.

## Team

Team Proteus — NASA Space Apps Challenge 2026, Paris.
