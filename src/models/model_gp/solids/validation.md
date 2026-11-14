# Validation du modèle des solides (carte d'inflammabilité BASS / BASS-II)

Généré par `python -m src.models.model_gp.solids.evaluate` le 2026-11-14. Ne pas éditer à la main.

- Données : 218 observations « la flamme tient / ne tient pas » tirées de 95 essais (29 jours d'essai) ; règles d'étiquetage dans `src/models/model_gp/solids/model.py`.
- Variables : is_pmma_flat, is_pmma_rod_sphere, is_fabric_other, x_o2, log_flow.
- O2 de 14.2% à 22.2% ; vitesse d'air de 0.5 à 53 cm/s ; pression ~1 atm.
- Validation croisée **par jour d'essai** (5 plis) : les observations d'un même essai (et d'un même jour) ne sont jamais séparées.

## Verdict

**Fiabilité faible** : AUC 0.59 (0,5 = hasard), exactitude 74% contre 76% en répondant toujours la classe majoritaire. Les données BASS / BASS-II ne suffisent pas à prédire, d'un jour d'essai à l'autre, si une flamme tient. Variantes testées avec la même validation (matériau détaillé en 6 classes, débit linéaire, longueur de corrélation libre : AUC 0,50 ; régression logistique avec log(débit)² : AUC 0,52–0,55) : aucune ne fait mieux. Le modèle retenu sert seulement d'indication ; la recommandation repose surtout sur la nouveauté (distance aux essais existants).

## La flamme tient-elle ?

| | AUC | Brier ↓ | Log loss ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|---:|
| **Modèle (processus gaussien)** | 0.589 | 0.198 | 0.602 | 0.739 |
| Référence : taux par classe de matériau | 0.419 | 0.213 | 0.647 | 0.752 |
| Référence : toujours la classe majoritaire | — | — | — | 0.761 |

Calibration (hors échantillon) :

| Probabilité prédite | Observations | Moyenne prédite | Fréquence observée |
|---|---:|---:|---:|
| 0.0–0.2 | 1 | 0.16 | 0.00 |
| 0.2–0.4 | 18 | 0.28 | 0.50 |
| 0.4–0.6 | 49 | 0.50 | 0.73 |
| 0.6–0.8 | 82 | 0.71 | 0.84 |
| 0.8–1.0 | 68 | 0.88 | 0.76 |

Métriques détaillées (hors échantillon, seuil 0.5) : 218 cas, 76% « la flamme tient » ; exactitude en répondant toujours la classe majoritaire : 0.761.

| Métrique | Modèle | Référence naïve |
|---|---:|---:|
| Exactitude (accuracy) | 0.739 | 0.752 |
| Exactitude équilibrée | 0.610 | 0.494 |
| Précision « la flamme tient » | 0.811 | 0.759 |
| Rappel « la flamme tient » | 0.855 | 0.988 |
| F1 « la flamme tient » | 0.833 | 0.859 |
| Précision « ne tient pas » | 0.442 | 0.000 |
| Rappel « ne tient pas » | 0.365 | 0.000 |
| F1 « ne tient pas » | 0.400 | 0.000 |
| F1 macro | 0.616 | 0.429 |
| MCC (0 = hasard, 1 = parfait) | 0.236 | -0.054 |
| AUC | 0.589 | 0.419 |
| Brier (plus bas = mieux) | 0.198 | 0.213 |
| Log loss (plus bas = mieux) | 0.602 | 0.647 |

Matrices de confusion (positif = « la flamme tient ») :

| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |
|---|---:|---:|---:|---:|
| Modèle | 142 | 24 | 33 | 19 |
| Référence naïve | 164 | 2 | 52 | 0 |

Observations par classe de matériau :

| Classe | Observations | Part « tient » |
|---|---:|---:|
| pmma_thin | 32 | 0.81 |
| pmma_thick | 67 | 0.84 |
| pmma_rod | 78 | 0.72 |
| pmma_sphere | 5 | 0.80 |
| sibal | 30 | 0.70 |
| other | 6 | 0.50 |

## Importance des variables (longueurs de corrélation, données normalisées ; petite = influente)

| Variable | Longueur |
|---|---:|
| is_pmma_flat | 3.36 |
| is_pmma_rod_sphere | 3.31 |
| is_fabric_other | 100.00 |
| x_o2 | 1.48 |
| log_flow | 2.08 |

## Limites

- **Aucun essai solide au-dessus de 22,7 % d'O2** (BASS) / 22,2 % (observations utilisées) : toute prédiction en atmosphère enrichie est une extrapolation.
- Les vitesses sont celles de l'anémomètre ; quand l'extinction a lieu à un réglage du potentiomètre sous la dernière vitesse affichée, seuls les points « tient » sont connus (la limite basse réelle est plus basse que la dernière vitesse affichée).
- Peu d'observations « ne tient pas » ; les essais ont été conduits pour chercher les limites, ce n'est pas un échantillon uniforme.
- Pression nominale 1 atm (BASS-II) : le modèle ne dit rien de l'effet de la pression.
