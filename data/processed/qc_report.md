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
| PSI-26 | BASS | solid | 0 | 0 | à faire (solids) |
| PSI-25 | BASS-II | solid | 0 | 0 | à faire (solids) |
| PSI-98 | SAFFIRE-I | solid | 0 | 0 | à faire (solids) |
| PSI-99 | SAFFIRE-II | solid | 0 | 0 | à faire (solids) |
| PSI-100 | SAFFIRE-III | solid | 0 | 0 | à faire (solids) |
| PSI-101 | SAME-R | aerosol | 0 | 0 | à faire (aerosols) |
| PSI-102 | SAME | aerosol | 0 | 0 | à faire (aerosols) |

Lignes écartées : 34 (détail dans `skipped_rows.csv`).

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

## unified.parquet

1369 lignes.

| Colonne | Vides | sans objet | faux zéro vidé | autre marque | absente du fichier source | vraiment manquants |
|---|---:|---:|---:|---:|---:|---:|
| `o2_percent` | 11 / 1369 | 0 | 0 | 11 | 0 | 0 |
| `pressure_kpa` | 1 / 1369 | 0 | 1 | 0 | 0 | 0 |
| `flow_cm_s` | 962 / 1369 | 660 | 0 | 8 | 274 | 20 |
| `outcome` | 762 / 1369 | 0 | 0 | 0 | 762 | 0 |
| `spread_rate_mm_s` | 1369 / 1369 | 1369 | 0 | 0 | 0 | 0 |
| `burning_rate` | 1111 / 1369 | 1095 | 0 | 0 | 0 | 16 |
