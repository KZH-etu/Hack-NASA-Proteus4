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

Autres marques : `deduit` (issue écrite en toutes lettres dans une autre colonne de la même ligne), `approx` (« ~6 »), `rampe` (« RAMP », « RAMPED », « 10, 5, 3 »), `sans_allumage_chaud` (ACME CFI-G), `qualitatif` (texte comme « LOW O2 » à la place d'un nombre, recopié dans les commentaires), `erreur_excel` (« #DIV/0! », « #VALUE! »). La liste fait foi dans `QC_REASONS` (`src/common/schema.py`), et `check_qc_flags()` vérifie une valeur.

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
Référence des colonnes : NASA/TP-2015-216046 (NTRS 20150023456), Table IX, p. 19. Chiffres vérifiés par `build_unified.py` (voir `data/processed/qc_report.md`).
- **Diamètre d'extinction : « – », vide ou 0 (85 lignes)**. Le rapport dit que « – » signifie « pas d'extinction (combustion complète ou éclatement) ».
  - 58 lignes en Disruption ou Completion → **B (sans objet)**, marque `d_ext_mm:sans_objet` ; les 8 qui valaient 0 ont en plus `zero_fictif`.
  - 27 lignes en Extinction sans diamètre → **A (manquant)** : l'investigation précise que certains diamètres d'extinction étaient trop petits pour être mesurés.
- **Diamètre initial « – » ou vide (12 lignes)** : **A**.
- **Pression = 0 mmHg** (essai C11M201) : **E → vide**.
- **Burn time « ~6 » et « ~9 »** : 6 et 9 avec la marque `approx`.
- **« Burning rate; mm »** : c'est la constante K en **mm²/s** (le rapport le précise), d'où `burning_rate_mm2_s`.
- **Dates** au format `3/5/2009` et `10/24/09` : les deux formats sont gérés.
- **Identifiant CIR `193F001` en double** (essais 70 et 73) : marque `a_verifier` ; la clé d'essai est `FLEX Test #`, qui est unique.
- Les compositions (O2 + N2 + CO2 + He) somment bien à 1 (0,98–1,01). Les 0 de CO2 et de He sont de **vrais zéros** (pas de suppresseur).
- **Vitesse de propagation** : notion des solides, sans objet pour une gouttelette → `spread_rate_mm_s:sans_objet` dans la table unifiée.

### CFI (PSI-39)
- **`Fiber` vide (9 lignes)** : **A**. Ne pas supposer « No ».
- Une ligne (Flex 1220) a O2 + N2 + He = 0,97 : **F**.
- Les pressions sont du texte avec unité (« 1 atm », « 1.25 atm ») : convertir.

### Flammes gazeuses : conventions communes (`families/gas.parquet`)
Chiffres vérifiés par `build_unified.py`. Dans `qc_report.md`, chaque case vide est classée : sans objet, faux zéro vidé, autre marque, colonne absente du fichier source (ex. buse SPICE pour ACME), ou vraiment manquante.
- **`flame_type`** : `normal` (combustible dans le jet, O2 dans la chambre), `inverse` (O2 dans le jet, combustible dans la chambre), `coflow` (SPICE).
- **`o2_percent` dans la table unifiée = O2 côté oxydant.** Pour les flammes inverses ACME, c'est l'O2 du jet du brûleur (jusqu'à 85 %), pas une atmosphère de cabine. Il faut filtrer sur `flame_type` avant de comparer à un scénario d'habitat.
- **`flow_cm_s`** : `sans_objet` pour ACME (brûleur sphérique en chambre calme, débits en mg/s dans `families/gas`) ; co-courant d'air pour SPICE.
- **`spread_rate_mm_s` et `burning_rate`** : `sans_objet` pour les gaz.
- **Date ACME** : déduite du code d'essai `AAJJJ…` (année + jour de l'année), convention donnée dans la table ACME s-Flame (PSI-23). `session` = ce jour d'essai.

### ACME CFI-G (PSI-159)
- **« Cool flame? » vide (171 / 179)** : **G**. Ce n'est **pas** « non ». `cool_flame` est rempli seulement si la colonne ou un commentaire est explicite (« Cool flame! », « direct cool », « No cool flame detected ») : 9 oui, 2 non, 322 vides.
- **« Hot ignition = No » ne veut pas dire « pas de flamme »** (piège **G**) : 2 essais ont une flamme froide sans allumage chaud.
- **Burn time quand Hot ignition = No (62 lignes)** : la durée de flamme **chaude** est 0 (4 étaient vides) → 0 + `sans_allumage_chaud`.
- **Pression** : colonne « approx p (bar) » → kPa avec la marque `approx`.
- **Xf = 0 et mHC = 0** (essais 21125A4 et 21125H3, sans allumage) : `x_fuel:a_verifier`.
- **Température du brûleur** : convertie depuis la colonne en °C (+ 273,15). La colonne K de la table inverse (avec deux `#VALUE!` d'Excel) n'est pas utilisée. « - » → vide.
- **Tad et Zst = `#DIV/0!`** (2 flammes normales) : vide + `erreur_excel`.
- Casse incohérente (`Yes` / `yes`, `Inverse` / `inverse`, `Blue` / `blue`) : normalisée.
- Table « Inverse Flames » : 861 lignes entièrement vides en fin de fichier, ignorées.

### ACME Flame Design (PSI-10)
- **Pas d'issue dans la table** (le but était les limites de suie et d'extinction) : `outcome` vide, **A**.
- **XO2 final, p final, p mean vides (20 lignes)** : tous les essais du jour 13 (21301*). Rien n'a été noté ce jour-là : **A**.
- **`RAMP` / `RAMPED`** (60 flammes normales, 9 inverses) : condition variable pendant l'essai → vide + `rampe`.
- **`LOW O2`** (2 flammes inverses) : texte qualitatif à la place d'un nombre → vide + `qualitatif`, texte recopié dans `comments`.
- Flammes inverses : le combustible de la chambre est l'éthylène (colonnes « XC2H4 »).

### SPICE (PSI-107)
- **34 copies exactes** (mêmes heures, mêmes débits que la ligne précédente) → écartées dans `skipped_rows.csv` (`copie_exacte`). Reste 435 points de mesure.
- **Pas d'identifiant d'essai** : `test_id = GMT<jour>-L<ligne>` ; `session` = jour + heure d'allumage (une flamme). Pas d'année dans la table → `test_date` vide (**A**).
- **O2 et pression : C (nominal)**. Co-courant d'air de la cabine dans la MSG → O2 21 % et 1 atm, marqués `nominal` (pression : NASA/TM-20210011385 p. 11, même boîte à gants).
- **Combustible pur** quand le libellé n'a pas de pourcentage → `x_fuel = 1`. « 75 % Propylene » → `x_fuel = 0,75`, **diluant non précisé (A)**.
- **Fuel Rate vide (12 lignes)** avec **HC Fuel Rate = 0** : perte de signal (« Ku LOS »). Le 0 est un **faux zéro (E) → vide** (7 lignes après retrait des copies).
- **Air Rate négatif** (−0,28 et −5,92 cm/s, 8 lignes) : **F → vide**, marque `incoherent`.
- Pas d'issue dans la table (point de fumée étudié) : `outcome` vide, **A**.

### Solides : conventions communes (`families/solids.parquet`)
Chiffres vérifiés par `build_unified.py`.
- **Matériau et géométrie** sont lus dans la description d'échantillon (« 1/4" black rod », « 2 cm 0.1 mm PMMA film », « SIBAL 2 cm »…). Diamètres des tiges : 1/4" = 6,35 mm, 3/8" = 9,525 mm, 1/2" = 12,7 mm.
- **PMMA implicite** (tiges, sphères, sections sphériques, films sans le mot « PMMA ») : `material:doc` (BASS 30 lignes, BASS-II 57) ; sources : NASA/TM-20210011385 p. 47 et plans BASS (PSI-26, Engineering Documents). Une « candle » sans précision garde un matériau vide (3 lignes, **A**).
- **Dimensions sans objet selon la géométrie** : pas de largeur ni d'épaisseur pour une tige, une sphère ou une bougie ; pas de diamètre pour un échantillon plat → `sans_objet`.
- **Vitesse d'air** (« Air display » BASS / BASS-II, anémomètre en cm/s : NASA/TM-20210011385 p. 21, et observations BASS « at 10 cm/s ») :
  - une seule valeur → `flow_cm_s` ;
  - plusieurs valeurs (« 10, 5, 3 ») → `flow_cm_s` vide + `rampe`, avec `flow_min_cm_s` / `flow_max_cm_s` ;
  - une valeur accompagnée de texte (« 3 ign », « 10 max ») → `qualitatif` ;
  - les réglages du potentiomètre ne sont pas des vitesses : « 5 3 pot 0.4 », « 3 0.5 pot 0.4 pot », « 5 pots 0.4 0.36 0.32 » (tous les nombres après « pots ») sont ignorés (texte brut dans `flow_raw`) ;
  - « <1 » compte pour 1 dans `flow_min_cm_s`, avec la marque `approx`.
- **`spread_rate_mm_s` et `burning_rate`** : les vitesses de propagation BASS / BASS-II ne sont que dans les figures des rapports (**A**) ; `burning_rate` est `sans_objet`.

### BASS (PSI-26)
- La table PSI (essais) est enrichie par la matrice `As Run` (O2, pression mesurée 0,97–1,01 atm, CO2, vitesse d'air, observations). **Jointure sur (n° As Run, n° d'essai)** : les 121 essais sont appariés sans ambiguïté (le n° As Run seul est en double pour 5 essais, et les dates diffèrent de format, ex. « 6/29/`12 »).
- `test_id` = `AR<n° As Run>-T<n° d'essai>`.
- **1 ligne « SOOT Cleaning »** sans numéro d'essai : pas un essai → `skipped_rows.csv`.
- **Issue** : « ext » ou « blowoff » écrit dans les colonnes de débit → `extinguished` + `outcome:deduit` (2 essais) ; sinon seulement dans les observations en texte libre → vide tant que `annotations/bass_outcomes.csv` n'est pas rempli.

### BASS-II (PSI-25)
- **Pression** : 101,325 kPa `nominal` (rapport p. 11 et 41).
- **« Fan display » vide (13 lignes)** : réglage au potentiomètre, **A** sans conséquence (la vitesse est dans « Air display »).
- **O2 final très bas** (B2 : 1,6 % ; P22a : 0,6 % ; T28a : 0,9 %) : `x_o2_final:incoherent`. Utiliser l'O2 initial.
- **CO négatif** (jusqu'à −3 ppm) : dérive du capteur, valeur gardée + `incoherent`.
- **Issue déduite (23 essais)** : « ext », « extinguished » ou « blowoff » écrit dans « Air display » ou « Fan display » (ex. « 5 3 2 ext », « 10 blowoff ») → `extinguished` + `outcome:deduit`. L'absence de ces mots ne veut **pas** dire que la flamme a tenu (vide). Idée reprise de Krypton-N.
- **Issue et sens de l'écoulement complets** : annexe A du rapport (pp. 103–113, texte libre) → à saisir dans `annotations/bass_outcomes.csv` (colonnes `outcome`, `flow_direction`, `source_page`). Une annotation remplace l'issue déduite (marque `doc`).

### Saffire I, II, III (PSI-98, 99, 100)
- **Lignes de visualisation d'écoulement** (`F1C1/F1C2`…) et **lignes « Note 1…4 »** : écartées (`skipped_rows.csv`) ; le texte des notes est recopié dans `observations` / `notes` des échantillons qui y renvoient (la Note 1, « O2 déduit de la production de CO2 », concerne la colonne O2 de tous les essais en vol de Saffire-II).
- **Saffire-II : chaque échantillon donne 2 lignes** : vol (`gravity = micro`) et essai de comparaison au sol (`test_id` + `-1g`, `gravity = 1g`). Pour le sol, O2, débit et pression ne sont pas donnés : **A**.
- **Matériau vide pour 2-6 et 2-9** : **C**. 2-6 = SIBAL et 2-9 = PMMA plat de 10 mm, d'après NTRS 20170001636 (Table 1) ; 2-8 = PMMA « structuré » (`geometry:doc`).
- **Longueur brûlée « Complete »** : `burn_complete = True` et longueur brûlée = longueur de l'échantillon (`recopie`). Sinon, `burn_complete` est déduit en comparant les deux longueurs de la même ligne.
- **Longueur brûlée « ~ 0 »** (silicone, Nomex) : 0 + `approx`, issue `other` (pas de propagation) ; vitesse de propagation `sans_objet`. « n/a (Nomex) » → `sans_objet`.
- **Vitesse en 1g « Acceleratory »** : pas de vitesse unique → vide + `qualitatif`, `spread_mode = acceleratory`. « Note 4 » (flamme ancrée à la base, régression 0,01–0,04 mm/s) → vide + `qualitatif`.
- **O2 en fourchette** (« 21.5 - 21.7 », « 22.1 to 22.0 ») : milieu de la fourchette + `approx`.
- **Épaisseurs incohérentes (F)** :
  - Saffire-I indique « 0,37 cm » et Saffire-III « 0,33 cm » de SIBAL, alors que le document NASA donne **0,33 mm**. Valeur de la table gardée (3,7 et 3,3 mm) + `incoherent` ; un tissu de 3,7 mm n'est pas réaliste.
  - Saffire-II « 037 mm » = 0,37 mm (décimale manquante) + `a_verifier`.
- **Saffire-I, longueur et largeur inversées ?** : 40,6 cm × 94 cm dans la table, 0,4 m (large) × 0,95 m (long) dans le document NASA → `a_verifier`.
- **Saffire-II, débit** : 20 cm/s partout dans la table, alors que l'investigation PSI dit « 20 ou 30 cm/s selon le matériau » et que le document de 2016 prévoyait 30 cm/s pour S6 → `a_verifier`.
- **Saffire-III** : O2 et pression mesurés par des capteurs mais seulement dans la télémétrie (non téléchargée) → vides. Pas de résultat de combustion dans la table → `outcome` vide.
- Issue : longueur brûlée > 0 ou « Complete » → `burned` ; ~ 0 ou cas mixte PMMA / Nomex (2-7) → `other` ; Saffire-I : durée de combustion > 0 → `burned`.

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
