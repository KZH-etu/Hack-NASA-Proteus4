# Modèles

Chaque modèle est un dossier `src/models/model_<nom>/` (underscore et non tiret : un nom de module Python ne peut pas contenir de tiret). Plusieurs modèles peuvent cohabiter ; l'app les liste et les charge par leur nom :

```python
from src.models import available_models, load
available_models()                 # ['model_gp', ...]
m = load("model_gp")
m.FAMILIES["droplets"].predict({"fuel": "heptane", "o2_percent": 21, "pressure_kpa": 101.3, "d0_mm": 3.0})
m.recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0})
```

## Modèles présents

| Dossier | Contenu |
|---|---|
| `model_gp/` | Processus gaussiens : `flex/` (gouttelettes FLEX), `solids/` (BASS / BASS-II), `gas/` (ACME CFI-G) ; `recommend.py` (prochaine expérience). Rapports de validation dans `<famille>/validation.md`. |
| `model_rf/` | Forêts aléatoires avec incertitude, une par famille ; point d'entrée `service.py` (`MLService`), voir `model_rf/README.md`. Pas encore de `FAMILIES` : `load("model_rf")` ne donne pas l'interface commune. |
| `model_catboost/` | Un seul CatBoost à 3 classes (extinction / combustion / intermédiaire) pour gouttelettes, solides et gaz. `train.py` (entraînement, écrit `catboost_fire_3classes.cbm`), `evaluate.py` → `validation.md`. Pas de recommandation. |

| `model_thermo/` (Nicolas) | Gradient boosting sur des propriétés thermo-physiques des matériaux (toutes familles) ; `predict_fire_safety(...)`, `train.py` (données : `data/processed/experiments_all.csv`). Pas encore de `FAMILIES`. |

## Comparer les modèles

`python -m src.models.compare` réentraîne chaque modèle sur les mêmes plis par jour d'essai et écrit `comparaison.md`.

## Ajouter un modèle

1. Créer `src/models/model_<nom>/` avec un `__init__.py` qui expose :
   - `NAME` (le nom du dossier) et `DESCRIPTION` (une phrase) ;
   - `FAMILIES` : dictionnaire `{"droplets": ..., "solids": ..., "gas": ...}` (seulement les familles couvertes), chaque valeur ayant une fonction `predict(conditions) -> dict` ;
   - `recommend_next_experiment(scenario, n=5) -> dict` (facultatif).
2. Entrées de `predict` (mêmes clés que `model_gp`, pour que l'app puisse comparer les modèles) :
   - `droplets` : `fuel`, `o2_percent`, `pressure_kpa`, `co2_percent`, `he_percent`, `d0_mm` ;
   - `solids` : `material`, `o2_percent`, `flow_cm_s` ;
   - `gas` : `fuel`, `o2_percent`, `pressure_kpa`, `x_fuel`, `hc_rate_mg_s`.
3. Sorties : un dictionnaire avec les probabilités, **un intervalle d'incertitude** et une liste `warnings` (extrapolation, pas de donnée proche, fiabilité) que l'app affiche telle quelle.
4. Règles du projet :
   - données : `src.data.build_unified.load_family(...)` (jamais de données inventées) ; ne jamais mélanger 1g et microgravité ;
   - validation **par jour d'essai** (colonne `session`), comparée à des références naïves, résultats annoncés tels quels ;
   - un `evaluate.py` qui écrit un `validation.md` dans le dossier du modèle.
