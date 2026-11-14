# Validation du modèle ACME CFI-G (flammes normales)

Généré par `python -m src.models.model_gp.gas.evaluate` le 2026-11-14. Ne pas éditer à la main.

- Données : 177 flammes normales (jet de gaz dans une atmosphère contenant l'O2) sur 11 jours d'essai ; variables : is_ethane, is_propane, is_n_butane, x_o2, pressure_kpa, x_fuel, hc_rate_mg_s.
- O2 de 18% à 40% ; pression de 51 à 304 kPa.
- Validation croisée **par jour d'essai** (5 plis) ; référence : taux observé par combustible dans l'entraînement.
- Deux réglages comparés : longueur de corrélation libre (≥ 0,01) et contrainte (≥ 1, pour que l'O2, qui baisse au fil d'une journée, ne serve pas d'identifiant du jour). Réglage retenu dans `src/models/model_gp/gas/model.py` : ≥ 1.

## Allumage d'une flamme chaude

| | AUC | Brier ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|
| Modèle, longueur ≥ 0.01 | 0.659 | 0.201 | 0.689 |
| Modèle, longueur ≥ 1 | 0.655 | 0.202 | 0.689 |
| Référence : taux par combustible | 0.445 | 0.206 | 0.746 |
| Référence : toujours la classe majoritaire | — | — | 0.746 |

177 essais ; part positive 0.75.

Réglage retenu (longueur ≥ 1) :

Métriques détaillées (hors échantillon, seuil 0.5) : 177 cas, 75% « allumage » ; exactitude en répondant toujours la classe majoritaire : 0.746.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.689 | 0.746 |
| Exactitude équilibrée | 0.535 | 0.500 |
| Précision « allumage » | 0.762 | 0.746 |
| Rappel « allumage » | 0.848 | 1.000 |
| F1 « allumage » | 0.803 | 0.854 |
| Précision « pas d'allumage » | 0.333 | 0.000 |
| Rappel « pas d'allumage » | 0.222 | 0.000 |
| F1 « pas d'allumage » | 0.267 | 0.000 |
| F1 macro | 0.535 | 0.427 |
| MCC (0 = hasard, 1 = parfait) | 0.082 | 0.000 |
| AUC | 0.655 | 0.445 |
| Brier (plus bas = mieux) | 0.202 | 0.206 |
| Log loss (plus bas = mieux) | 0.591 | 0.644 |

Matrices de confusion (positif = « allumage ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 112 | 20 | 35 | 10 |
| Référence naïve | 132 | 0 | 45 | 0 |

## Auto-extinction (essais allumés)

| | AUC | Brier ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|
| Modèle, longueur ≥ 0.01 | 0.749 | 0.170 | 0.803 |
| Modèle, longueur ≥ 1 | 0.759 | 0.166 | 0.818 |
| Référence : taux par combustible | 0.420 | 0.190 | 0.773 |
| Référence : toujours la classe majoritaire | — | — | 0.773 |

132 essais ; part positive 0.77.

Réglage retenu (longueur ≥ 1) :

Métriques détaillées (hors échantillon, seuil 0.5) : 132 cas, 77% « auto-extinction » ; exactitude en répondant toujours la classe majoritaire : 0.773.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.818 | 0.773 |
| Exactitude équilibrée | 0.729 | 0.500 |
| Précision « auto-extinction » | 0.875 | 0.773 |
| Rappel « auto-extinction » | 0.892 | 1.000 |
| F1 « auto-extinction » | 0.883 | 0.872 |
| Précision « flamme maintenue » | 0.607 | 0.000 |
| Rappel « flamme maintenue » | 0.567 | 0.000 |
| F1 « flamme maintenue » | 0.586 | 0.000 |
| F1 macro | 0.735 | 0.436 |
| MCC (0 = hasard, 1 = parfait) | 0.470 | 0.000 |
| AUC | 0.759 | 0.420 |
| Brier (plus bas = mieux) | 0.166 | 0.190 |
| Log loss (plus bas = mieux) | 0.509 | 0.581 |

Matrices de confusion (positif = « auto-extinction ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 91 | 11 | 13 | 17 |
| Référence naïve | 102 | 0 | 30 | 0 |

## Données près de l'atmosphère d'exploration

20 flammes normales à ≤ 70 kPa et ≥ 30 % d'O2 (jours 21106, 21153, 21174) : 17 allumages ; parmi eux 13 auto-extinctions.

## Limites

- 11 jours d'essai seulement : la validation par jour repose sur peu de groupes.
- L'O2 de la chambre baisse au fil des essais d'une journée (combustion) : O2 et ordre des essais sont liés.
- « Auto-extinction » inclut des passages en flamme froide ; « flamme maintenue » (FT) = l'équipe a coupé le débit.
- Brûleur sphérique en chambre calme : rien sur l'effet d'une ventilation.
