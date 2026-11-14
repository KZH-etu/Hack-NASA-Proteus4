# Rapport qualité — data/processed

Généré par `python -m src.data.build_unified`. Ne pas éditer à la main.
Règles : `docs/regles_valeurs_manquantes.md`.

## Lignes par campagne

| PSI | Expérience | Famille | Lignes | Avec marques | Statut |
|---|---|---|---:|---:|---|
| PSI-69 | FLEX | droplet | 274 | 274 | traité |
| PSI-39 | CFI | droplet | 0 | 0 | à faire (droplets) |
| PSI-159 | ACME CFI-G | gas | 333 | 333 | traité |
| PSI-10 | ACME Flame Design | gas | 327 | 327 | traité |
| PSI-107 | SPICE | gas | 435 | 435 | traité |
| PSI-26 | BASS | solid | 121 | 121 | traité |
| PSI-25 | BASS-II | solid | 129 | 129 | traité |
| PSI-98 | SAFFIRE-I | solid | 2 | 2 | traité |
| PSI-99 | SAFFIRE-II | solid | 18 | 18 | traité |
| PSI-100 | SAFFIRE-III | solid | 2 | 2 | traité |
| PSI-101 | SAME-R | aerosol | 0 | 0 | à faire (aerosols) |
| PSI-102 | SAME | aerosol | 0 | 0 | à faire (aerosols) |

Lignes écartées : 43 (détail dans `skipped_rows.csv`).

## families/droplets.parquet (274 lignes)

Marques les plus fréquentes :

- `d_ext_mm:sans_objet` × 58
- `d_ext_mm:zero_fictif` × 8
- `cir_identifier:a_verifier` × 2
- `burn_time_s:approx` × 2
- `pressure_kpa:zero_fictif` × 1

Cases vides :

| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |
|---|---:|---:|---:|---:|---:|---:|
| `test_time_gmt` | 1 / 274 | 0 | 0 | 0 | 0 | 1 |
| `pressure_kpa` | 1 / 274 | 0 | 1 | 0 | 0 | 0 |
| `d0_mm` | 12 / 274 | 0 | 0 | 0 | 0 | 12 |
| `d_ext_mm` | 85 / 274 | 58 | 0 | 0 | 0 | 27 |
| `burning_rate_mm2_s` | 16 / 274 | 0 | 0 | 0 | 0 | 16 |
| `burn_time_s` | 6 / 274 | 0 | 0 | 0 | 0 | 6 |

## families/gas.parquet (1095 lignes)

Marques les plus fréquentes :

- `x_o2:nominal` × 435
- `pressure_kpa:nominal` × 435
- `pressure_kpa:approx` × 333
- `n2_rate_mg_s:rampe` × 69
- `total_rate_mg_s:rampe` × 69
- `z_st:rampe` × 69
- `t_ad_K:rampe` × 69
- `burn_time_s:sans_allumage_chaud` × 62
- `x_fuel:rampe` × 60
- `fuel_rate_mg_s:rampe` × 60
- `x_o2:rampe` × 9
- `coflow_cm_s:incoherent` × 8
- `hc_rate_mg_s:zero_fictif` × 7
- `o2_rate_mg_s:rampe` × 6
- `x_fuel:a_verifier` × 2

Cases vides :

| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |
|---|---:|---:|---:|---:|---:|---:|
| `test_date` | 435 / 1095 | 0 | 0 | 0 | 435 | 0 |
| `x_fuel` | 60 / 1095 | 0 | 0 | 60 | 0 | 0 |
| `x_fuel_final` | 821 / 1095 | 0 | 0 | 0 | 821 | 0 |
| `x_o2` | 11 / 1095 | 0 | 0 | 11 | 0 | 0 |
| `x_o2_final` | 729 / 1095 | 0 | 0 | 0 | 709 | 20 |
| `pressure_final_kpa` | 788 / 1095 | 0 | 0 | 0 | 768 | 20 |
| `fuel_rate_mg_s` | 520 / 1095 | 0 | 0 | 60 | 453 | 7 |
| `hc_rate_mg_s` | 334 / 1095 | 0 | 7 | 0 | 327 | 0 |
| `fuel_rate_sccm` | 667 / 1095 | 0 | 0 | 0 | 660 | 7 |
| `o2_rate_mg_s` | 829 / 1095 | 0 | 0 | 8 | 821 | 0 |
| `n2_rate_mg_s` | 839 / 1095 | 0 | 0 | 71 | 768 | 0 |
| `total_rate_mg_s` | 839 / 1095 | 0 | 0 | 71 | 768 | 0 |
| `nozzle_mm` | 660 / 1095 | 0 | 0 | 0 | 660 | 0 |
| `coflow_cm_s` | 688 / 1095 | 0 | 0 | 8 | 660 | 20 |
| `z_st` | 508 / 1095 | 0 | 0 | 73 | 435 | 0 |
| `t_ad_K` | 508 / 1095 | 0 | 0 | 73 | 435 | 0 |
| `tfp` | 762 / 1095 | 0 | 0 | 0 | 762 | 0 |
| `hot_ignition_raw` | 762 / 1095 | 0 | 0 | 0 | 762 | 0 |
| `end_mode_raw` | 762 / 1095 | 0 | 0 | 0 | 762 | 0 |
| `cool_flame` | 1084 / 1095 | 0 | 0 | 0 | 916 | 168 |
| `burn_time_s` | 762 / 1095 | 0 | 0 | 0 | 762 | 0 |
| `peak_burner_T_K` | 811 / 1095 | 0 | 0 | 0 | 762 | 49 |
| `flame_color` | 975 / 1095 | 0 | 0 | 0 | 941 | 34 |
| `outcome` | 762 / 1095 | 0 | 0 | 0 | 762 | 0 |
| `comments` | 1010 / 1095 | 0 | 0 | 0 | 642 | 368 |

## families/solids.parquet (272 lignes)

Marques les plus fréquentes :

- `diameter_mm:sans_objet` × 148
- `flow_cm_s:rampe` × 129
- `pressure_kpa:nominal` × 129
- `width_cm:sans_objet` × 124
- `thickness_mm:sans_objet` × 124
- `material:doc` × 91
- `flow_cm_s:qualitatif` × 29
- `co_initial_ppm:incoherent` × 13
- `x_o2:approx` × 11
- `flow_cm_s:a_verifier` × 9
- `co_final_ppm:qualitatif` × 8
- `burn_length_cm:approx` × 8
- `spread_rate_mm_s:sans_objet` × 7
- `spread_rate_mm_s:qualitatif` × 7
- `burn_length_cm:recopie` × 6

Cases vides :

| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |
|---|---:|---:|---:|---:|---:|---:|
| `test_date` | 22 / 272 | 0 | 0 | 0 | 22 | 0 |
| `pi` | 143 / 272 | 0 | 0 | 0 | 143 | 0 |
| `material` | 3 / 272 | 0 | 0 | 0 | 0 | 3 |
| `material_raw` | 4 / 272 | 0 | 0 | 0 | 0 | 4 |
| `thickness_mm` | 212 / 272 | 124 | 0 | 4 | 54 | 30 |
| `width_cm` | 145 / 272 | 124 | 0 | 0 | 0 | 21 |
| `length_cm` | 252 / 272 | 0 | 0 | 2 | 250 | 0 |
| `diameter_mm` | 173 / 272 | 148 | 0 | 0 | 0 | 25 |
| `color` | 218 / 272 | 0 | 0 | 0 | 143 | 75 |
| `sides_burning` | 266 / 272 | 0 | 0 | 0 | 143 | 123 |
| `flow_direction` | 256 / 272 | 0 | 0 | 0 | 129 | 127 |
| `flow_cm_s` | 183 / 272 | 0 | 0 | 158 | 0 | 25 |
| `flow_min_cm_s` | 29 / 272 | 0 | 0 | 0 | 0 | 29 |
| `flow_max_cm_s` | 29 / 272 | 0 | 0 | 0 | 0 | 29 |
| `flow_raw` | 25 / 272 | 0 | 0 | 0 | 0 | 25 |
| `fan_raw` | 36 / 272 | 0 | 0 | 0 | 22 | 14 |
| `flow_restrictor` | 23 / 272 | 0 | 0 | 0 | 22 | 1 |
| `x_o2` | 11 / 272 | 0 | 0 | 0 | 2 | 9 |
| `x_o2_final` | 145 / 272 | 0 | 0 | 2 | 143 | 0 |
| `pressure_kpa` | 22 / 272 | 0 | 0 | 0 | 22 | 0 |
| `co2_initial_pct` | 145 / 272 | 0 | 0 | 2 | 143 | 0 |
| `co2_final_pct` | 149 / 272 | 0 | 0 | 5 | 143 | 1 |
| `co2_mmhg` | 161 / 272 | 0 | 0 | 5 | 151 | 5 |
| `co_initial_ppm` | 146 / 272 | 0 | 0 | 3 | 143 | 0 |
| `co_final_ppm` | 152 / 272 | 0 | 0 | 8 | 143 | 1 |
| `ignition_power_W` | 261 / 272 | 0 | 0 | 0 | 252 | 9 |
| `ignition_time_s` | 261 / 272 | 0 | 0 | 0 | 252 | 9 |
| `burn_time_s` | 265 / 272 | 0 | 0 | 4 | 252 | 9 |
| `burn_length_cm` | 255 / 272 | 0 | 0 | 1 | 254 | 0 |
| `burn_complete` | 256 / 272 | 0 | 0 | 0 | 254 | 2 |
| `spread_rate_mm_s` | 268 / 272 | 7 | 0 | 7 | 254 | 0 |
| `spread_mode` | 267 / 272 | 0 | 0 | 0 | 254 | 13 |
| `observations` | 125 / 272 | 0 | 0 | 0 | 4 | 121 |
| `outcome` | 252 / 272 | 0 | 0 | 0 | 252 | 0 |

## unified.parquet

1641 lignes.

| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |
|---|---:|---:|---:|---:|---:|---:|
| `material` | 3 / 1641 | 0 | 0 | 0 | 0 | 3 |
| `o2_percent` | 22 / 1641 | 0 | 0 | 11 | 2 | 9 |
| `pressure_kpa` | 23 / 1641 | 0 | 1 | 0 | 22 | 0 |
| `flow_cm_s` | 1145 / 1641 | 660 | 0 | 166 | 274 | 45 |
| `outcome` | 1014 / 1641 | 0 | 0 | 0 | 1014 | 0 |
| `spread_rate_mm_s` | 1637 / 1641 | 1376 | 0 | 7 | 254 | 0 |
| `burning_rate` | 1383 / 1641 | 1367 | 0 | 0 | 0 | 16 |
