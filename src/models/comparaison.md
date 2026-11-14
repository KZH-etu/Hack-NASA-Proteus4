# Comparaison des modèles

Généré par `python -m src.models.compare` le 2026-11-14. Ne pas éditer à la main.

Mêmes essais et mêmes 5 plis par **jour d'essai** pour tous les modèles : à chaque pli, chaque modèle est réentraîné avec son propre code et ses propres données, dont on retire tous les essais des jours de test, puis jugé sur les mêmes essais. Décision « extinction » : seuil 0,5 (model_gp), classe la plus probable (model_rf, model_catboost), probabilité de feu < 0,35 (model_thermo, son seuil d'origine). « model_catboost sans d_ext_mm » : même modèle sans le diamètre à l'extinction, mesuré après l'essai (diagnostic : c'est la version qu'on pourrait utiliser avant un essai).

## Gouttelettes FLEX : extinction de la flamme

261 essais, 69% d'extinctions.

| Modèle | Essais | AUC | Brier ↓ | MCC | F1 macro | Exactitude équilibrée | Exactitude |
|---|---:|---:|---:|---:|---:|---:|---:|
| model_gp | 261 | 0.906 | 0.111 | 0.623 | 0.807 | 0.793 | 0.843 |
| model_rf | 261 | 0.878 | 0.134 | 0.543 | 0.764 | 0.747 | 0.812 |
| model_catboost | 261 | 0.930 | 0.100 | 0.694 | 0.847 | 0.842 | 0.870 |
| model_catboost sans d_ext_mm | 261 | 0.884 | 0.133 | 0.569 | 0.784 | 0.787 | 0.812 |
| model_thermo | 261 | 0.812 | 0.159 | 0.395 | 0.697 | 0.702 | 0.732 |
| Référence naïve (taux d'extinction) | 261 | 0.392 | 0.220 | 0.000 | 0.407 | 0.500 | 0.686 |

### Constante de combustion K (mm²/s)

| Modèle | Essais | R² | Erreur absolue moyenne | Couverture de l'intervalle à 95 % |
|---|---:|---:|---:|---:|
| model_gp | 257 | 0.677 | 0.047 | 92.6% |
| model_rf | 257 | 0.622 | 0.053 | 95.3% |
| model_catboost | — | pas de prédiction de K | | |
| model_catboost sans d_ext_mm | — | pas de prédiction de K | | |
| model_thermo | 257 | -0.136 | 0.099 | pas d'intervalle |
| Référence naïve (K moyen par combustible) | 257 | 0.006 | 0.105 | — |

## Flammes gazeuses ACME CFI-G (normales, allumées) : extinction

132 essais, 77% d'extinctions.

| Modèle | Essais | AUC | Brier ↓ | MCC | F1 macro | Exactitude équilibrée | Exactitude |
|---|---:|---:|---:|---:|---:|---:|---:|
| model_gp | 132 | 0.760 | 0.153 | 0.442 | 0.720 | 0.713 | 0.811 |
| model_rf | 132 | 0.760 | 0.157 | 0.399 | 0.697 | 0.712 | 0.773 |
| model_catboost | 132 | 0.717 | 0.166 | 0.199 | 0.598 | 0.593 | 0.735 |
| model_catboost sans d_ext_mm | 132 | 0.716 | 0.166 | 0.280 | 0.640 | 0.638 | 0.750 |
| model_thermo | 132 | 0.687 | 0.163 | 0.294 | 0.643 | 0.659 | 0.727 |
| Référence naïve (taux d'extinction) | 132 | 0.376 | 0.180 | 0.000 | 0.436 | 0.500 | 0.773 |

## Solides : extinction ou combustion

114 essais, 80% d'extinctions.

| Modèle | Essais | AUC | Brier ↓ | MCC | F1 macro | Exactitude équilibrée | Exactitude |
|---|---:|---:|---:|---:|---:|---:|---:|
| model_gp | — | pas de modèle pour cette tâche | | | | | |
| model_rf | — | pas de modèle pour cette tâche | | | | | |
| model_catboost | 114 | 0.726 | 0.135 | 0.379 | 0.601 | 0.587 | 0.833 |
| model_catboost sans d_ext_mm | 114 | 0.710 | 0.144 | 0.177 | 0.564 | 0.559 | 0.789 |
| model_thermo | 114 | 0.814 | 0.125 | 0.363 | 0.675 | 0.657 | 0.816 |
| Référence naïve (taux d'extinction) | 114 | 0.186 | 0.186 | 0.000 | 0.444 | 0.500 | 0.798 |

## Scénario de mission (modèles livrés)

| Conditions (gouttelette d'heptane, 3 mm) | Essais FLEX proches : part d'extinctions | model_gp | model_rf | model_catboost | model_thermo |
|---|---:|---:|---:|---:|---:|
| Air de l'ISS : 21 % O2, 101,3 kPa | 0.45 (20 essais) | 0.41 [0.06–0.64] | 0.10 | 0.12 | 0.34 |
| Habitat lunaire : 34 % O2, 55 kPa | aucun essai | 0.02 [0.01–0.31] | 0.12 | 0.03 | 0.14 |
| Bas O2 : 15 % O2, 101,3 kPa | 1.00 (3 essais) | 0.97 [0.91–0.99] | 0.85 | 0.62 | 0.91 |

Probabilité d'extinction de la flamme ; entre crochets, l'intervalle à 90 % annoncé par model_gp quand il en donne un. Essais proches : heptane, O2 à ± 1,5 point, pression à ± 15 kPa, diamètre à ± 0,75 mm. Le scénario lunaire (55 kPa) est sous la plus basse pression testée par FLEX (≈ 70 kPa) : tous les modèles extrapolent.

