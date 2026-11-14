# Validation — Gouttelettes (FLEX) — forêt aléatoire

Relancer : `python -m src.models.model_rf.flex.evaluate`

## Données

- Table `droplets.parquet`, expérience FLEX, microgravité uniquement : **274 essais, 80 sessions**.
- Entrées (conditions fixées avant l'essai) : `fuel`, `x_o2`, `x_co2`, `x_he`, `pressure_kpa`, `d0_mm`.
- Sorties : `outcome` (completion / disruption / extinguished) et `burning_rate_mm2_s` (258 essais renseignés).
- Colonnes exclues car mesurées pendant ou après l'essai (fuite d'information) : `burn_time_s`, `d_ext_mm`.

## Méthode

- Forêt aléatoire, 300 arbres, `min_samples_leaf=2`.
- Issue : pondération des issues rares (`class_weight="balanced_subsample"`).
- Vitesse : intervalles calibrés par les prédictions hors-sac (out-of-bag), pour une couverture réelle de 95 %.
- Évaluation : `GroupKFold` à 5 plis **par session** (une session entière n'est jamais vue à l'entraînement).
- Référence naïve : toujours l'issue la plus fréquente, ou toujours la vitesse médiane.
- IC 95 % : bootstrap de sessions entières (1000 tirages).

## Résultats — issue

| Issue | Précision | Rappel | F1 | Support |
|---|---|---|---|---|
| completion | 0,50 | 0,26 | 0,34 | 27 |
| disruption | 0,62 | 0,62 | 0,62 | 61 |
| extinguished | 0,85 | 0,91 | 0,88 | 186 |
| **macro** | 0,66 | 0,60 | **0,61** | 274 |
| pondérée | 0,76 | 0,78 | 0,77 | 274 |

| Mesure | Modèle | Référence |
|---|---|---|
| Accuracy | **0,78** | 0,68 |
| F1 macro | **0,61** (IC 0,51 – 0,70) | 0,27 |
| Exactitude équilibrée | 0,60 (IC 0,51 – 0,68) | 0,33 |
| Écart de fiabilité des probabilités | 0,065 | — |

Matrice de confusion (lignes = vrai, colonnes = prédit) :

| | completion | disruption | extinguished |
|---|---|---|---|
| completion | 7 | 9 | 11 |
| disruption | 4 | 38 | 19 |
| extinguished | 3 | 14 | 169 |

## Résultats — vitesse de combustion (mm²/s)

| Mesure | Modèle | Référence |
|---|---|---|
| MAE | **0,054** (IC 0,044 – 0,067) | 0,108 |
| RMSE | 0,085 | 0,138 |
| R² | **0,62** (IC 0,45 – 0,74) | 0 |
| Erreur relative moyenne | 13 % | — |
| Couverture de l'intervalle 95 % | **95,3 %** | — |

## Améliorations testées (règle fixée avant : gain retenu seulement si IC 95 % du gain > 0)

| Essai | Résultat | Décision |
|---|---|---|
| Pondération des issues rares | rappel completion 15 % → 26 % | **retenue** |
| Calibration des intervalles | couverture 90 % → 95 % | **retenue** |
| Variables physiques (p_O2 = x_o2 × pression…) | pas de gain démontré | non retenue |
| Réglage automatique (validation imbriquée) | pas de gain démontré | non retenu |
| Oversampling aléatoire / SMOTE | pas de gain démontré | non retenus |

## Limites

- **combustion complète** mal reconnue (27 cas seulement) : rappel 26 %.
- Pression testée de 70 à 309 kPa : un habitat à 56 kPa est **hors plage** (alerte automatique).
- La forêt n'extrapole pas : hors plage, elle répond comme au bord des données.
