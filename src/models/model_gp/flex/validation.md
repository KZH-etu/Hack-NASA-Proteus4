# Validation du modèle FLEX

Généré par `python -m src.models.model_gp.flex.evaluate` le 2026-11-14. Ne pas éditer à la main.

- Données : 261 essais FLEX utilisables (toutes les variables présentes) sur 80 jours d'essai ; variables : is_heptane, x_o2, pressure_kpa, x_co2, x_he, d0_mm.
- Validation croisée **par jour d'essai** (5 plis, `GroupKFold` sur `session`) : un jour n'est jamais à la fois en entraînement et en test.
- Références naïves : taux d'extinction (ou K moyen) du même combustible dans les données d'entraînement ; classe majoritaire.

## Extinction (la flamme s'éteint avant la fin de la combustion)

| | AUC | Brier ↓ | Log loss ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|---:|
| **Modèle (processus gaussien)** | 0.906 | 0.111 | 0.352 | 0.843 |
| Référence : taux par combustible | 0.598 | 0.206 | 0.598 | 0.644 |
| Référence : toujours la classe majoritaire | — | — | — | 0.686 |

Par combustible (modèle) :

| Combustible | Essais | AUC | Brier | Exactitude |
|---|---:|---:|---:|---:|
| heptane | 108 | 0.911 | 0.123 | 0.815 |
| methanol | 153 | 0.880 | 0.102 | 0.863 |

Calibration (hors échantillon) :

| Probabilité prédite | Essais | Moyenne prédite | Fréquence observée |
|---|---:|---:|---:|
| 0.0–0.2 | 35 | 0.09 | 0.06 |
| 0.2–0.4 | 19 | 0.32 | 0.37 |
| 0.4–0.6 | 28 | 0.49 | 0.36 |
| 0.6–0.8 | 37 | 0.71 | 0.76 |
| 0.8–1.0 | 142 | 0.93 | 0.93 |

Métriques détaillées (hors échantillon, seuil 0.5) : 261 cas, 69% « extinction » ; exactitude en répondant toujours la classe majoritaire : 0.686.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.843 | 0.644 |
| Exactitude équilibrée | 0.793 | 0.486 |
| Précision « extinction » | 0.856 | 0.679 |
| Rappel « extinction » | 0.927 | 0.911 |
| F1 « extinction » | 0.890 | 0.778 |
| Précision « la flamme tient » | 0.806 | 0.238 |
| Rappel « la flamme tient » | 0.659 | 0.061 |
| F1 « la flamme tient » | 0.725 | 0.097 |
| F1 macro | 0.807 | 0.438 |
| MCC (0 = hasard, 1 = parfait) | 0.623 | -0.048 |
| AUC | 0.906 | 0.598 |
| Brier (plus bas = mieux) | 0.111 | 0.206 |
| Log loss (plus bas = mieux) | 0.352 | 0.598 |

Matrices de confusion (positif = « extinction ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 166 | 13 | 28 | 54 |
| Référence naïve | 163 | 16 | 77 | 5 |

## Constante de combustion K (mm²/s)

| | R² | Erreur absolue moyenne | RMSE |
|---|---:|---:|---:|
| **Modèle (processus gaussien)** | 0.677 | 0.047 | 0.078 |
| Référence : K moyen par combustible | 0.006 | 0.105 | 0.137 |

Intervalle à 90 % (± 1,645 écart-type) : la vraie valeur est dedans dans **90%** des cas (attendu : 90 %) ; écart-type moyen 0.066 mm²/s ; 257 essais avec K.

| Intervalle | Part des essais dedans | Attendu |
|---|---:|---:|
| ± 1 écart-type (68 %) | 80.5% | 68 % |
| ± 1,645 écart-type (90 %) | 89.9% | 90 % |
| ± 1,96 écart-type (95 %) | 92.6% | 95 % |
| **Intervalle à 95 % calibré** (`burning_rate_k_interval_95`) | **94.9%** | 95 % |

Calibration : l'écart-type est élargi d'un facteur appris par validation croisée interne par jour d'essai, sur les seules données d'entraînement de chaque pli (facteurs obtenus : 1.0, 1.2, 1.27, 1.28, 1.35).

## Importance des variables (longueurs de corrélation du noyau, données normalisées ; petite = influente)

| Variable | Extinction | K |
|---|---:|---:|
| is_heptane | 1.90 | 2.12 |
| x_o2 | 3.53 | 3.56 |
| pressure_kpa | 100.00 | 4.63 |
| x_co2 | 13.59 | 5.19 |
| x_he | 14.20 | 6.53 |
| d0_mm | 4.42 | 2.82 |

## Limites

- Les essais FLEX ont été choisis pour encadrer les limites d'extinction : ce n'est pas un échantillon uniforme des conditions possibles.
- Heptane et méthanol seulement ; pression de 70 à 309 kPa (aucun essai sous 0,69 atm) ; O2 de 12 à 34 %.
- Une prédiction hors de ces plages est une extrapolation : `predict()` le signale, ainsi que l'absence d'essai proche.
- La pression n'a presque aucun effet appris sur l'extinction (longueur de corrélation à la borne) : sous 70 kPa, l'intervalle d'incertitude est sous-estimé ; c'est précisément la zone de l'atmosphère d'exploration (≈ 55 kPa).
- La zone de probabilité 0,4–0,6 est un peu surestimée (voir calibration).
