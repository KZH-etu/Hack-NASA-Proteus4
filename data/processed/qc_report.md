# Rapport qualité — data/processed

Généré par `python -m src.data.build_unified`. Ne pas éditer à la main.
Règles : `docs/regles_valeurs_manquantes.md`.

## Lignes par campagne

| PSI | Expérience | Famille | Lignes | Avec marques | Statut |
|---|---|---|---:|---:|---|
| PSI-69 | FLEX | droplet | 274 | 274 | traité |
| PSI-39 | CFI | droplet | 0 | 0 | à faire (droplets) |
| PSI-159 | ACME CFI-G | gas | 0 | 0 | à faire (gas) |
| PSI-10 | ACME Flame Design | gas | 0 | 0 | à faire (gas) |
| PSI-107 | SPICE | gas | 0 | 0 | à faire (gas) |
| PSI-26 | BASS | solid | 0 | 0 | à faire (solids) |
| PSI-25 | BASS-II | solid | 0 | 0 | à faire (solids) |
| PSI-98 | SAFFIRE-I | solid | 0 | 0 | à faire (solids) |
| PSI-99 | SAFFIRE-II | solid | 0 | 0 | à faire (solids) |
| PSI-100 | SAFFIRE-III | solid | 0 | 0 | à faire (solids) |
| PSI-101 | SAME-R | aerosol | 0 | 0 | à faire (aerosols) |
| PSI-102 | SAME | aerosol | 0 | 0 | à faire (aerosols) |

Lignes écartées : 0 (détail dans `skipped_rows.csv`).

## families/droplets.parquet (274 lignes)

Marques les plus fréquentes :

- `d_ext_mm:sans_objet` × 58
- `d_ext_mm:zero_fictif` × 8
- `cir_identifier:a_verifier` × 2
- `burn_time_s:approx` × 2
- `pressure_kpa:zero_fictif` × 1

Cases vides :

| Colonne | Vides | dont sans objet | dont faux zéro vidé | vraiment manquants |
|---|---:|---:|---:|---:|
| `test_time_gmt` | 1 / 274 | 0 | 0 | 1 |
| `pressure_kpa` | 1 / 274 | 0 | 1 | 0 |
| `d0_mm` | 12 / 274 | 0 | 0 | 12 |
| `d_ext_mm` | 85 / 274 | 58 | 0 | 27 |
| `burning_rate_mm2_s` | 16 / 274 | 0 | 0 | 16 |
| `burn_time_s` | 6 / 274 | 0 | 0 | 6 |

## unified.parquet

274 lignes.

| Colonne | Vides | dont sans objet | dont faux zéro vidé | vraiment manquants |
|---|---:|---:|---:|---:|
| `pressure_kpa` | 1 / 274 | 0 | 1 | 0 |
| `flow_cm_s` | 274 / 274 | 0 | 0 | 274 |
| `spread_rate_mm_s` | 274 / 274 | 274 | 0 | 0 |
| `burning_rate` | 16 / 274 | 0 | 0 | 16 |
