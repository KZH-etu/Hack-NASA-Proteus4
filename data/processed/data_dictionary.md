# Dictionnaire des données — data/processed

Généré par `python -m src.data.build_unified` à partir du code. Ne pas éditer à la main.

## unified.parquet (table catalogue)

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `experiment` | string |  | Nom de l'expérience |
| `psi_id` | string |  | Investigation PSI |
| `doi` | string |  | DOI de l'investigation PSI |
| `test_id` | string |  | Identifiant de l'essai dans la source |
| `fuel_type` | string |  | Famille : solid, droplet, gas |
| `material` | string |  | Combustible ou matériau (minuscules) |
| `geometry` | string |  | Géométrie de l'échantillon |
| `o2_percent` | Float64 | % | O2 initial côté oxydant, en % molaire (flammes inverses ACME : O2 du jet du brûleur) |
| `pressure_kpa` | Float64 | kPa | Pression ambiante |
| `flow_cm_s` | Float64 | cm/s | Vitesse d'écoulement imposé (SPICE : co-courant d'air) ; vide si non quantifiée (FLEX : gouttelettes libres ou à dérive lente) ou sans objet (ACME : brûleur sphérique en chambre calme) |
| `gravity` | string |  | micro / 1g ; ne jamais mélanger les deux dans un entraînement |
| `outcome` | string |  | Issue normalisée : burned, extinguished, no_ignition, disruption, completion, other (texte d'origine dans notes) |
| `spread_rate_mm_s` | Float64 | mm/s | Vitesse de propagation de flamme |
| `burning_rate` | Float64 | mm²/s | Constante de combustion K des gouttelettes (FLEX) ; sans objet pour les gaz et les solides |
| `source_doc` | string |  | Fichier PSI ou document NASA d'où vient la ligne |
| `source_page` | string |  | Ligne du fichier PSI ou page du document |
| `notes` | string |  | Texte d'origine utile (issue brute, diluant, unités) |
| `qc_flags` | string |  | Marques qualité « colonne:motif;... » |

## families/droplets.parquet

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `experiment` | string |  | Nom de l'expérience (FLEX) |
| `psi_id` | string |  | Investigation PSI |
| `test_id` | string |  | Numéro d'essai de l'équipe scientifique (« FLEX Test # ») |
| `cir_identifier` | string |  | Identifiant de l'équipe ingénierie CIR (« FLEX Identifier »), pas toujours unique |
| `test_date` | string | AAAA-MM-JJ | Date de l'essai |
| `test_time_gmt` | string | HH:MM:SS | Heure de l'essai (GMT) |
| `session` | string |  | Groupe pour la validation croisée : jour d'essai (les essais d'un même jour partagent l'atmosphère de la chambre) |
| `fuel` | string |  | Combustible (heptane, methanol) |
| `pressure_kpa` | Float64 | kPa | Pression ambiante (source en mmHg, × 0.133322) |
| `x_o2` | Float64 | fraction molaire | O2 initial |
| `x_n2` | Float64 | fraction molaire | N2 initial |
| `x_co2` | Float64 | fraction molaire | CO2 initial (0 = pas de CO2, vrai zéro) |
| `x_he` | Float64 | fraction molaire | He initial (0 = pas d'hélium, vrai zéro) |
| `diluent` | string |  | Gaz inertes présents, calculé depuis x_n2, x_co2, x_he (ex. « N2+CO2 ») |
| `d0_mm` | Float64 | mm | Diamètre initial de la gouttelette |
| `d_ext_mm` | Float64 | mm | Diamètre à l'extinction de la flamme visible ; vide si pas d'extinction (qc: sans_objet) |
| `burning_rate_mm2_s` | Float64 | mm²/s | Constante de combustion K (pente de d² en fonction du temps) ; l'en-tête PSI dit « mm », le rapport NASA dit mm²/s |
| `burn_time_s` | Float64 | s | Durée de combustion |
| `test_end_raw` | string |  | Issue telle qu'écrite dans la source (Extinction, Disruption, Completion) |
| `outcome` | string |  | Issue normalisée (valeurs OUTCOMES du schéma) |
| `gravity` | string |  | micro : investigation de type « Microgravity Investigation » (ISS) |
| `source_file` | string |  | Fichier PSI d'origine |
| `source_line` | Int64 |  | Ligne dans le fichier d'origine (en-tête = 1) |
| `qc_flags` | string |  | Marques qualité « colonne:motif;... » (motifs : QC_REASONS du schéma) |

## families/gas.parquet

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `experiment` | string |  | ACME CFI-G, ACME Flame Design ou SPICE |
| `psi_id` | string |  | Investigation PSI |
| `test_id` | string |  | Code d'essai (ACME, espaces retirés) ou « GMT<jour>-L<ligne> » (SPICE, qui n'a pas d'identifiant) |
| `session` | string |  | Groupe pour la validation croisée : jour d'essai (ACME) ou flamme = jour + heure d'allumage (SPICE) |
| `test_date` | string | AAAA-MM-JJ | ACME : déduite du code AAJJJ ; SPICE : année inconnue, vide |
| `gmt_day` | Int64 | jour de l'année | Jour GMT (SPICE ; ACME : JJJ du code) |
| `flame_type` | string |  | normal, inverse ou coflow |
| `fuel` | string |  | Combustible (ethylene, propane, n-butane...) |
| `fuel_label_raw` | string |  | Libellé d'origine (ex. « 30% butane » = bouteille à 30 %, « 75 % Propylene ») |
| `x_fuel` | Float64 | fraction molaire | Combustible côté combustible, en début d'essai |
| `x_fuel_final` | Float64 | fraction molaire | Combustible dans la chambre en fin d'essai (flammes inverses) |
| `x_o2` | Float64 | fraction molaire | O2 côté oxydant, en début d'essai |
| `x_o2_final` | Float64 | fraction molaire | O2 dans la chambre en fin d'essai (flammes normales) |
| `pressure_kpa` | Float64 | kPa | Pression en début d'essai (CFI-G : « approx p », marqué approx) |
| `pressure_final_kpa` | Float64 | kPa | Pression en fin d'essai (Flame Design) |
| `fuel_rate_mg_s` | Float64 | mg/s | Débit de combustible au brûleur (mélange) |
| `hc_rate_mg_s` | Float64 | mg/s | Débit d'hydrocarbure seul (SPICE « HC Fuel Rate », CFI-G « mHC » / « HC burnrate ») |
| `fuel_rate_sccm` | Float64 | sccm | Débit de combustible (SPICE) |
| `o2_rate_mg_s` | Float64 | mg/s | Débit d'O2 au brûleur (flammes inverses) |
| `n2_rate_mg_s` | Float64 | mg/s | Débit de N2 au brûleur |
| `total_rate_mg_s` | Float64 | mg/s | Débit total au brûleur |
| `nozzle_mm` | Float64 | mm | Diamètre de la buse (SPICE) |
| `coflow_cm_s` | Float64 | cm/s | Vitesse du co-courant d'air (SPICE) |
| `z_st` | Float64 |  | Fraction de mélange stœchiométrique |
| `t_ad_K` | Float64 | K | Température adiabatique de flamme (calculée par l'équipe ACME) |
| `tfp` | boolean |  | Sonde TFP (pyrométrie à filament fin) utilisée (CFI-G) |
| `hot_ignition_raw` | string |  | Allumage chaud tel qu'écrit (yes, no, flash) |
| `end_mode_raw` | string |  | Fin d'essai : SE = auto-extinction, FT = coupure du débit, « - » = rien |
| `cool_flame` | boolean |  | Flamme froide observée : colonne « Cool flame? » ou commentaire explicite ; vide = non renseigné (pas « non ») |
| `burn_time_s` | Float64 | s | Durée de la flamme chaude |
| `peak_burner_T_K` | Float64 | K | Température maximale du brûleur (source en °C, + 273.15) |
| `flame_color` | string |  | Couleur notée (minuscules) |
| `outcome` | string |  | Issue normalisée (OUTCOMES du schéma) ; vide pour Flame Design et SPICE (pas d'issue dans la table) |
| `gravity` | string |  | micro : investigations de type « Microgravity Investigation » (ISS) |
| `comments` | string |  | Commentaires d'origine |
| `source_file` | string |  | Fichier PSI d'origine |
| `source_line` | Int64 |  | Ligne dans le fichier d'origine (en-tête = 1) |
| `qc_flags` | string |  | Marques qualité « colonne:motif;... » |

## families/solids.parquet

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `experiment` | string |  | BASS, BASS-II, Saffire-I, Saffire-II, Saffire-III |
| `psi_id` | string |  | Investigation PSI |
| `test_id` | string |  | BASS : « AR<n° As Run>-T<n° essai> » ; BASS-II : n° d'essai (B1, O3a...) ; Saffire : n° d'échantillon (+ « -1g » pour les essais au sol) |
| `session` | string |  | Groupe pour la validation croisée : jour d'essai (BASS, BASS-II) ou vol (Saffire) |
| `test_date` | string | AAAA-MM-JJ | Date de l'essai |
| `pi` | string |  | Chercheur principal responsable de l'essai (BASS-II) |
| `sample_no` | string |  | Numéro d'échantillon |
| `material` | string |  | pmma, sibal (tissu 75 % coton / 25 % fibre de verre), nomex, ultem, silicone, paraffin wax, japan wax, wax, pmma+nomex |
| `material_raw` | string |  | Description d'origine de l'échantillon |
| `geometry` | string |  | flat sample, film, slab, rod, sphere, spherical section, candle, fabric, structured sample |
| `thickness_mm` | Float64 | mm | Épaisseur |
| `width_cm` | Float64 | cm | Largeur |
| `length_cm` | Float64 | cm | Longueur (Saffire) |
| `diameter_mm` | Float64 | mm | Diamètre (tiges, sphères) |
| `color` | string |  | black / clear (PMMA) |
| `sides_burning` | Int64 |  | Échantillon allumé sur 1 ou 2 faces (« 1 sided ») |
| `flow_direction` | string |  | opposed / concurrent |
| `flow_cm_s` | Float64 | cm/s | Vitesse d'air si une seule valeur ; vide si rampe (voir flow_min / flow_max) |
| `flow_min_cm_s` | Float64 | cm/s | Plus petite vitesse d'air affichée pendant l'essai (hors réglages en « pot ») |
| `flow_max_cm_s` | Float64 | cm/s | Plus grande vitesse d'air affichée pendant l'essai |
| `flow_raw` | string |  | Vitesse d'air telle qu'écrite (« Air display », « Air Flow ») |
| `fan_raw` | string |  | Réglage du ventilateur tel qu'écrit (« Fan display », potentiomètre) |
| `flow_restrictor` | string |  | Restricteur de débit (BASS, BASS-II) |
| `x_o2` | Float64 | fraction molaire | O2 initial |
| `x_o2_final` | Float64 | fraction molaire | O2 final (BASS-II) |
| `pressure_kpa` | Float64 | kPa | Pression (BASS : mesurée ; BASS-II : nominale 1 atm ; Saffire : non donnée) |
| `co2_initial_pct` | Float64 | % vol | CO2 initial (BASS-II) |
| `co2_final_pct` | Float64 | % vol | CO2 final (BASS-II) |
| `co2_mmhg` | Float64 | mmHg | CO2 (BASS) |
| `co_initial_ppm` | Float64 | ppm | CO initial (BASS-II) |
| `co_final_ppm` | Float64 | ppm | CO final (BASS-II) |
| `ignition_power_W` | Float64 | W | Puissance de l'allumeur (Saffire) |
| `ignition_time_s` | Float64 | s | Durée d'allumage (Saffire) |
| `burn_time_s` | Float64 | s | Durée de combustion (Saffire) |
| `burn_length_cm` | Float64 | cm | Longueur brûlée (Saffire-II) |
| `burn_complete` | boolean |  | Échantillon entièrement brûlé (« Complete ») |
| `spread_rate_mm_s` | Float64 | mm/s | Vitesse de propagation (Saffire-II) |
| `spread_mode` | string |  | Mode de propagation noté (ex. « acceleratory » : pas de vitesse unique) |
| `observations` | string |  | Observations d'origine (BASS) et textes qualitatifs |
| `outcome` | string |  | Issue normalisée ; BASS / BASS-II : depuis annotations/bass_outcomes.csv |
| `gravity` | string |  | micro (vol) ou 1g (essais au sol de Saffire-II) |
| `source_file` | string |  | Fichier PSI d'origine |
| `source_line` | Int64 |  | Ligne dans le fichier d'origine (en-tête = 1) |
| `qc_flags` | string |  | Marques qualité « colonne:motif;... » |

## Motifs de `qc_flags`

| Motif | Sens |
|---|---|
| `sans_objet` | vide car sans objet vu l'issue de l'essai (ne compte pas comme un trou de données) |
| `doc` | valeur absente de la table, prise dans un document NASA (source_doc / source_page) |
| `nominal` | valeur nominale de l'expérience, pas mesurée essai par essai |
| `recopie` | recopiée d'une autre ligne de la même table |
| `zero_fictif` | 0 de la source remplacé par vide (0 utilisé pour « pas de donnée ») |
| `incoherent` | valeur physiquement douteuse |
| `a_verifier` | sources NASA contradictoires ou identifiant en double |
| `approx` | valeur approchée dans la source (« ~6 ») |
| `rampe` | condition variable pendant l'essai |
| `sans_allumage_chaud` | burn time = 0 car pas d'allumage chaud |
| `qualitatif` | texte qualitatif à la place d'un nombre (« LOW O2 ») : vide, texte gardé en commentaire |
| `erreur_excel` | erreur de formule dans la source (« #DIV/0! », « #VALUE! ») : vide |
| `deduit` | déduit d'un texte explicite de la même ligne (ex. « 5 3 2 ext » -> extinction) |
