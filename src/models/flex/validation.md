# Validation du modèle FLEX

Généré par `python -m src.models.flex.evaluate` le 2026-11-14. Ne pas éditer à la main.

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

## Constante de combustion K (mm²/s)

| | R² | Erreur absolue moyenne |
|---|---:|---:|
| **Modèle (processus gaussien)** | 0.677 | 0.047 |
| Référence : K moyen par combustible | 0.006 | 0.105 |

Intervalle à 90 % (± 1,645 écart-type) : la vraie valeur est dedans dans **90%** des cas (attendu : 90 %) ; écart-type moyen 0.066 mm²/s ; 257 essais avec K.

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
