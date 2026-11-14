# Validation du modèle ACME CFI-G (flammes normales)

Généré par `python -m src.models.gas.evaluate` le 2026-11-14. Ne pas éditer à la main.

- Données : 177 flammes normales (jet de gaz dans une atmosphère contenant l'O2) sur 11 jours d'essai ; variables : is_ethane, is_propane, is_n_butane, x_o2, pressure_kpa, x_fuel, hc_rate_mg_s.
- O2 de 18% à 40% ; pression de 51 à 304 kPa.
- Validation croisée **par jour d'essai** (5 plis) ; référence : taux observé par combustible dans l'entraînement.
- Deux réglages comparés : longueur de corrélation libre (≥ 0,01) et contrainte (≥ 1, pour que l'O2, qui baisse au fil d'une journée, ne serve pas d'identifiant du jour). Réglage retenu dans `src/models/gas/model.py` : ≥ 1.

## Allumage d'une flamme chaude

| | AUC | Brier ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|
| Modèle, longueur ≥ 0.01 | 0.659 | 0.201 | 0.689 |
| Modèle, longueur ≥ 1 | 0.655 | 0.202 | 0.689 |
| Référence : taux par combustible | 0.445 | 0.206 | 0.746 |
| Référence : toujours la classe majoritaire | — | — | 0.746 |

177 essais ; part positive 0.75.

## Auto-extinction (essais allumés)

| | AUC | Brier ↓ | Exactitude (seuil 0,5) |
|---|---:|---:|---:|
| Modèle, longueur ≥ 0.01 | 0.749 | 0.170 | 0.803 |
| Modèle, longueur ≥ 1 | 0.759 | 0.166 | 0.818 |
| Référence : taux par combustible | 0.420 | 0.190 | 0.773 |
| Référence : toujours la classe majoritaire | — | — | 0.773 |

132 essais ; part positive 0.77.

## Données près de l'atmosphère d'exploration

20 flammes normales à ≤ 70 kPa et ≥ 30 % d'O2 (jours 21106, 21153, 21174) : 17 allumages ; parmi eux 13 auto-extinctions.

## Limites

- 11 jours d'essai seulement : la validation par jour repose sur peu de groupes.
- L'O2 de la chambre baisse au fil des essais d'une journée (combustion) : O2 et ordre des essais sont liés.
- « Auto-extinction » inclut des passages en flamme froide ; « flamme maintenue » (FT) = l'équipe a coupé le débit.
- Brûleur sphérique en chambre calme : rien sur l'effet d'une ventilation.
