# Validation — Solides (BASS-II, Saffire) — PAS DE MODÈLE

Relancer : `python -m src.models.model_rf.solids.evaluate`

## Décision

**Aucun modèle de prédiction.** La famille est proposée en mode « données réelles » :
l'utilisateur règle matériau, forme, O2 et vitesse d'air, et reçoit les essais NASA réels
les plus proches (issue, mode d'extinction, notes, source PSI).

## Pourquoi

Données : `solids.parquet` (version solids_2), microgravité, BASS-II + Saffire I–III :
**142 essais, 33 sessions, 6 matériaux**. BASS (v1) exclu : issue presque jamais renseignée.

| Cible envisagée | Problème | Verdict |
|---|---|---|
| `outcome` (brûle / s'éteint) | 89 éteints contre 16 brûlés : protocole = air réduit **jusqu'à l'extinction** ; à air constant, 35 essais dont 3 brûlés | impossible à apprendre |
| `flow_min_cm_s` | vitesse de l'air **pendant** l'essai (souvent une rampe), égale à l'extinction très rarement | ce n'est pas un résultat |
| `extinction_flow_cm_s` | 14 essais seulement, presque tous en PMMA, 5 modes mélangés | trop peu |
| `extinction_pot` | position du bouton du ventilateur (pas des cm/s), déduite des notes, quasi constante (~0,3) | rien à prédire |
| `extinction_mode` | dépend surtout de la conduite de l'essai (opérateur), pas des conditions de départ | prédirait l'opérateur |

Une première version prédisait `flow_min_cm_s` comme « débit d'extinction » : elle faisait **moins bien
qu'une réponse fixe** (MAE 3,34 contre 2,99 cm/s) et reposait sur une mauvaise interprétation de la
colonne. Elle a été supprimée.

## Ce qui est montré

| Matériau | Forme | Essais | O2 testé | Manque d'air | Soufflage | Flamme brève |
|---|---|---|---|---|---|---|
| PMMA | tige | 54 | 13,6 – 22,2 % | 27 | 9 | 3 |
| SIBAL | tissu | 27 | 16,4 – 20,8 % | 6 | 2 | 5 |
| PMMA | film | 22 | 15,0 – 22,2 % | 8 | 2 | 1 |
| PMMA | plaque | 17 | 17,9 – 22,2 % | 9 | 0 | 1 |

Observation (quelques essais, pas une loi) : le tissu SIBAL s'éteint par manque d'air autour de
3 cm/s, une plaque de PMMA entre 5 et 18 cm/s.
