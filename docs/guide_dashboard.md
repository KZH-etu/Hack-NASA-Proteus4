# Guide du front-end

L'interface **HEPHAISTOS** (`app/frontend_hephaistos/index.html`) et le serveur qui la fait marcher (`src/api`) : comment lancer, ce que la page envoie et reçoit, ce qu'elle doit afficher.

## 1. Lancer

```bash
pip install -r requirements.txt
python -m src.rag.storage.download_chroma_release   # une fois : base du RAG (gh auth login requis)
python -m src.api                                   # puis ouvrir http://127.0.0.1:8000
```

Un seul serveur, sur le port 8000, fait tout :

```text
 navigateur ──GET  /                ──►  la page HEPHAISTOS
            ──POST /predict         ──►  modèles (src/models/model_gp)
            ──GET  /models/status   ──►  état des modèles et du RAG
            ──POST /ask             ──►  RAG (src/rag) + LLM de LM Studio
```

- **Préchauffage :** au démarrage, les trois modèles s'entraînent en arrière-plan (environ 50 s). La page affiche « chargement… » puis « prêt » grâce à `/models/status`.
- **Chat :** LM Studio doit tourner en local (`http://localhost:1234`), avec le modèle d'embedding du RAG et un modèle de chat (variable `RAG_CHAT_MODEL`). Sans lui, les prédictions marchent, mais pas le chat.
- **Options :** `--skip-sync` (ne vérifie pas la release de la base), `--no-rag` (prédictions seules), `--port 8010`.
- La page marche aussi ouverte en double-cliquant dessus (`file://`) : elle appelle alors `http://localhost:8000`.

## 2. Le formulaire

Le choix du **type** décide des champs affichés (déjà fait dans la page v5).

| Champ (`name`) | Gouttelette | Solide | Gaz | Unité / valeurs | Plage testée par la NASA |
|---|:-:|:-:|:-:|---|---|
| `fuel_type` | ✔ | ✔ | ✔ | `droplet`, `solid`, `gas` | — |
| `material` | ✔ | ✔ | ✔ | liste, voir dessous | — |
| `o2_percent` | ✔ | ✔ | ✔ | % d'O2 (21 = air) | gouttelette 12–34 · solide 14,2–22,2 · gaz 18–40 |
| `pressure_kpa` | ✔ | — | ✔ | kPa (101,3 = 1 atm) | gouttelette 70–309 · gaz 51–304 |
| `flow_cm_s` | — | ✔ | — | vitesse de l'air, cm/s | 0,5–53 |
| `d0_mm` | ✔ | — | — | diamètre de la goutte, mm (3 par défaut) | 1,1–4,7 |
| `co2_percent`, `he_percent` | ✔ | — | — | % de CO2 / d'hélium (0 par défaut) | 0–70 / 0–45 |
| `x_fuel` | — | — | ✔ | part de combustible dans le jet, 0 à 1 | 0,02–1 |
| `hc_rate_mg_s` | — | — | ✔ | débit de combustible, mg/s | 0,1–3,2 |

| Type | `material` | Texte affiché |
|---|---|---|
| Gouttelette | `heptane`, `methanol` | Heptane, Méthanol |
| Solide | `pmma_flat`, `pmma_rod_sphere`, `fabric_other` | PMMA (plaque), PMMA (tige ou sphère), Tissu / autre |
| Gaz | `ethane`, `propane`, `n-butane` | Éthane, Propane, n-Butane |

Une valeur hors de la plage testée n'est pas bloquée : la réponse contient une alerte d'extrapolation. Les modèles ne couvrent que la **microgravité**.

## 3. `POST /predict`

**Envoi** (à plat, champs du type choisi ; `model` est accepté et ignoré) :

```json
{"fuel_type": "droplet", "material": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3, "co2_percent": 0, "he_percent": 0}
```

**Réponse** : la sortie du modèle, plus `sources`. Exemple réel (habitat lunaire) :

```json
{
  "experiment": "FLEX",
  "p_extinction": 0.022,
  "p_extinction_interval_90": [0.008, 0.307],
  "burning_rate_k_mm2_s": 0.764,
  "burning_rate_k_std": 0.07,
  "burning_rate_k_interval_95": [0.587, 0.941],
  "near_data": true,
  "warnings": ["pressure_kpa = 55 hors de la plage mesurée par FLEX (70.17 à 309.29) : extrapolation ; ..."],
  "n_training_tests": 261,
  "sources": [{"experiment": "FLEX", "test_id": "39", "psi_id": "PSI-69", "material": "heptane",
               "o2_percent": 34.0, "pressure_kpa": 71.3, "outcome": "disruption",
               "url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-69"}]
}
```

Champs à afficher selon le type :

| Type | Chiffre principal | Fourchette | Autres |
|---|---|---|---|
| Gouttelette | `p_extinction` : probabilité que la flamme s'éteigne d'elle-même | `p_extinction_interval_90` | `burning_rate_k_mm2_s` + `burning_rate_k_interval_95` (mm²/s), `near_data` |
| Solide | `p_flame_sustained` : probabilité que la flamme tienne | `p_flame_sustained_interval_90` | `n_observations_same_group` |
| Gaz | `p_hot_ignition` : probabilité d'allumage, et `p_self_extinction_if_ignited` : si elle s'allume, probabilité qu'elle s'éteigne seule | `p_hot_ignition_interval_90`, `p_self_extinction_interval_90` | `p_hot_ignition_reliability`, `p_self_extinction_reliability` |
| Tous | — | — | `warnings`, `sources`, `n_training_tests` |

- **Pas de donnée :** pour les solides au-dessus de 22,2 % d'O2, `p_flame_sustained` vaut `null`. Afficher « Pas de donnée NASA dans ces conditions », jamais 0 % ni 50 %.
- **Erreurs :** code 422 avec un message lisible dans `detail` (champ manquant, combustible non couvert). La page l'affiche déjà.

## 4. Ce qu'il faut afficher

1. Le chiffre en grand, avec sa fourchette juste en dessous : « 2,2 % (entre 0,8 % et 30,7 %) ».
2. La fiabilité :

   | Type | Fiabilité | Phrase |
   |---|---|---|
   | Gouttelette | bonne | « Modèle validé sur 261 essais FLEX. » |
   | Gaz | moyenne (auto-extinction) / faible (allumage) | « Modèle validé sur 177 essais ACME ; l'allumage est difficile à prévoir. » |
   | Solide | faible | « Indication seulement : les données ne suffisent pas à prédire de façon fiable. » |

3. Les `warnings`, chacun tel quel dans un encadré.
4. Les sources : une ligne par essai, avec son lien. Exemple : « **FLEX (PSI-69) essai 39** · heptane · O2 34 % · 71,3 kPa · issue : goutte éclatée ».

| `outcome` | Texte |
|---|---|
| `extinguished` | extinction |
| `burned` | a brûlé |
| `completion` | brûlée jusqu'au bout |
| `disruption` | goutte éclatée |
| `no_ignition` | ne s'est pas allumée |

S'il n'y a aucune source : « Aucun test de la NASA n'a été effectué sur une situation similaire ».

## 5. `POST /ask` (chat)

```text
envoi   : {"question": "Pourquoi une flamme s'éteint-elle en microgravité ?",
           "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
réponse : {"answer": "... par rayonnement [1] ...",
           "sources": [{"title": "Detailed Results from the Flame Extinguishment Experiment (FLEX) ...",
                        "ntrs_id": "20150023456", "page": 1, "url": "https://ntrs.nasa.gov/citations/20150023456",
                        "year": 2015, "source_type": "ntrs"}]}
```

- La réponse cite ses sources par numéro : `[1]` renvoie à la 1re source de la liste. Afficher les sources numérotées dans cet ordre.
- **LLM arrêté** (mais LM Studio joignable pour la recherche) : `answer` le signale et `sources` contient quand même les passages trouvés.
- **LM Studio injoignable ou base absente :** code 503 avec la raison dans `detail`.
- Questions de démo : « Pourquoi une flamme s'éteint-elle plus facilement en microgravité ? », « Qu'a montré l'expérience FLEX (Flame Extinguishment Experiment) ? », « Quels matériaux brûlent à 34 % d'O2 ? ».

## 6. `GET /models/status`

```json
{"models": {"droplet": {"status": "ready"}, "gas": {"status": "loading"}, "solid": {"status": "pending"}},
 "rag": {"status": "ready", "chunks": 21374}}
```

`status` vaut `pending`, `loading`, `ready` ou `error` (avec `error`). Le RAG peut aussi valoir `disabled` (`--no-rag`).

## 7. Scénarios de démo

| Bouton | Envoi |
|---|---|
| Cabine ISS | gouttelette, heptane, 21 % O2, 101,3 kPa, 3 mm |
| Habitat lunaire | gouttelette, heptane, 34 % O2, 55 kPa, 3 mm |
| Atmosphère pauvre en O2 | gouttelette, heptane, 15 % O2, 101,3 kPa, 3 mm |
| Matériau de cabine | solide, PMMA plaque, 21 % O2, 10 cm/s |

L'histoire à raconter : pour l'habitat lunaire, la NASA n'a aucun essai FLEX sous 70 kPa. Le modèle le signale (alerte d'extrapolation, fourchette large) : c'est là qu'il faudrait tester sur l'ISS (`recommend_next_experiment` dans `model_gp`, pas encore exposé par l'API).

## 8. Règles

1. Toujours la fourchette à côté du chiffre.
2. Toujours les alertes (`warnings`).
3. Jamais de chiffre inventé : une valeur absente s'affiche « pas de donnée ».
4. Toujours la source de chaque essai ou document montré.
5. **Logo :** le logo NASA ne doit pas laisser croire à un soutien officiel (règles du Space Apps Challenge et charte NASA). Le retirer et écrire plutôt « Données : NASA Physical Sciences Informatics (PSI) et NTRS ».
