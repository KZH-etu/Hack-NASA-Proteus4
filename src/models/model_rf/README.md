# model_rf — Forêt aléatoire avec incertitude

Un modèle par famille d'expériences. L'utilisateur choisit une famille, règle ses paramètres,
et reçoit soit une **prédiction avec incertitude** (familles avec modèle), soit les **essais NASA réels
les plus proches** (familles sans modèle). Dans les deux cas : la source PSI de chaque essai montré.

Données attendues : `data/processed/{droplets,solids,gas,aerosols}.parquet` (à la racine du dépôt).

## Familles

| Dossier | Famille | Mode | Résultat principal (sessions jamais vues) | Détails |
|---|---|---|---|---|
| `flex/` | Gouttelettes (FLEX) | prédiction | issue : F1 macro **0,61** (réf. 0,27) ; vitesse : MAE **0,054** (réf. 0,108), couverture 95 % | `flex/validation.md` |
| `gas/` | Gaz (ACME CFI-G) | prédiction | issue : F1 macro **0,63** (réf. 0,24) | `gas/validation.md` |
| `solids/` | Solides (BASS-II, Saffire) | données réelles | pas de modèle honnête possible | `solids/validation.md` |
| `aerosols/` | Aérosols (SAME, SAME-R) | données réelles | pas de mesure de résultat dans la table | `aerosols/validation.md` |

## Structure

```
model_rf/
├── families.py       # fiches : entrées, sorties, filtres de chaque famille (+ choix du modèle)
├── data_prep.py      # chargement des tables, microgravité seulement
├── forest.py         # forêt aléatoire + incertitude (+ variantes testées : SMOTE, oversampling, réglée)
├── metrics.py        # validation par session, référence naïve, précision/rappel/F1, IC 95 %
├── recommend.py      # prochaine expérience recommandée (incertitude + zone inexplorée)
├── service.py        # MLService : point d'entrée unique pour le dashboard
├── data_only.py      # recherche d'essais réels (solides, aérosols)
├── family_tools.py   # fonctions communes aux sous-dossiers
├── train.py          # entraîne et sauvegarde dans artifacts/
├── flex/  gas/  solids/  aerosols/   # model.py, evaluate.py, validation.md (+ recommend.py pour flex)
├── experiments/      # essais d'amélioration, comparaisons, rapports
├── results/          # résultats des expériences (csv, txt)
└── artifacts/        # service entraîné (non versionné, recréé automatiquement)
```

## Commandes (depuis la racine du dépôt)

```bash
python -m src.models.model_rf.train                  # entraîne + évalue (~15 s)
python -m src.models.model_rf.flex.evaluate          # toutes les mesures FLEX
python -m src.models.model_rf.gas.evaluate
python -m src.models.model_rf.solids.evaluate        # description des données
python -m src.models.model_rf.aerosols.evaluate
python -m src.models.model_rf.flex.recommend         # prochaine expérience FLEX
python -m src.models.model_rf.experiments.rapport_complet   # toutes les familles -> results/
```

## Dans le dashboard

```python
import streamlit as st
from src.models.model_rf.service import MLService

@st.cache_resource
def get_ml():
    return MLService.load_or_train()   # charge artifacts/ ; s'il n'existe pas, entraîne (~15 s)

ml = get_ml()
cat = ml.catalogue()                   # [{"famille", "mode": "prediction" | "donnees", "description"}]
famille = st.selectbox("Type d'expérience", [c["famille"] for c in cat])
params = {}
for nom, p in ml.parameters(famille).items():
    if p["type"] == "nombre":
        params[nom] = st.slider(nom, p["min"], p["max"], p["defaut"])
    else:
        params[nom] = st.selectbox(nom, p["choix"])
r = ml.ask(famille, params)
# r["essais_proches"]    essais NASA réels les plus proches (avec source) — toujours présent
# r.get("avertissement") aucun essai proche / hors plage testée / catégorie jamais testée
# r["resultats"]         prédictions + incertitude (familles « prediction » seulement)
# ml.recommend_next_experiment(famille, params)   (familles « prediction » seulement)
# ml.explorer.summary(famille)                    tableau d'ensemble (familles « donnees »)
```

Attention : `x_o2`, `x_co2`, `x_he`, `x_fuel` sont des **fractions** (0,21 = 21 %).

## Règles suivies

- Microgravité uniquement ; jamais de mélange avec le 1g.
- Entrées = conditions fixées **avant** l'essai ; jamais une mesure faite pendant ou après.
- Validation par **session** (une session entière jamais vue à l'entraînement), comparaison à une
  référence naïve, désactivation automatique d'un modèle qui ne la bat pas.
- Une amélioration n'est retenue que si l'IC 95 % de son gain est entièrement positif
  (voir `experiments/ameliorations.py`, `experiments/oversampling.py`).
- Aucune donnée inventée n'est affichée : les essais artificiels de SMOTE servent uniquement à l'entraînement.

## Comparer avec model_gp

Pour une comparaison équitable, les deux modèles doivent passer **le même examen** :
mêmes tables, mêmes entrées, mêmes sessions mises de côté (`GroupKFold` à 5 plis sur `session`),
mêmes mesures (F1 macro pour les issues, MAE + couverture 95 % pour les valeurs).
Le plus simple : envelopper le modèle GP dans une classe à l'interface de `forest.ForestModel`
(`__init__(kind, entrees)`, `fit(X, y)`, `predict_with_uncertainty(X)`, `classes_`) — exemple dans
`experiments/modele_exemple.py` — puis lancer `experiments/compare_models.py`, et `metrics.paired_gain`
pour savoir si l'écart est réel.
