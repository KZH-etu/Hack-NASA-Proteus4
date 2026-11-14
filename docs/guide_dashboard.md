# Guide du dashboard

Tout ce qu'il faut pour construire `app/streamlit_app.py` à partir de ce qui existe dans le dépôt : données, modèles, RAG, contenu de chaque onglet, code de départ et pièges connus. Les noms de fonctions, de colonnes et de clés ci-dessous ont été vérifiés sur `main`.

## 1. Ce que le dashboard doit montrer

Objectif du challenge : un dashboard qui **résume, classe et explique** des décennies d'essais NASA de combustion en microgravité, pour la sécurité incendie des missions Lune et Mars.

Quatre onglets (déjà créés, vides, dans `app/streamlit_app.py`) :

| Onglet | Rôle | Source |
|---|---|---|
| **Explorer** | parcourir les 1 720 essais : filtres, table, graphiques, lien vers la source NASA de chaque essai | `data/processed/experiments_all.csv` |
| **Carte des trous** | où la NASA a testé, où elle n'a pas testé ; le scénario de mission en marqueur ; zones où le modèle est incertain | tables par famille + modèles |
| **Prochaine expérience** | un scénario de mission → prédiction avec **incertitude** + expériences ISS recommandées, chacune expliquée | `model_gp` (+ `model_rf` en second avis) |
| **Assistant** | questions en langage naturel, réponses qui **citent leurs sources** | RAG (`src/rag`), voir § 6 |

Histoire de la démo (fil rouge) : *« Un ingénieur conçoit un habitat lunaire à atmosphère enrichie en O2 (34 %, 55 kPa). Que sait-on ? Que prédit le modèle, avec quelle confiance ? Quelle expérience faire sur l'ISS pour le savoir ? »*

## 2. Lancer le projet

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (source .venv/bin/activate sur Linux / macOS)
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

- `marker-pdf` (dans `requirements.txt`) télécharge PyTorch (plusieurs Go). Il ne sert qu'à l'OCR du RAG. Pour le dashboard seul, on peut l'enlever de la commande : `pip install pandas pyarrow scikit-learn catboost streamlit plotly ...`.
- Machine avec peu de mémoire libre : si un message `OpenBLAS error: Memory allocation still failed` apparaît, lancer avec `OPENBLAS_NUM_THREADS=1` (Windows PowerShell : `$env:OPENBLAS_NUM_THREADS=1`).
- Travailler sur la branche `dashboard`, puis ouvrir une PR vers `main`.

**Important : chemin d'import.** `streamlit run app/streamlit_app.py` met `app/` en tête du chemin Python, pas la racine du dépôt. `import src...` échoue sans ces deux lignes en haut de l'app :

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # racine du dépôt
```

## 3. Règles d'affichage (à respecter partout)

1. **Jamais de donnée inventée.** Une case vide reste vide (afficher « — » ou « non mesuré »). Ne pas remplir avec une valeur par défaut.
2. **Toujours montrer l'incertitude** : un intervalle à côté de chaque probabilité (barre d'erreur, fourchette « 0,41 [0,06 – 0,64] »).
3. **Afficher les `warnings` des modèles tels quels** (`st.warning`) : extrapolation, pas de donnée proche, fiabilité faible. C'est ce qui rend le dashboard crédible pour un jury NASA.
4. **Citer la source de chaque essai** : colonnes `psi_url` / `doi_url` de `experiments_all.csv`, ou `psi_id` + `source_file` + `source_line` dans les tables par famille.
5. **Ne pas mélanger 1g et microgravité** (colonne `gravity` : `micro` ou `1g` ; 9 essais en 1g, tous des solides). Filtrer sur `micro` par défaut.
6. **Montrer les `qc_flags`** quand on affiche un essai : format `colonne:motif;colonne:motif` (ex. `pressure_kpa:nominal`). Motifs : `sans_objet`, `doc`, `nominal`, `recopie`, `zero_fictif`, `incoherent`, `a_verifier`, `approx`, `rampe`, `sans_allumage_chaud`, `qualitatif`, `erreur_excel`, `deduit`. Détails : `docs/regles_valeurs_manquantes.md`.

## 4. Données

Toutes les données sont dans le dépôt, il n'y a rien à télécharger.

### 4.1 Catalogue des essais (onglet Explorer)

`data/processed/experiments_all.csv` : 1 720 essais, une ligne par essai, 20 colonnes (aussi en Parquet, sans les deux URL : `data/processed/unified.parquet`, via `src.data.build_unified.load_unified_table()`).

| Colonne | Contenu |
|---|---|
| `experiment` | SPICE 435, ACME CFI-G 333, ACME Flame Design 327, FLEX 274, BASS-II 129, BASS 121, CFI 79, Saffire-II 18, Saffire-I 2, Saffire-III 2 |
| `psi_id`, `doi`, `test_id` | identifiants ; `psi_url`, `doi_url` : liens cliquables vers la source |
| `fuel_type` | `gas` (1 095), `droplet` (353), `solid` (272) |
| `material`, `geometry` | combustible ou matériau (heptane, methanol, propane, pmma, nomex…), géométrie de l'échantillon |
| `o2_percent` | **% d'O2** (21 = air) |
| `pressure_kpa`, `flow_cm_s` | pression (101,3 = 1 atm), vitesse d'air |
| `gravity` | `micro` (1 711) ou `1g` (9) |
| `outcome` | `extinguished` 460, `burned` 111, `no_ignition` 63, `disruption` 61 (gouttelette qui éclate), `completion` 27 (brûle jusqu'au bout), `other` 9, vide 989 (essais sans issue mesurée : SPICE, Flame Design…) |
| `spread_rate_mm_s`, `burning_rate` | vitesse de propagation (solides), constante de combustion K (gouttelettes, mm²/s) |
| `source_doc`, `source_page`, `notes`, `qc_flags` | provenance et contrôle qualité |

Les campagnes sont décrites dans `data/processed/campaigns.csv` (12 lignes : `psi_id`, `experiment`, `family`, `title`, `doi`, `license`, `platform`, `hardware`, `start`, `end`, `n_rows`…), ce qui permet un encart « À propos des données ». Le dictionnaire complet des colonnes est dans `data/processed/data_dictionary.md`.

### 4.2 Tables par famille (Carte des trous, détails)

`from src.data.build_unified import load_family` puis `load_family("droplets" | "gas" | "solids" | "aerosols")`. Ces tables ont plus de colonnes (27 à 47), mais **l'O2 y est une fraction** (`x_o2` : 0,21 = air).

| Famille | Lignes | Colonnes utiles pour les cartes |
|---|---:|---|
| `droplets` | 353 | `experiment`, `fuel`, `x_o2`, `pressure_kpa`, `x_co2`, `x_he`, `d0_mm`, `burning_rate_mm2_s`, `outcome`, `session` |
| `gas` | 1 095 | `experiment`, `fuel`, `flame_type` (normal / inverse), `x_o2`, `pressure_kpa`, `x_fuel`, `hc_rate_mg_s`, `outcome` |
| `solids` | 272 | `experiment`, `material`, `geometry`, `x_o2`, `flow_cm_s`, `flow_min_cm_s`, `flow_max_cm_s`, `extinction_flow_cm_s`, `extinction_mode`, `outcome`, `gravity` |
| `aerosols` | 129 | `experiment`, `material`, `flow_cm_s`, `rt_r0`, `weight_loss_mg_min` (pas d'issue de combustion) |

Plages testées (utile pour les curseurs et pour signaler l'extrapolation) :
- gouttelettes FLEX : O2 de 12 à 34 %, pression de 70 à 309 kPa (**rien sous 70 kPa**) ;
- gaz ACME CFI-G : O2 de 13,5 à 85 %, pression de 49,5 à 331 kPa ;
- solides BASS-II : O2 de 14,5 à 22,2 % (**rien au-dessus de 22,7 %**), pression d'environ 1 atm.

## 5. Modèles

### 5.1 Lequel utiliser

D'après `src/models/comparaison.md` (les 4 modèles réentraînés sur les mêmes plis par jour d'essai) :

- **`model_gp` : modèle principal du dashboard.** Il est le meilleur sur les gouttelettes, sur K et sur les gaz. Il est le seul en accord avec les essais réels pour l'air de l'ISS (0,41 prédit pour 0,45 observé), il donne des intervalles et des alertes, et il fournit `recommend_next_experiment`.
- **`model_rf` : second avis, et mode « essais réels »** pour les solides et les aérosols (il renvoie les essais NASA les plus proches au lieu d'une prédiction).
- `model_catboost` et `model_thermo` : à ne pas brancher dans le dashboard (voir la comparaison).

### 5.2 Chargement et cache (obligatoire)

Le **premier appel** de chaque modèle de `model_gp` entraîne des ensembles bootstrap : environ **30 s par famille** (22 à 32 s mesurés), soit environ 1 min 30 au total. Les appels suivants prennent environ 0,03 s. Il faut donc charger une seule fois avec `st.cache_resource` :

```python
import streamlit as st
from src.models import load

@st.cache_resource(show_spinner="Entraînement des modèles (environ 1 min 30 au premier lancement)…")
def get_gp():
    gp = load("model_gp")
    gp.flex.trained_model(); gp.solids.trained_model(); gp.gas.trained_model()  # entraîne une fois
    return gp

@st.cache_resource(show_spinner="Chargement du second modèle…")
def get_rf():
    from src.models.model_rf.service import MLService
    return MLService.load_or_train()   # environ 0,2 s (sauvegardé dans model_rf/artifacts/)

@st.cache_data
def get_catalogue():
    import pandas as pd
    return pd.read_csv("data/processed/experiments_all.csv")
```

### 5.3 `model_gp` : prédire

Les entrées utilisent **`o2_percent` en %** et `pressure_kpa` en kPa.

```python
gp = get_gp()

r = gp.flex.predict({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0,
                     "co2_percent": 0, "he_percent": 0})          # fuel : "heptane" | "methanol"
# {'experiment': 'FLEX',
#  'p_extinction': 0.022, 'p_extinction_interval_90': (0.008, 0.307),
#  'burning_rate_k_mm2_s': 0.764, 'burning_rate_k_std': 0.07,
#  'nearest_data_distance': 0.46, 'near_data': True, 'n_training_tests': 261,
#  'warnings': ["pressure_kpa = 55 hors de la plage mesurée par FLEX (70.17 à 309.29) : extrapolation ; ..."]}

r = gp.solids.predict({"material": "pmma_flat", "o2_percent": 21, "flow_cm_s": 10})
# material : "pmma_flat" | "pmma_rod_sphere" | "fabric_other"
# {'experiment': 'BASS / BASS-II', 'material_group': 'pmma_flat',
#  'p_flame_sustained': 0.813, 'p_flame_sustained_interval_90': (0.493, 0.946),
#  'reliable': False, 'n_observations_same_group': 99, 'warnings': ['fiabilité du modèle faible ...']}
# Au-dessus de 22,2 % d'O2 : p_flame_sustained = None (pas de donnée) -> afficher « pas de donnée », pas 0,5.

r = gp.gas.predict({"fuel": "propane", "o2_percent": 34, "pressure_kpa": 55, "x_fuel": 0.3, "hc_rate_mg_s": 1.0})
# fuel : "ethane" | "propane" | "n-butane" ; flammes normales seulement
# {'experiment': 'ACME CFI-G (flammes normales)', 'fuel': 'propane',
#  'p_hot_ignition': 0.977, 'p_hot_ignition_interval_90': (0.519, 0.981), 'p_hot_ignition_reliability': 'faible : ...',
#  'p_self_extinction_if_ignited': 0.569, 'p_self_extinction_interval_90': (0.484, 0.874),
#  'p_self_extinction_reliability': 'moyenne : ...',
#  'nearest_tests': [{'test_id': '21153A5', 'fuel': 'ethane', 'o2_percent': 33.2, 'pressure_kpa': 50.7,
#                     'x_fuel': 0.3, 'hc_rate_mg_s': 0.75, 'outcome': 'burned', 'distance': 0.76}, ...],
#  'n_training_tests': 177, 'warnings': []}
```

Fiabilité à annoncer dans l'UI (validation par jour d'essai) : FLEX **bonne** (AUC 0,91) ; gaz, auto-extinction **moyenne** (0,76) ; gaz, allumage **faible** (0,66) ; solides **faible** (0,59, à ne pas utiliser pour décider). Détails : `src/models/model_gp/<famille>/validation.md`.

### 5.4 `model_gp` : recommander la prochaine expérience

```python
rec = gp.recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0}, n=5)
# Solides : gp.recommend_next_experiment({"material": "pmma_flat", "o2_percent": 34, "flow_cm_s": 10}, n=5)
```

Environ 0,1 s une fois le modèle en cache. Structure renvoyée :

| Clé | Contenu |
|---|---|
| `scenario` | le scénario reçu |
| `scenario_prediction` | la sortie de `predict` pour le scénario (voir § 5.3) |
| `nearest_flex_tests` (solides : `nearest_observations`) | essais réels les plus proches : `test_id`, conditions, `outcome`, `distance` |
| `recommendations` | liste triée : `rank`, `conditions` (dict prêt à afficher), `score`, `relevance`, `uncertainty`, `novelty`, `p_extinction` + `p_extinction_interval_90` (solides : `p_flame_sustained`…), `nearest_flex_test`, **`why`** (phrase d'explication) |
| `method` | une phrase sur la méthode (score = pertinence × (incertitude + nouveauté)) |

Exemple de `why` : *« aucun essai FLEX sous 70 kPa ; essai réel le plus proche loin (n° 39 : 34.0 % O2, 71.3 kPa, issue disruption) ; modèle incertain (intervalle de probabilité d'extinction large de 0.31) »*. C'est à afficher tel quel, c'est l'argument de la démo.

### 5.5 `model_rf` : second avis et essais réels

```python
rf = get_rf()
rf.catalogue()      # [{'famille': 'Gouttelettes (FLEX)', 'mode': 'prediction', 'description': ...},
                    #  {'famille': 'Gaz (ACME CFI-G)', 'mode': 'prediction', ...},
                    #  {'famille': 'Solides (BASS-II, Saffire)', 'mode': 'donnees', ...},
                    #  {'famille': 'Aérosols / fumées (SAME, SAME-R)', 'mode': 'donnees', ...}]
rf.parameters("Gaz (ACME CFI-G)")   # {'x_o2': {'type': 'nombre', 'min': 0.12, 'max': 0.85, 'defaut': 0.386}, ...}
                                     # -> de quoi générer les curseurs automatiquement
r = rf.ask("Gouttelettes (FLEX)", {"fuel": "heptane", "x_o2": 0.34, "pressure_kpa": 55,
                                   "x_co2": 0.0, "x_he": 0.0, "d0_mm": 3.0})   # O2 en FRACTION ici
# r['resultats']['issue'] = {'issue_probable': 'disruption', 'probabilite': 0.819, 'incertitude': 0.34,
#                            'toutes_les_issues': {'completion': 0.059, 'disruption': 0.819, 'extinguished': 0.122}}
# r['resultats']['vitesse_combustion_mm2_s'] = {'valeur': 0.763, 'incertitude': 0.093, 'intervalle_95': (0.58, 0.95)}
# r['essais_proches'] : DataFrame des essais réels proches (test_id, session, psi_id, source_file, source_line, ...)
# r['hors_plage'], r['avertissement'] : à afficher
r = rf.ask("Solides (BASS-II, Saffire)", {"material": "pmma", "x_o2": 0.21})   # mode « donnees »
# -> pas de prédiction : r['essais_proches'] (DataFrame : material, geometry, x_o2, flow_max_cm_s, outcome,
#    extinction_mode, extinction_flow_cm_s, ...) + r['avertissement']
```

## 6. Assistant (RAG)

État actuel :
- **Corpus prêt** dans le dépôt : `data/raw/ntrs/catalog.csv` (399 documents : `id`, `title`, `authors`, `year`, `url`, `pdf_url`, `topics`, `source`…) et `data/raw/ntrs/pages/<id>.jsonl` (390 fichiers, une ligne par page : `{"page": 1, "label": null, "text": "..."}`).
- **Ingestion en cours** (Louis, `src/rag/README.md`) : OCR → métadonnées → ChromaDB, avec un LLM et des embeddings servis en local par LM Studio (`http://localhost:1234/v1`).
- **Pas encore de fonction de question / réponse.**

Contrat proposé pour brancher l'onglet dès maintenant (à fournir par le RAG) :

```python
def ask(question: str, k: int = 5) -> dict:
    """{'answer': str,
        'sources': [{'title': str, 'year': int, 'url': str, 'page': int, 'excerpt': str}, ...]}"""
```

En attendant, l'onglet peut fonctionner avec une recherche plein texte simple sur `pages/*.jsonl` (affichage des extraits et des liens, sans réponse générée). Il suffira de remplacer cette fonction par celle du RAG.

```python
import json
from pathlib import Path
import pandas as pd

@st.cache_data
def load_pages():
    cat = pd.read_csv("data/raw/ntrs/catalog.csv").set_index("id")
    rows = []
    for f in Path("data/raw/ntrs/pages").glob("*.jsonl"):
        doc = f.stem
        for line in f.open(encoding="utf-8"):
            p = json.loads(line)
            rows.append({"id": doc, "page": p["page"], "text": p["text"]})
    pages = pd.DataFrame(rows)
    pages["id"] = pages["id"].astype(cat.index.dtype)  # les identifiants du catalogue peuvent être des nombres
    return pages.join(cat[["title", "year", "url"]], on="id")

def search(question, k=5):
    words = [w for w in question.lower().split() if len(w) > 3]
    pages = load_pages()
    score = sum(pages["text"].str.lower().str.count(w) for w in words)
    return pages.assign(score=score).nlargest(k, "score")
```

Sur Streamlit Community Cloud, LM Studio n'est pas disponible : prévoir que l'Assistant affiche les sources seules si le LLM ne répond pas.

## 7. Onglet par onglet

### 7.1 Explorer

- **Barre latérale** : multiselect `experiment`, `fuel_type`, `material`, `outcome` ; curseurs `o2_percent` (0–100) et `pressure_kpa` ; case « microgravité seulement » (cochée par défaut).
- **Indicateurs** (`st.metric`) : nombre d'essais, nombre de campagnes, part d'extinctions parmi les essais avec issue.
- **Table** : `st.dataframe(df, column_config={"psi_url": st.column_config.LinkColumn("Source PSI"), "doi_url": st.column_config.LinkColumn("DOI")})`.
- **Graphiques** (plotly) : histogramme `o2_percent` coloré par `outcome` ; nuage `o2_percent` × `pressure_kpa` coloré par `experiment` ; barres « essais par campagne ».

### 7.2 Carte des trous

Pour chaque famille, un nuage des conditions testées avec le scénario en étoile. En option, un fond de couleur donne la **largeur de l'intervalle** du modèle (grand = on ne sait pas) : c'est la vraie « carte des trous ».

| Famille | Axe x | Axe y | Couleur des points |
|---|---|---|---|
| Gouttelettes | `x_o2` × 100 (%) | `pressure_kpa` | `outcome` |
| Gaz | `x_o2` × 100 | `pressure_kpa` | `outcome` |
| Solides | `x_o2` × 100 | `flow_cm_s` (échelle log) | `outcome` |

Fond d'incertitude pour FLEX (900 points en environ 0,3 s, modèle en cache) :

```python
import numpy as np
import plotly.graph_objects as go
from src.data.build_unified import load_family

m = get_gp().flex.trained_model()
o2 = np.linspace(0.12, 0.40, 40); p = np.linspace(40, 310, 40)
O2, P = np.meshgrid(o2, p)
# colonnes de flex.FEATURES : is_heptane, x_o2, pressure_kpa, x_co2, x_he, d0_mm
X = np.column_stack([np.ones(O2.size), O2.ravel(), P.ravel(), np.zeros(O2.size), np.zeros(O2.size), np.full(O2.size, 3.0)])
f = m.predict_frame(X)                       # p_extinction, p_low, p_high, k_mm2_s, k_std, nn_distance, near_data
width = (f["p_high"] - f["p_low"]).to_numpy().reshape(O2.shape)

d = load_family("droplets"); d = d[d["experiment"] == "FLEX"]
fig = go.Figure(go.Heatmap(x=o2 * 100, y=p, z=width, colorscale="Oranges", colorbar=dict(title="incertitude")))
fig.add_scatter(x=d["x_o2"].astype(float) * 100, y=d["pressure_kpa"].astype(float), mode="markers",
                marker=dict(size=5, color="black"), name="essais FLEX")
fig.add_scatter(x=[34], y=[55], mode="markers", marker=dict(symbol="star", size=18, color="red"), name="scénario")
fig.update_layout(xaxis_title="O2 (%)", yaxis_title="Pression (kPa)")
st.plotly_chart(fig, use_container_width=True)
```

Attention : `trained_model().predict_frame` ne masque pas les zones sans données (contrairement à `predict`). Pour les solides, au-dessus de 22,2 % d'O2, le modèle revient à 0,5 : griser ces zones au lieu d'afficher une probabilité. Colonnes de `solids.FEATURES` : `is_pmma_flat`, `is_pmma_rod_sphere`, `is_fabric_other`, `x_o2`, `log_flow` (= ln du débit en cm/s). Colonnes de `gas.FEATURES` : `is_ethane`, `is_propane`, `is_n_butane`, `x_o2`, `pressure_kpa`, `x_fuel`, `hc_rate_mg_s`.

### 7.3 Prochaine expérience

1. **Choix du scénario** : boutons de préréglage (§ 8) + curseurs (famille, combustible ou matériau, O2, pression, débit, diamètre).
2. **Carte de prédiction** : grande valeur avec fourchette (« Probabilité d'extinction : 0,02 [0,01 – 0,31] »), K avec ± écart-type, badge de fiabilité, `st.warning` pour chaque alerte, essais réels les plus proches (avec lien source).
3. **Second avis** (repliable) : `model_rf` sur le même scénario ; signaler quand les deux modèles divergent.
4. **Recommandations** : table `rank`, conditions, `score`, `p_extinction` [intervalle], et la phrase `why` ; les recommandations en étoiles sur la carte des trous.

### 7.4 Assistant

`st.chat_input`, historique dans `st.session_state`, réponse puis **sources cliquables** (titre, année, page, lien `url`). Questions de démo : « Pourquoi une flamme s'éteint-elle plus facilement en microgravité ? », « Qu'a montré FLEX sur l'extinction radiative ? », « Quels matériaux brûlent à 34 % d'O2 ? ».

## 8. Scénarios de démo (préréglages)

| Scénario | Entrées |
|---|---|
| Cabine ISS | gouttelette d'heptane, 21 % O2, 101,3 kPa, 3 mm |
| Habitat lunaire enrichi en O2 | 34 % O2, 55 kPa (gouttelette d'heptane 3 mm ; PMMA à 10 cm/s pour les solides) |
| Atmosphère appauvrie en O2 | 15 % O2, 101,3 kPa |

Valeur ajoutée à montrer sur le scénario lunaire : aucun essai FLEX sous 70 kPa, les modèles divergent (de 0,02 à 0,14), le modèle le dit (alerte d'extrapolation), et `recommend_next_experiment` propose justement d'aller tester cette zone.

## 9. Pièges connus

| Piège | Solution |
|---|---|
| `ModuleNotFoundError: src` | `sys.path.insert(...)` en haut de l'app (§ 2) |
| Démarrage d'environ 1 min 30 | `st.cache_resource` + spinner (§ 5.2) ; ne jamais réentraîner dans un callback |
| O2 en % ou en fraction | `o2_percent` (catalogue, `model_gp`) contre `x_o2` (tables par famille, `model_rf`) |
| Solides au-dessus de 22,2 % d'O2 | `p_flame_sustained` vaut `None` : afficher « pas de donnée » |
| Intervalle « 0,5 – 0,5 » sur une carte | zone sans données : la griser |
| `OpenBLAS error: Memory allocation` | `OPENBLAS_NUM_THREADS=1` |
| Assistant sans LLM (cloud) | n'afficher que les sources (§ 6) |
| Valeurs manquantes | afficher « — », ne pas remplir |

## 10. Checklist « prêt pour la démo »

- [ ] L'app démarre depuis un clone propre (`pip install` + `streamlit run`), modèles en cache.
- [ ] Explorer : filtres, table avec liens PSI / DOI, 2 graphiques.
- [ ] Carte des trous : 3 familles, scénario en étoile, zones sans données visibles.
- [ ] Prochaine expérience : préréglages, prédiction avec intervalle et alertes, recommandations avec `why`.
- [ ] Assistant : question, réponse ou extraits, sources cliquables.
- [ ] Aucune valeur inventée affichée ; fiabilité annoncée pour chaque modèle.
