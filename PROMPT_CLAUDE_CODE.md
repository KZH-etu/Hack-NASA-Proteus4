# Prompt pour Claude Code — NASA Space Apps 2026 « Flame in Freefall »

> Avant de coller : remplacez les `[CROCHETS]` (noms de l'équipe, pseudos GitHub, nom du dépôt, fournisseur LLM).

---

## CONTEXTE

Nous sommes une équipe de [N] personnes au NASA Space Apps Challenge 2026 (Paris, 14–15 novembre). La soumission ferme **dimanche 15 novembre à 23 h 59** (heure de Paris) ; nous visons une soumission vers 22 h. Il nous faut une démo en ligne et une vidéo.

**Challenge : « Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data ».**
Objectif officiel : un dashboard propulsé par l'IA qui **résume, classe et explique** des décennies de résultats NASA sur la combustion en microgravité, pour éclairer la sécurité incendie des missions Lune et Mars.

**Notre angle différenciant :** « Quelle expérience faire ensuite ? »
Le dashboard (1) cartographie les conditions déjà testées en microgravité (matériau × % O2 × pression × débit d'air), (2) prédit le comportement de la flamme avec une **incertitude**, (3) recommande la prochaine expérience ISS qui réduirait le plus l'incertitude pour un scénario de mission donné (ex. habitat lunaire à atmosphère enrichie en O2), et (4) explique tout cela via un **RAG qui cite ses sources** (articles NASA).

## RÈGLES NON NÉGOCIABLES

1. **Jamais de données inventées.** Aucune ligne générée par formule ou par LLM ne doit être présentée comme une donnée NASA. Chaque ligne de données porte sa source (`source_id` PSI, DOI, document NTRS + page). Si une valeur manque, elle reste vide.
2. **Ne jamais mélanger 1g et microgravité** dans un même entraînement : le 1g est une couche de comparaison.
3. **Toujours afficher l'incertitude** et dire « pas de donnée proche » quand c'est le cas.
4. **Le RAG cite toujours** (titre, expérience, page) et répond « je ne sais pas » si rien de pertinent n'est trouvé.
5. Code simple et lisible : on a 36 heures. Une fonctionnalité qui marche vaut mieux que trois à moitié finies.
6. Les secrets (clés API) vont dans `.env`, jamais dans Git.

## SOURCES DE DONNÉES

**NASA PSI (Physical Sciences Informatics)** — https://psi.nasa.gov/physci/repo — licence CC0, sans compte. Commencer par le dossier « Experimental table » de chaque investigation.

| Expérience | PSI | DOI | Contenu |
|---|---|---|---|
| BASS | PSI-26 | 10.60555/58h4-dy80 | Matrice d'essais réalisés |
| BASS-II | PSI-25 | 10.60555/4qc4-de67 | Essais solides : matériau, débit, O2/CO2/CO. **Pas de vitesse de propagation** (→ rapport NASA/TM-20210011385, annexe A) |
| FLEX | PSI-69 | 10.60555/mbq8-0451 | ~274 essais gouttelettes, issue (extinction / disruption / completion) |
| Saffire I/II/III | PSI-98/99/100 | 10.60555/0t15-1z43, /2chp-m469, /040q-4h36 | Grands feux dans Cygnus, comparaison 1g |
| ACME Flame Design | PSI-10 | 10.60555/w4zy-bt45 | Tableaux d'essais flammes gazeuses |
| ACME s-Flame | PSI-23 | 10.60555/k57n-p030 | Flammes sphériques |
| ACME CFI-G | PSI-159 | — | Flammes froides gazeuses |
| SAME / SAME-R | PSI-101/102 | — | Fumées, détecteurs |

À vérifier sur PSI avant usage (identifiants relevés dans des dépôts d'autres équipes). Pièges connus : ~2 600 anciens fichiers en 404 (surtout FLEX-2) ; SoFIE et MIST absents de PSI ; aucune donnée en gravité partielle dans PSI.

**NASA NTRS (articles, pour le RAG)** — API : `https://ntrs.nasa.gov/api/citations/search?q=...` (doc : https://ntrs.nasa.gov/api/openapi/). Documents prioritaires :
- NASA/TP-2015-216046 — Detailed Results From FLEX (NTRS 20150023456)
- NASA/TM-20210011385 — BASS-II (vitesses de propagation, annexe A)
- NTRS 20160000593 — Combustion of Solids in Microgravity, BASS-II
- NTRS 20220015583 — ACME overview ; NTRS 20210021781 — article ACME JASMAC
- NASA/TP-2010-216134 — atmosphère d'exploration
- « A Researcher's Guide to: Combustion Science » (ISS Program Science Office)

## STACK

- Python 3.11+, gestion des dépendances avec `requirements.txt` (ou `uv` si tout le monde l'a)
- Données : pandas, fichiers Parquet/CSV dans `data/`
- ML : scikit-learn (GaussianProcessRegressor ou ensemble de modèles pour l'incertitude)
- RAG : LlamaIndex + ChromaDB, recherche hybride BM25 + embeddings fusionnée par Reciprocal Rank Fusion
- LLM : [FOURNISSEUR — Mistral / Anthropic / OpenAI], clé dans `.env` (`LLM_API_KEY`, `LLM_MODEL`)
- Dashboard : Streamlit, déployé sur Streamlit Community Cloud

## ARCHITECTURE DU DÉPÔT

```
flame-in-freefall/
├── README.md                 # pitch, démo, installation, sources
├── requirements.txt
├── .env.example
├── .gitignore                # .env, data/raw/, chroma/, __pycache__, .venv
├── data/
│   ├── raw/                  # fichiers NASA bruts (non versionnés si lourds)
│   ├── processed/            # tables propres versionnées (petites)
│   └── SOURCES.md            # chaque fichier : URL, DOI, date de téléchargement
├── src/
│   ├── data/                 # téléchargement PSI, nettoyage, table unifiée
│   ├── models/               # prédiction + incertitude + recommandation d'expérience
│   ├── rag/                  # ingestion NTRS, index hybride, réponses citées
│   └── common/schema.py      # schéma de la table unifiée (source de vérité partagée)
├── app/
│   └── streamlit_app.py      # pages : Explorer · Carte des trous · Prochaine expérience · Assistant
├── eval/
│   └── rag_questions.csv     # questions de référence + réponses attendues + sources
└── docs/                     # pitch, script vidéo, captures
```

**Schéma de la table unifiée (`src/common/schema.py`)** — à figer en premier, tout le monde s'y aligne :
`experiment, psi_id, doi, test_id, fuel_type (solid/droplet/gas), material, geometry, o2_percent, pressure_kpa, flow_cm_s, gravity (micro/1g), outcome (burned/extinguished/no_ignition/…), spread_rate_mm_s, burning_rate, source_doc, source_page, notes`

## CONVENTIONS DE TRAVAIL

- Une branche par tâche (ex. `rag`, `ml`, `dashboard`, `data`), Pull Request vers `main`, `main` doit toujours tourner.
- Commits courts et explicites. Pas de commit de `.env` ni de fichiers > 50 Mo.
- Chaque module expose des fonctions simples que l'app appelle (ex. `load_unified_table()`, `predict(conditions)`, `recommend_next_experiment(scenario)`, `ask(question)`).
- Le samedi à 19 h : intégration de bout en bout (version 1 en ligne). Dimanche 18 h : gel du code.
- Pas de labels ni d'issues GitHub : l'organisation se fait directement entre nous.
- Rien de ce qui est visible sur GitHub (commits, PR, README, commentaires du code) ne mentionne d'outil d'IA : pas de ligne `Co-Authored-By`, pas de « Generated with… ». Le dépôt doit refléter le travail de l'équipe.

---

## TÂCHE 1 (À FAIRE MAINTENANT) — INITIALISER LE DÉPÔT GITHUB

Fais exactement ceci, en me montrant chaque commande avant de l'exécuter :

1. Vérifie que `git` et `gh` sont installés et que `gh auth status` est OK (sinon, guide-moi pour `gh auth login`).
2. Crée le dépôt public `[NOM-DU-DEPOT]` (ex. `flame-in-freefall`) avec `gh repo create`, clone-le.
3. Crée l'arborescence ci-dessus avec des fichiers minimaux :
   - `README.md` : titre, une phrase de pitch, sections vides (Démo, Installation, Architecture, Sources, Équipe).
   - `.gitignore` Python + `.env`, `data/raw/`, `chroma/`, `.venv/`.
   - `.env.example` avec `LLM_API_KEY=`, `LLM_MODEL=`, `EMBEDDING_MODEL=`.
   - `requirements.txt` : pandas, pyarrow, requests, scikit-learn, streamlit, llama-index, llama-index-vector-stores-chroma, chromadb, rank-bm25, python-dotenv, plotly.
   - `src/common/schema.py` avec le schéma de la table unifiée (dataclass ou dict de colonnes typées).
   - `app/streamlit_app.py` : une page « Hello Flame in Freefall » avec 4 onglets vides.
   - `data/SOURCES.md` et `eval/rag_questions.csv` (en-têtes seulement : `question,expected_answer,expected_source`).
   - Un `__init__.py` dans chaque dossier de `src/`.
4. Premier commit sur `main`, push.
5. Ajoute les collaborateurs : `gh repo edit` / `gh api` pour inviter [PSEUDOS_GITHUB].
6. Vérifie en local : `python -m venv .venv`, installation des dépendances, `streamlit run app/streamlit_app.py` démarre.

Ne commence aucune autre tâche avant que je valide la tâche 1.

**État :** tâche 1 terminée (dépôt créé, collaborateurs invités, app vérifiée en local le samedi 14 novembre).

---

## ORGANISATION PROPOSÉE (indicative, à ajuster librement)

Rien de figé : chacun reste libre de changer de tâche, d'aider ailleurs ou de réorganiser selon l'avancement.

| Branche | Qui (proposition) | Contenu |
|---|---|---|
| `rag` | 2 personnes (dont moi) | Tâche 4 : récupération NTRS, index hybride, `ask()`, évaluation |
| `ml` | 1 personne | Tâche 3 : `predict()`, `recommend_next_experiment()` |
| `dashboard` | à définir | Tâche 5 : les 4 pages Streamlit |

La tâche data (2) et le pitch (6) restent à répartir selon les disponibilités.

**Travailler en parallèle sans attendre les données :**
- Le RAG ne dépend pas de la table unifiée (il travaille sur les PDF NTRS) : il peut démarrer tout de suite.
- Le ML peut écrire son code en se basant sur les colonnes de `src/common/schema.py` et le tester sur une petite table factice **dans un fichier de test uniquement** (jamais dans `data/` ni dans l'app). Une fois `unified.parquet` prêt, on ajuste : colonnes vraiment remplies, valeurs de `outcome`, hyperparamètres, métriques.
- Le dashboard avance avec des données « DEMO » clairement étiquetées, puis branche les vraies fonctions.
- Si quelqu'un a besoin de modifier le schéma (nouvelle colonne, nouvelle valeur), il prévient l'équipe et le change dans une petite PR dédiée, plutôt que chacun de son côté.

---

## TÂCHES PAR PERSONNE (réparties au sein de l'équipe, pas d'issues GitHub)

### Tâche 2 — Data engineer : [PRÉNOM]
- Télécharger les « Experimental table » PSI de BASS, BASS-II, FLEX, Saffire I–III (puis ACME si le temps le permet) dans `data/raw/`, documenter chaque fichier dans `data/SOURCES.md`.
- Écrire `src/data/build_unified.py` : nettoie et convertit chaque table vers le schéma unifié, garde la traçabilité.
- Récupérer les vitesses de propagation BASS-II depuis le rapport NASA/TM-20210011385 (annexe A), en notant la page.
- Livrable samedi 14 h : `data/processed/unified.parquet` + `load_unified_table()`.

### Tâche 3 — ML engineer : [PRÉNOM]
- `src/models/predict.py` : modèles « extinction oui/non » (FLEX, BASS) et « vitesse de propagation » (BASS-II), avec incertitude (GaussianProcess ou ensemble + intervalle).
- Validation honnête : découpage par expérience/campagne, pas de fuite de données ; afficher les métriques réelles, même modestes.
- `src/models/recommend.py` : pour un scénario (ex. O2 34 %, pression réduite, débit faible), lister les conditions candidates et classer celles qui réduisent le plus l'incertitude (variance prédictive maximale près du scénario).
- Livrable samedi 19 h : `predict(conditions)` et `recommend_next_experiment(scenario)`.

### Tâche 4 — RAG engineer : [PRÉNOM]
- `src/rag/fetch_ntrs.py` : récupérer via l'API NTRS 50 à 100 documents ciblés (BASS, Saffire, FLEX, ACME, SAME, fire safety), télécharger les PDF, garder métadonnées (titre, id NTRS, année).
- `src/rag/index.py` : découpage, embeddings, ChromaDB + BM25, fusion RRF ; option reranking si le temps le permet.
- `src/rag/ask.py` : `ask(question)` → réponse + liste de sources (titre, id, page) ; seuil de pertinence → « je ne sais pas ».
- `eval/` : 20 questions de référence, script qui mesure pertinence, exactitude des sources et latence, et compare vectoriel vs hybride.
- Livrable samedi 19 h : `ask()` utilisable par l'app.

### Tâche 5 — Frontend / dashboard : [PRÉNOM]
- Pages Streamlit : **Explorer** (filtres expérience/matériau/O2/gravité + table + graphiques), **Carte des trous** (nuage O2 × débit, scénario en marqueur, zones sans données), **Prochaine expérience** (curseurs du scénario → prédiction avec incertitude + recommandation), **Assistant** (chat RAG avec sources cliquables).
- Utiliser d'abord des données factices **clairement étiquetées « DEMO »** tant que les modules ne sont pas prêts, puis brancher les vraies fonctions.
- Déployer sur Streamlit Community Cloud dès samedi soir.

### Tâche 6 — Chef de projet / pitch : [PRÉNOM]
- Page projet Space Apps (onglet Project de l'équipe), README final, `docs/pitch.md`.
- Scénario de démo : « Un ingénieur conçoit un habitat lunaire à atmosphère enrichie en O2… »
- Script et tournage de la vidéo démo, captures d'écran, tests de chaque page.
- Surveille l'horloge : coupe toute fonctionnalité non prête à dimanche 18 h.
