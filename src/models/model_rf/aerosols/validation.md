# Validation — Aérosols / fumées (SAME, SAME-R) — PAS DE MODÈLE

Relancer : `python -m src.models.model_rf.aerosols.evaluate`

## Décision

**Aucun modèle de prédiction.** Famille proposée en mode « données réelles » : l'utilisateur règle
matériau, vitesse d'air et chauffe (Rt/R0) et reçoit les essais NASA réels les plus proches.

## Pourquoi

Données : `aerosols.parquet`, microgravité : **129 essais, 18 sessions, 7 matériaux**.

- `rt_r0` = Rt/R0 = résistance du fil chauffant à chaud / à température ambiante :
  c'est le **réglage** de la température de chauffe (une entrée), pas un résultat.
- La table ne contient **aucune mesure de fumée** (taille ou nombre de particules, réponse des détecteurs).
- Il n'y a donc rien à prédire.

Si ces mesures sont retrouvées dans les fichiers PSI de SAME, un modèle « matériau + chauffe + air →
fumée produite » deviendrait possible (utile pour la conception de détecteurs).

## Ce qui est montré

| Expérience | Matériau | Essais | Vitesses d'air (cm/s) | Rt/R0 |
|---|---|---|---|---|
| SAME | 5 matériaux | 4 chacun | 5, 10 | — |
| SAME-R | kapton | 29 | 0, 1, 2, 8,1 | 1,38 – 1,48 |
| SAME-R | silicone | 22 | 0, 1, 2, 8, 8,1 | 1,30 – 1,36 |
| SAME-R | lampwick | 20 | 0, 2, 8, 8,1 | 1,25 – 1,28 |
| SAME-R | pyrell | 20 | 0, 1, 2, 8,1 | 1,22 – 1,23 |
| SAME-R | teflon | 18 | 0, 2, 8,1 | 1,25 – 1,45 |
