# Validation du modèle CatBoost (3 classes, toutes familles)

Généré par `python -m src.models.model_catboost.evaluate` le 2026-11-14. Ne pas éditer à la main.

- Données : 659 essais (gouttelettes, solides, gaz) dont le résultat est extinction (`extinguished`), combustion (`burned`, `completion`) ou intermédiaire (`disruption`) ; gouttelettes 274, gaz 271, solides 114.
- 32 variables : material, geometry, thickness_mm, width_cm, length_cm, diameter_mm, color, flow_direction, flow_cm_s, flow_restrictor, x_o2, pressure_kpa, co2_initial_pct, co2_mmhg, co_initial_ppm, ignition_power_W, gravity, material_type, flame_type, fuel, x_fuel, hc_rate_mg_s, o2_rate_mg_s, z_st, t_ad_K, fuel_main_fraction, x_n2, x_co2, x_he, diluent, d0_mm, d_ext_mm.
- Logique du modèle inchangée par rapport au script d'origine (voir `model.py`).

## 1. Découpage d'origine (20 % des essais en test, une seule fois)

Résultat du script d'origine, reproduit à l'identique (meilleure itération : 1038).

132 cas ; exactitude en répondant toujours la classe majoritaire : 0.697.

| Métrique | Modèle | Référence naïve (fréquences par famille) |
|---|---:|---:|
| Exactitude (accuracy) | 0.826 | 0.697 |
| Exactitude équilibrée | 0.689 | 0.333 |
| F1 macro | 0.715 | 0.274 |
| F1 pondéré | 0.820 | 0.573 |
| MCC (0 = hasard, 1 = parfait) | 0.604 | 0.000 |
| AUC (une classe contre les autres, moyenne) | 0.902 | 0.675 |
| Log loss (plus bas = mieux) | 2.012 | 1.419 |

Par classe (modèle) :

| Classe | Précision | Rappel | F1 | Cas |
|---|---:|---:|---:|---:|
| extinction | 0.867 | 0.924 | 0.895 | 92 |
| combustion | 0.720 | 0.643 | 0.679 | 28 |
| intermediate | 0.667 | 0.500 | 0.571 | 12 |

Matrice de confusion du modèle (lignes = réel, colonnes = prédit) :

| | extinction | combustion | intermediate |
|---|---:|---:|---:|
| extinction | 85 | 7 | 0 |
| combustion | 7 | 18 | 3 |
| intermediate | 6 | 0 | 6 |

## 2. Validation croisée par jour d'essai (comparable à model_gp)

5 plis, `GroupKFold` sur le jour d'essai (135 jours) : tous les essais d'un même jour sont du même côté. Le découpage d'origine sépare les essais mais pas les jours ; or les essais d'un même jour se ressemblent (même montage, même gaz, réglages voisins), ce qui rend un test par essai plus optimiste.
Meilleures itérations par pli : 942, 145, 1106, 1234, 315.

659 cas ; exactitude en répondant toujours la classe majoritaire : 0.698.

| Métrique | Modèle | Référence naïve (fréquences par famille) |
|---|---:|---:|
| Exactitude (accuracy) | 0.766 | 0.698 |
| Exactitude équilibrée | 0.656 | 0.333 |
| F1 macro | 0.648 | 0.274 |
| F1 pondéré | 0.740 | 0.574 |
| MCC (0 = hasard, 1 = parfait) | 0.454 | 0.000 |
| AUC (une classe contre les autres, moyenne) | 0.843 | 0.619 |
| Log loss (plus bas = mieux) | 1.637 | 1.397 |

Par classe (modèle) :

| Classe | Précision | Rappel | F1 | Cas |
|---|---:|---:|---:|---:|
| extinction | 0.805 | 0.913 | 0.855 | 460 |
| combustion | 0.561 | 0.268 | 0.363 | 138 |
| intermediate | 0.676 | 0.787 | 0.727 | 61 |

Matrice de confusion du modèle (lignes = réel, colonnes = prédit) :

| | extinction | combustion | intermediate |
|---|---:|---:|---:|
| extinction | 420 | 28 | 12 |
| combustion | 90 | 37 | 11 |
| intermediate | 12 | 1 | 48 |

Par famille (modèle, validation par jour d'essai) :

| Famille | Cas | Exactitude | Exactitude équilibrée | F1 macro | MCC |
|---|---:|---:|---:|---:|---:|
| Gouttelettes | 274 | 0.821 | 0.622 | 0.624 | 0.612 |
| Solides | 114 | 0.816 | 0.543 | 0.352 | 0.266 |
| Gaz | 271 | 0.690 | 0.602 | 0.404 | 0.234 |

Par famille (référence naïve) :

| Famille | Cas | Exactitude | Exactitude équilibrée | F1 macro | MCC |
|---|---:|---:|---:|---:|---:|
| Gouttelettes | 274 | 0.679 | 0.333 | 0.270 | 0.000 |
| Solides | 114 | 0.798 | 0.500 | 0.296 | 0.000 |
| Gaz | 271 | 0.675 | 0.500 | 0.269 | 0.000 |

### Vue binaire « extinction » contre le reste, par famille

Probabilité d'extinction du modèle, mêmes métriques que les rapports de model_gp. Attention : les tâches ne sont pas identiques à celles de model_gp (ici tous les essais de la famille, résultat de l'essai ; model_gp/flex : essais FLEX complets ; model_gp/solids : observations « la flamme tient » à chaque réglage ; model_gp/gas : allumage puis auto-extinction des flammes normales).

#### Gouttelettes

Métriques détaillées (hors échantillon, seuil 0.5) : 274 cas, 68% « extinction » ; exactitude en répondant toujours la classe majoritaire : 0.679.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.810 | 0.679 |
| Exactitude équilibrée | 0.800 | 0.500 |
| Précision « extinction » | 0.885 | 0.679 |
| Rappel « extinction » | 0.828 | 1.000 |
| F1 « extinction » | 0.856 | 0.809 |
| Précision « pas d'extinction » | 0.680 | 0.000 |
| Rappel « pas d'extinction » | 0.773 | 0.000 |
| F1 « pas d'extinction » | 0.723 | 0.000 |
| F1 macro | 0.789 | 0.404 |
| MCC (0 = hasard, 1 = parfait) | 0.583 | 0.000 |
| AUC | 0.886 | 0.402 |
| Brier (plus bas = mieux) | 0.127 | 0.221 |
| Log loss (plus bas = mieux) | 0.407 | 0.635 |

Matrices de confusion (positif = « extinction ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 154 | 32 | 20 | 68 |
| Référence naïve | 186 | 0 | 88 | 0 |

#### Solides

Métriques détaillées (hors échantillon, seuil 0.5) : 114 cas, 80% « extinction » ; exactitude en répondant toujours la classe majoritaire : 0.798.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.833 | 0.798 |
| Exactitude équilibrée | 0.587 | 0.500 |
| Précision « extinction » | 0.827 | 0.798 |
| Rappel « extinction » | 1.000 | 1.000 |
| F1 « extinction » | 0.905 | 0.888 |
| Précision « pas d'extinction » | 1.000 | 0.000 |
| Rappel « pas d'extinction » | 0.174 | 0.000 |
| F1 « pas d'extinction » | 0.296 | 0.000 |
| F1 macro | 0.601 | 0.444 |
| MCC (0 = hasard, 1 = parfait) | 0.379 | 0.000 |
| AUC | 0.742 | 0.288 |
| Brier (plus bas = mieux) | 0.131 | 0.171 |
| Log loss (plus bas = mieux) | 0.439 | 0.536 |

Matrices de confusion (positif = « extinction ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 91 | 0 | 19 | 4 |
| Référence naïve | 91 | 0 | 23 | 0 |

#### Gaz

Métriques détaillées (hors échantillon, seuil 0.5) : 271 cas, 68% « extinction » ; exactitude en répondant toujours la classe majoritaire : 0.675.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.679 | 0.675 |
| Exactitude équilibrée | 0.594 | 0.500 |
| Précision « extinction » | 0.729 | 0.675 |
| Rappel « extinction » | 0.836 | 1.000 |
| F1 « extinction » | 0.779 | 0.806 |
| Précision « pas d'extinction » | 0.508 | 0.000 |
| Rappel « pas d'extinction » | 0.352 | 0.000 |
| F1 « pas d'extinction » | 0.416 | 0.000 |
| F1 macro | 0.597 | 0.403 |
| MCC (0 = hasard, 1 = parfait) | 0.211 | 0.000 |
| AUC | 0.705 | 0.362 |
| Brier (plus bas = mieux) | 0.195 | 0.227 |
| Log loss (plus bas = mieux) | 0.571 | 0.648 |

Matrices de confusion (positif = « extinction ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 153 | 30 | 57 | 31 |
| Référence naïve | 183 | 0 | 88 | 0 |

## 3. Diagnostic : sans `d_ext_mm`

`d_ext_mm` (diamètre de la gouttelette à l'extinction) est mesuré **après** l'essai et n'est renseigné que s'il y a eu extinction ; il fait partie des entrées du modèle. Même validation par jour d'essai, cette variable retirée (diagnostic seulement, le modèle livré la garde) :

| | Exactitude | Exactitude équilibrée | F1 macro | MCC | Log loss |
|---|---:|---:|---:|---:|---:|
| Modèle tel quel | 0.766 | 0.656 | 0.648 | 0.454 | 1.637 |
| Sans `d_ext_mm` | 0.734 | 0.640 | 0.617 | 0.404 | 1.604 |

Par famille, sans `d_ext_mm` :

| Famille | Cas | Exactitude | Exactitude équilibrée | F1 macro | MCC |
|---|---:|---:|---:|---:|---:|
| Gouttelettes | 274 | 0.741 | 0.540 | 0.509 | 0.453 |
| Solides | 114 | 0.833 | 0.587 | 0.401 | 0.379 |
| Gaz | 271 | 0.686 | 0.626 | 0.420 | 0.262 |

## Limites

- Pas d'intervalle d'incertitude (probabilité ponctuelle).
- Un seul modèle pour des familles aux variables différentes : les variables d'une famille sont vides pour les autres ; `material_type` et `gravity` sont des entrées (la gravité 1g ne concerne que des essais de solides).
- Avant un essai, `d_ext_mm` est inconnu : la prédiction se fait avec cette entrée vide (voir section 3).
