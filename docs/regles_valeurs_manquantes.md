# Valeurs manquantes : ce qui est vraiment vide et ce qui ne l'est pas

Audit des 12 tables PSI de `data/raw/psi/` (samedi 14 novembre 2026). Objectif : qu'une case vide dans `data/processed/` veuille toujours dire « la NASA ne l'a pas mesuré ou pas noté ». Elle ne doit pas cacher une valeur évidente d'après la conception de l'expérience, une valeur écrite ailleurs dans la table, ni un 0 qui tient lieu de « vide ».

Ces règles servent de spécification à `src/data/build_unified.py`.

## Les 7 cas

| Cas | Que faire | Marque dans `notes` / `qc_flags` |
|---|---|---|
| **A. Vraiment manquant** | laisser vide | — |
| **B. Sans objet** (n'a pas de sens vu l'issue de l'essai) | laisser vide, ne pas compter comme « trou » | `<col>:sans_objet` |
| **C. Implicite, documenté par la NASA** (conception de l'expérience) | remplir, avec la source et la page | `<col>:doc` ou `<col>:nominal` + source |
| **D. Écrit ailleurs dans la même table** (« same as 1-4 », ligne parente) | recopier | `<col>:recopie` |
| **E. Faux zéro** (0 utilisé à la place de « vide ») | vider | `<col>:zero_fictif` |
| **F. Incohérent** | garder la valeur et la signaler (la vider si physiquement impossible) | `<col>:incoherent` ou `<col>:a_verifier` |
| **G. Piège : l'« évident » est faux** | **ne pas remplir** | — |

Autres marques : `approx` (« ~6 »), `rampe` (« RAMPED », « 10, 5, 3 »), `sans_allumage_chaud` (ACME CFI-G). La liste fait foi dans `QC_REASONS` (`src/common/schema.py`), et `check_qc_flags()` vérifie une valeur.

## Colonnes du schéma absentes des tables sources

| Colonne | Expérience | Cas | Règle | Source |
|---|---|---|---|---|
| `gravity` | toutes | **C** | `micro` pour toutes les lignes. Saffire-II a en plus des colonnes 1g, qui deviennent des **lignes séparées** `gravity = 1g` | `investigation.json` : `projectType = "Microgravity Investigation"`, ISS / Cygnus |
| `fuel_type` | toutes | **C** | droplet (FLEX, CFI), gas (ACME, SPICE), solid (BASS, BASS-II, Saffire) | conception des expériences |
| `flow_cm_s` | FLEX, CFI | **G** | **ne pas mettre 0**. Beaucoup de gouttelettes étaient libres, avec une dérive lente, et certains essais ajoutaient un petit écoulement en déplaçant la gouttelette. Laisser vide ; noter « gouttelette libre ou sur fibre, écoulement non quantifié » | `PSI-69/investigation.json`, champ `approach` |
| `pressure_kpa` | BASS-II | **C** | 101,3 kPa nominal (1 atm, pression cabine dans la boîte à gants), marqué `nominal` | NASA/TM-20210011385, p. 11 (modèle de dilution, P = 1 atm) et p. 41 (« at 1 atm ») |
| `pressure_kpa` | BASS | **A → récupérable** | mesurée par essai (0,97–0,99 atm) dans `documents/PSI-26_…As Run_Test Matrix.xlsx`, colonne « pressure, atm » | PSI-26 |
| `pressure_kpa`, `o2_percent` | Saffire-III | **A → récupérable** | mesurés par des capteurs ; disponibles dans les fichiers de télémétrie `Raw Data` (non téléchargés). Vide en attendant | `PSI-100/investigation.json` |
| `material` | BASS-II (tiges « 1/4" clear rod », « black rod »…) | **C** | `PMMA` (coulé, noir ou transparent) | NASA/TM-20210011385, p. 47 (« rods of cast PMMA ») |
| `flow_direction` (table `families/solids` seulement) | BASS-II | **C** | présent dans l'annexe A du rapport (colonne « Opposed / Concurrent »), pas dans le CSV | NASA/TM-20210011385, pp. 103–113 |

## Vides dans les tables, par expérience

### FLEX (PSI-69)
- **Diamètre d'extinction vide (49 lignes)** : 27 lignes ont une issue Disruption ou Completion. La flamme ne s'est pas éteinte, donc c'est le cas **B (sans objet)**. Les 22 lignes en Extinction sont **A (manquant)**.
- **Diamètre d'extinction = 0 (8 lignes)** : toutes en Disruption ou Completion. Ce n'est pas une mesure, c'est **E (faux zéro) → vide**, avec la marque `sans_objet`.
- **Pression = 0 mmHg** (essai C11M201) : **E → vide**.
- **Burn time « ~6 »** : garder 6 avec la marque `approx`.
- Les compositions (O2 + N2 + CO2 + He) somment bien à 1 (0,98–1,01) : OK. Les 0 de CO2 et de He sont de **vrais zéros** (pas de suppresseur).

### CFI (PSI-39)
- **`Fiber` vide (9 lignes)** : **A**. Ne pas supposer « No ».
- Une ligne (Flex 1220) a O2 + N2 + He = 0,97 : **F**.
- Les pressions sont du texte avec unité (« 1 atm », « 1.25 atm ») : convertir.

### ACME CFI-G (PSI-159)
- **« Cool flame? » vide (171 / 179)** : **G**. Ce n'est **pas** « non » : des commentaires mentionnent des flammes froides sur des lignes où cette colonne est vide (« direct cool - no hot ignition »). Laisser vide.
- **« Hot ignition = No » ne veut pas dire « pas de flamme »** (piège **G**) : il peut y avoir une flamme froide sans allumage chaud.
- **Burn time = 0 ou vide quand Hot ignition = No** : la durée de flamme **chaude** est bien 0. Harmoniser en 0 avec la marque `sans_allumage_chaud`.
- Casse incohérente (`Yes` / `yes`, `Inverse` / `inverse`) : normaliser.
- Table « Inverse Flames » : 861 lignes entièrement vides en fin de fichier, à supprimer.

### ACME Flame Design (PSI-10)
- **XO2 final, p final, p mean vides (20 lignes)** : tous les essais du jour 13 (21301*). Rien n'a été noté ce jour-là : **A**.
- Valeurs `RAMPED` : condition variable pendant l'essai, donc pas une valeur unique. Laisser vide avec la marque `rampe`.

### SPICE (PSI-107)
- **Fuel Rate vide (12 lignes)** avec **HC Fuel Rate = 0** : perte de signal (« Ku LOS » dans les colonnes d'heure). Fuel Rate est **A**, et le 0 de HC Fuel Rate est un **faux zéro (E) → vide**.
- **Air Rate négatif** (−0,28 et −5,92 cm/s, 8 lignes) : physiquement impossible, donc **F → vide**, avec la marque `incoherent`.
- Combustibles « 75 % Propylene » : le diluant n'est pas précisé, **A**.

### BASS (PSI-26) et BASS-II (PSI-25)
- BASS-II, **« Fan display » vide (13 lignes)** : le débit est réglé au potentiomètre (colonne « Air display »). **A**, et sans gravité pour nous.
- BASS-II, **O2 final très bas** (B2 : 1,6 % ; P22a : 0,6 % ; T28a : 0,9 %) : chute impossible dans la boîte à gants. **F**, à ne pas utiliser comme O2 de l'essai (on utilise l'O2 initial).
- CO initial négatif (jusqu'à −3 ppm) : dérive du capteur, **F** (valeur gardée).
- BASS, 1 ligne sans numéro d'essai (8/3/2012) : à vérifier dans l'Excel « As Run » ; c'est sans doute une ligne de commentaire.

### Saffire I, II, III (PSI-98, 99, 100)
- **Lignes de visualisation d'écoulement** (`F1C1/F1C2`…) et **lignes « Note 1…4 »** de Saffire-II : ce ne sont pas des essais. À exclure. Le texte des notes va dans `notes` des lignes concernées.
- **Saffire-II, matériau vide pour 2-6 et 2-9** : **C**. 2-6 = tissu SIBAL et 2-9 = PMMA plat de 10 mm, d'après NTRS 20170001636 (Table 1, échantillons S6 et S9).
- **Saffire-II, longueur de propagation µg vide pour le silicone (2-1 à 2-4)** : la longueur brûlée est ~0, donc pas de propagation. **B (sans objet)**, pas un manquant.
- **Saffire-II, vitesse 1g vide pour 2-3** : longueur brûlée en 1g ~0, **B**.
- **Épaisseurs incohérentes (F)** :
  - Saffire-I indique « 0,37 cm » et Saffire-III « 0,33 cm » de SIBAL, alors que le document NASA donne **0,33 mm**. L'unité « cm » de ces tables est probablement fausse (un tissu de 3,7 mm n'est pas réaliste).
  - Saffire-II « 037 mm » = 0,37 mm (décimale manquante).
- **Saffire-I, longueur et largeur inversées ?** : la table donne longueur 40,6 cm et largeur 94 cm, alors que le document NASA donne 0,4 m × 0,95 m (large × long). Marque **F**.
- **Saffire-II, débit** : la table donne 20 cm/s pour tous les échantillons. Mais l'investigation PSI dit « 20 ou 30 cm/s selon le matériau », et le document de 2016 prévoyait 30 cm/s pour S6. On garde la table, avec la marque `a_verifier`.

### SAME (PSI-102) et SAME-R (PSI-101), hors modèle
- SAME, échantillons 5 à 8 : la source dit explicitement « same conditions as 1-4 ». **D** : chaque matériau a 4 conditions, à dupliquer depuis les lignes 1 à 4.
- SAME-R, lignes « a » (61a, 62a…) : mesure du **même** échantillon après vieillissement. Durée et temps de vieillissement primaire viennent de la ligne parente (61, 62…) : **D**.
- SAME-R, « Inlet velocity = 0 » (22 lignes) : vrais zéros (essais « No flow run »).

## Correspondance des issues vers `outcome`

Valeurs autorisées : `OUTCOMES` dans `src/common/schema.py`. Le texte d'origine est toujours recopié dans `notes`.

| Expérience | Source | → `outcome` |
|---|---|---|
| FLEX | `Test end` = Extinction / Disruption / Completion | `extinguished` / `disruption` / `completion` |
| ACME CFI-G | Hot ignition = yes + `SE` (auto-extinction) | `extinguished` |
| ACME CFI-G | Hot ignition = yes + `FT` (flamme encore présente quand on coupe le débit) | `burned` |
| ACME CFI-G | Hot ignition = flash (8 lignes, « A flash and gone ») | `extinguished`, avec la note « flash » |
| ACME CFI-G | Hot ignition = no, commentaire mentionnant une flamme froide (2 lignes) | `other`, avec la note « flamme froide sans allumage chaud » |
| ACME CFI-G | Hot ignition = no, sans commentaire (59 lignes) | `no_ignition` (allumage **chaud** absent ; flamme froide non vérifiée, cf. piège G) |
| ACME CFI-G | Hot ignition = no + `FT` (1 ligne, Normal Flames) | `no_ignition` + `outcome:a_verifier` |
| Saffire I–III | longueur brûlée > 0 ou « Complete » | `burned` |
| Saffire-II | longueur brûlée µg « ~ 0 » (silicone 2-1 à 2-4, Nomex de 2-7) | `other`, avec la note « pas de propagation » (on ne sait pas s'il y a eu un allumage bref) |
| BASS, BASS-II | observations en texte libre | vide tant que `data/processed/annotations/` n'est pas rempli ; ensuite issue annotée + `outcome:doc` + page |
| ACME Flame Design, SPICE, CFI, SAME, SAME-R | pas d'issue enregistrée dans la table | vide (**A**) |

## Ce que ça change pour le schéma

La colonne `qc_flags` (texte, ex. `pressure_kpa:nominal;material:doc`) est dans `src/common/schema.py`. Ainsi :
- le ML peut exclure ou pondérer les valeurs non mesurées ;
- l'Explorer peut afficher « valeur nominale » ou « valeur documentée » ;
- la règle « jamais de données inventées » reste vérifiable ligne par ligne.
