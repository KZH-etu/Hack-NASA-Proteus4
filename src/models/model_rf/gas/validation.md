# Validation — Gaz (ACME CFI-G) — forêt aléatoire + SMOTE

Relancer : `python -m src.models.model_rf.gas.evaluate`

## Données

- Table `gas.parquet`, expérience ACME CFI-G, microgravité : **331 essais, 23 sessions**
  (2 essais « other » retirés, inclassables).
- Entrées : `fuel`, `flame_type`, `x_fuel`, `x_o2`, `pressure_kpa`, `hc_rate_mg_s`.
- Sortie : `outcome` (burned / extinguished / no_ignition).
- Colonnes exclues (fuite d'information) : `hot_ignition_raw` (donne directement no_ignition),
  `end_mode_raw`, `burn_time_s`.
- SPICE et ACME Flame Design : aucune colonne de résultat → pas de modèle.

## Méthode

- Forêt aléatoire, 300 arbres, `min_samples_leaf=2`, sans pondération.
- **SMOTE** dans `fit()` uniquement : création d'essais rares artificiels par interpolation entre
  deux essais rares voisins. Ces essais servent seulement à l'entraînement — jamais évalués ni affichés.
- Évaluation : `GroupKFold` à 5 plis par session ; IC 95 % par bootstrap de sessions.

## Résultats

| Issue | Précision | Rappel | F1 | Support |
|---|---|---|---|---|
| burned | 0,64 | 0,75 | 0,69 | 88 |
| extinguished | 0,76 | 0,78 | 0,77 | 183 |
| no_ignition | 0,53 | 0,35 | 0,42 | 60 |
| **macro** | 0,64 | 0,63 | **0,63** | 331 |
| pondérée | 0,69 | 0,70 | 0,69 | 331 |

| Mesure | Modèle | Référence |
|---|---|---|
| Accuracy | **0,70** | 0,55 |
| F1 macro | **0,63** (IC 0,54 – 0,71) | 0,24 |
| Exactitude équilibrée | 0,63 (IC 0,55 – 0,71) | 0,33 |
| Écart de fiabilité des probabilités | 0,042 | — |

Matrice de confusion (lignes = vrai, colonnes = prédit) :

| | burned | extinguished | no_ignition |
|---|---|---|---|
| burned | 66 | 19 | 3 |
| extinguished | 24 | 143 | 16 |
| no_ignition | 13 | 26 | 21 |

## Choix de SMOTE

| Variante | F1 macro | Gain vs pondération (IC 95 %) |
|---|---|---|
| Aucun rééquilibrage | 0,54 | −0,043 [−0,101 ; +0,039] |
| Pondération | 0,58 | — |
| Oversampling aléatoire | 0,58 | +0,003 [−0,027 ; +0,031] |
| **SMOTE** | **0,63** | **+0,047 [+0,005 ; +0,114]** → retenu |

Réserve : 6 comparaisons au total (gouttes + gaz), gain de justesse au-dessus de 0.
À re-vérifier (`python -m src.models.model_rf.experiments.oversampling`) si les données changent.

## Limites

- **no_ignition** mal reconnu (rappel 35 %) : l'allumage dépend de l'allumeur, absent des entrées.
- 23 sessions seulement : intervalles de confiance larges.
- `flame_type` normal / inverse : `x_fuel` et `x_o2` n'ont pas le même sens dans les deux cas
  (le modèle reçoit `flame_type` en entrée pour en tenir compte).
