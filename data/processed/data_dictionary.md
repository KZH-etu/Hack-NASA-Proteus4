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
| `o2_percent` | Float64 | % | O2 initial, en % molaire |
| `pressure_kpa` | Float64 | kPa | Pression ambiante |
| `flow_cm_s` | Float64 | cm/s | Vitesse d'écoulement imposé ; vide si non quantifiée (ex. FLEX : gouttelettes libres ou à dérive lente) |
| `gravity` | string |  | micro / 1g ; ne jamais mélanger les deux dans un entraînement |
| `outcome` | string |  | Issue normalisée : burned, extinguished, no_ignition, disruption, completion, other (texte d'origine dans notes) |
| `spread_rate_mm_s` | Float64 | mm/s | Vitesse de propagation de flamme |
| `burning_rate` | Float64 | selon l'expérience | Taux de combustion ; FLEX : constante K en mm²/s |
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
