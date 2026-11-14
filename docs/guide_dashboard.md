# Guide du front-end

Tout ce qu'il faut pour que l'interface **HEPHAISTOS** (`app/frontend_hephaistos/HEPHAISTOS_interface_v2.html`) affiche de vraies prédictions et de vraies réponses : quels champs proposer, ce qu'on envoie, ce qu'on reçoit, ce qu'il faut afficher et écrire.

## 1. Comment ça marche

```text
 Page HTML (HEPHAISTOS)  ──POST /predict──►  API Python  ──►  modèles (src/models/model_gp)
                         ──POST /ask──────►  (port 8000) ──►  RAG (src/rag)
```

- La page appelle deux adresses, déjà prévues dans son `CONFIG` : `PREDICT_URL = http://localhost:8000/predict` et `CHAT_URL = http://localhost:8000/ask`.
- Tant que `USE_DEMO: true`, la page affiche des réponses factices marquées « DEMO ». Il faut passer à `false` quand l'API tourne.
- **L'API Python reste à écrire** : c'est un petit fichier qui traduit le JSON de la page vers les modèles (§ 9). Le modèle utilisé est **`model_gp`**, le meilleur d'après `src/models/comparaison.md`.

## 2. Le formulaire de prédiction

Le choix du **type** décide des champs à montrer.

| Champ (`name`) | Gouttelette | Solide | Gaz | Unité / valeurs | Plage testée par la NASA |
|---|:-:|:-:|:-:|---|---|
| `fuel_type` | ✔ | ✔ | ✔ | `droplet`, `solid`, `gas` | — |
| `material` | ✔ | ✔ | ✔ | **liste déroulante**, voir dessous | — |
| `o2_percent` | ✔ | ✔ | ✔ | % d'O2 (21 = air) | gouttelette 12–34 · solide 14,2–22,2 · gaz 18–40 |
| `pressure_kpa` | ✔ | — | ✔ | kPa (101,3 = 1 atm) | gouttelette 70–309 · gaz 51–304 |
| `flow_cm_s` | — | ✔ | — | vitesse de l'air, cm/s | 0,5–53 |
| `d0_mm` | ✔ | — | — | diamètre de la goutte, mm (3 par défaut) | 1,1–4,7 |
| `co2_percent` | ✔ | — | — | % de CO2 (0 par défaut) | 0–70 |
| `he_percent` | ✔ | — | — | % d'hélium (0 par défaut) | 0–45 |
| `x_fuel` | — | — | ✔ | part de combustible dans le jet, 0 à 1 | 0,02–1 |
| `hc_rate_mg_s` | — | — | ✔ | débit de combustible, mg/s | 0,1–3,2 |

Valeurs de `material` (remplacer le champ texte par une liste) :

| Type | Valeur envoyée | Texte affiché |
|---|---|---|
| Gouttelette | `heptane`, `methanol` | Heptane, Méthanol |
| Solide | `pmma_flat`, `pmma_rod_sphere`, `fabric_other` | PMMA (plaque), PMMA (tige ou sphère), Tissu / autre |
| Gaz | `ethane`, `propane`, `n-butane` | Éthane, Propane, n-Butane |

**Gravité :** les modèles ne connaissent que la **microgravité**. Retirer « 1 g » du formulaire, ou le garder grisé avec la mention « non couvert par les données ».

Une valeur hors de la plage testée n'est pas bloquée : la réponse contiendra une alerte d'extrapolation, à afficher.

## 3. Ce que la page envoie : `POST /predict`

Une ligne JSON avec les champs du type choisi :

```json
{"fuel_type": "droplet", "material": "heptane", "o2_percent": 21, "pressure_kpa": 101.3, "d0_mm": 3.0, "co2_percent": 0, "he_percent": 0}
{"fuel_type": "solid", "material": "pmma_flat", "o2_percent": 21, "flow_cm_s": 10}
{"fuel_type": "gas", "material": "propane", "o2_percent": 34, "pressure_kpa": 55, "x_fuel": 0.3, "hc_rate_mg_s": 1.0}
```

## 4. Ce que la page reçoit

```json
{
  "probability": 0.59,
  "interval": [0.36, 0.94],
  "uncertainty": 0.29,
  "label": "Probabilité que la flamme continue de brûler",
  "reliability": "bonne",
  "warnings": [],
  "details": [
    {"label": "Vitesse de combustion", "value": 0.54, "interval": [0.38, 0.70], "unit": "mm²/s"}
  ],
  "sources": [
    {"experiment": "FLEX", "psi_id": "PSI-69", "test_id": "35", "material": "heptane",
     "o2_percent": 21.0, "pressure_kpa": 102.4, "outcome": "extinguished",
     "url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69"}
  ],
  "recommendation": null
}
```

| Champ | Contenu | Toujours présent ? |
|---|---|---|
| `probability` | entre 0 et 1 | oui |
| `interval` | `[bas, haut]` : fourchette à 90 % | oui, ou `null` |
| `uncertainty` | moitié de la largeur de la fourchette (déjà utilisée par la page : « ± X points ») | oui |
| `label` | ce que mesure la probabilité, à afficher comme titre | oui |
| `reliability` | `bonne`, `moyenne` ou `faible` | oui |
| `warnings` | phrases à afficher telles quelles | oui (liste vide possible) |
| `details` | autres résultats chiffrés (vitesse de combustion pour les gouttelettes) | non |
| `sources` | essais NASA les plus proches ; `[]` s'il n'y en a pas | oui |
| `recommendation` | prochaine expérience conseillée (§ 7) | non |

**Pas de donnée** (solides au-dessus de 22,2 % d'O2) : `probability` et `interval` valent `null`, et `warnings` l'explique. Afficher alors « Pas de donnée NASA dans ces conditions », **jamais 0 % ni 50 %**.

## 5. Ce qu'il faut afficher et écrire

**Le chiffre principal**, partout la même question : *la flamme continue-t-elle de brûler ?* (un chiffre haut = danger).

| Type | `label` | D'où vient le chiffre |
|---|---|---|
| Gouttelette | « Probabilité que la flamme continue de brûler » | 1 − probabilité d'extinction |
| Solide | « Probabilité que la flamme se maintienne » | probabilité que la flamme tienne |
| Gaz | « Probabilité qu'une flamme s'allume et se maintienne » | allumage × (1 − auto-extinction) |

**La zone de résultat**, dans cet ordre :
1. le `label` en titre (à la place de « Probabilité d'incendie ») ;
2. le chiffre en grand : **59 %** ;
3. la fourchette sous le chiffre : « entre 36 % et 94 % ». C'est plus juste que « ± X points » : la fourchette n'est pas symétrique ;
4. un badge de fiabilité : vert = bonne, orange = moyenne, rouge = faible ;
5. une ligne par `details` : « Vitesse de combustion : 0,54 mm²/s (entre 0,38 et 0,70) » ;
6. les `warnings`, chacun dans un encadré orange ;
7. le rappel des conditions (déjà présent dans la page).

**Fiabilité de chaque type** (validation sur des jours d'essai jamais vus par le modèle) :

| Type | Fiabilité | Phrase à écrire |
|---|---|---|
| Gouttelette | bonne | « Modèle validé sur 261 essais FLEX. » |
| Gaz | moyenne | « Modèle validé sur 177 essais ACME ; l'allumage est difficile à prévoir. » |
| Solide | faible | « Indication seulement : les données ne suffisent pas à prédire de façon fiable. » |

**Les sources**, une par essai :
> **FLEX (PSI-69) essai 35** · heptane · O2 21 % · 102,4 kPa · issue : extinction · [lien]

La page sait déjà les afficher (`renderSource`). Il suffit d'ajouter `outcome` :

| `outcome` | Texte |
|---|---|
| `extinguished` | extinction |
| `burned` | a brûlé |
| `completion` | brûlée jusqu'au bout |
| `disruption` | goutte éclatée |
| `no_ignition` | ne s'est pas allumée |

S'il n'y a aucune source, la page affiche déjà : « Aucun test de la NASA n'a été effectué sur une situation similaire ».

## 6. Le chat : `POST /ask`

Format déjà prévu par la page :

```text
envoi   : {"question": "Pourquoi une flamme s'éteint-elle en microgravité ?",
           "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
réponse : {"answer": "En microgravité, il n'y a pas de convection ...",
           "sources": [{"title": "Detailed Results from the Flame Extinguishment Experiment (FLEX)",
                        "ntrs_id": "20150023456", "page": 1, "url": "https://ntrs.nasa.gov/citations/20150023456"}]}
```

- Toujours afficher les sources sous la réponse. Si `sources` est vide, écrire : « Je n'ai pas trouvé de document NASA sur ce point. »
- **État du RAG :** les 399 documents NASA sont téléchargés (`data/raw/ntrs/`) et l'indexation est en cours (`src/rag`). La fonction de réponse n'existe pas encore : garder `USE_DEMO` pour le chat d'ici là.
- Questions de démo : « Pourquoi une flamme s'éteint-elle plus facilement en microgravité ? », « Qu'a montré l'expérience FLEX (Flame Extinguishment Experiment) ? », « Quels matériaux brûlent à 34 % d'O2 ? ».

## 7. Prochaine expérience (à ajouter sous la prédiction)

C'est le point fort du projet pour le jury : pour un scénario donné, quelle expérience faire sur l'ISS ? Disponible pour les gouttelettes et les solides. Champ `recommendation` de la réponse :

```json
{"conditions": {"o2_percent": 34, "pressure_kpa": 50, "d0_mm": 3.0},
 "why": "aucun essai FLEX sous 70 kPa ; essai réel le plus proche loin (n° 39 : 34 % O2, 71,3 kPa) ; modèle incertain"}
```

Afficher un encadré « Expérience recommandée sur l'ISS » : les conditions, puis la phrase `why` telle quelle.

## 8. Scénarios de démo (boutons de préremplissage)

| Bouton | Envoi |
|---|---|
| Cabine ISS | gouttelette, heptane, 21 % O2, 101,3 kPa, 3 mm |
| Habitat lunaire | gouttelette, heptane, 34 % O2, 55 kPa, 3 mm |
| Atmosphère pauvre en O2 | gouttelette, heptane, 15 % O2, 101,3 kPa, 3 mm |
| Matériau de cabine | solide, PMMA plaque, 21 % O2, 10 cm/s |

L'histoire à raconter : pour l'habitat lunaire, la NASA n'a aucun essai sous 70 kPa. Le modèle le signale (alerte), et la recommandation propose justement d'aller tester là.

## 9. Pour celui qui écrit l'API

Un fichier `src/api.py` (FastAPI, par exemple) avec deux routes, qui appellent :

| Type | Fonction | Champs utilisés dans le résultat |
|---|---|---|
| Gouttelette | `gp.flex.predict({"fuel": material, "o2_percent", "pressure_kpa", "d0_mm", "co2_percent", "he_percent"})` | `p_extinction`, `p_extinction_interval_90`, `burning_rate_k_mm2_s`, `burning_rate_k_interval_95`, `warnings` |
| Solide | `gp.solids.predict({"material", "o2_percent", "flow_cm_s"})` | `p_flame_sustained`, `p_flame_sustained_interval_90`, `warnings` |
| Gaz | `gp.gas.predict({"fuel": material, "o2_percent", "pressure_kpa", "x_fuel", "hc_rate_mg_s"})` | `p_hot_ignition`, `p_self_extinction_if_ignited` (+ intervalles), `nearest_tests`, `warnings` |
| Recommandation | `gp.recommend_next_experiment(...)` | `recommendations[0]` (`conditions`, `why`), `nearest_flex_tests` / `nearest_observations` (sources) |

- `gp = load("model_gp")` (`from src.models import load`), chargé **une seule fois** au démarrage : le premier appel prend environ 30 s par type, les suivants sont instantanés.
- Les liens des sources : colonnes `psi_url` et `doi_url` de `data/processed/experiments_all.csv`, retrouvées par `experiment` + `test_id`.
- Autoriser les appels depuis la page (CORS), puisque la page est ouverte comme fichier local.

## 10. Règles

1. **Toujours** la fourchette à côté du chiffre.
2. **Toujours** les alertes (`warnings`).
3. **Jamais** de chiffre inventé : une valeur absente s'affiche « pas de donnée ».
4. **Toujours** la source de chaque essai montré.
5. **Logo :** le logo NASA (`logo-nasa-sur-fond-blanc.PNG`) ne doit pas laisser croire à un soutien officiel (règles du Space Apps Challenge et charte NASA). Le retirer et écrire plutôt « Données : NASA Physical Sciences Informatics (PSI) et NTRS ».
