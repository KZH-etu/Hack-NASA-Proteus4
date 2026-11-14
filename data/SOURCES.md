# Lien d'origine des sources :

- https://psi.nasa.gov/physci/repo/search?q=combustion
- https://www.nasa.gov/glenn/glenn-expertise-space-exploration/physical-sciences-program/combustion-science/
- https://www.youtube.com/watch?v=W1oXykoz9zg
- https://www.nasa.gov/missions/station/a-researchers-guide-to-combustion-science/
- https://sma.nasa.gov/sma-disciplines/accllp/apollo-1
- https://sma.nasa.gov/sma-disciplines/accllp/apollo-13
- https://www.nasa.gov/history/25-years-ago-fire-aboard-space-station-mir/
- https://spinoff.nasa.gov/node/9582
- https://spinoff.nasa.gov/node/9407
- https://spinoff.nasa.gov/node/9918

# Sources des données

Chaque fichier de `data/raw/` et `data/processed/` doit être listé ici.

`data/raw/` n'est pas versionné : on le regénère avec les scripts ci-dessous. Le détail machine (statut HTTP, taille, chemin local) est dans `data/raw/download_log.csv` et dans le `files_manifest.csv` de chaque investigation.

## Structure

```
data/
├── raw/                                  # non versionné
│   ├── psi/
│   │   ├── psi_index.csv                 # 1 ligne par investigation (DOI, licence, nb de fichiers, taille totale)
│   │   └── PSI-xx_ACRONYME/
│   │       ├── investigation.json        # métadonnées brutes de l'API PSI
│   │       ├── files_manifest.csv        # tous les fichiers de l'investigation, téléchargés ou non
│   │       ├── experimental_table/       # CSV « Experimental table », tels quels
│   │       └── documents/                # matrices d'essais, calibration (tels quels)
│   ├── ntrs/                             # articles NTRS pour le RAG (branche rag)
│   └── download_log.csv
├── processed/                            # versionné, généré par src/data/
│   ├── unified.parquet                   # table catalogue (schéma src/common/schema.py)
│   ├── families/                         # une table de modélisation par famille physique
│   └── annotations/                      # valeurs saisies à la main, avec leur page source
└── SOURCES.md
```

## NASA PSI (Physical Sciences Informatics)

Script : `python -m src.data.download_psi` (API publique https://psi.nasa.gov, sans compte). Téléchargé le 2026-11-14.

| PSI | Expérience | Famille | DOI | Licence | Fichiers dans PSI |
|---|---|---|---|---|---|
| PSI-69 | FLEX | droplet | [10.60555/mbq8-0451](https://doi.org/10.60555/mbq8-0451) | CC0-1.0 | 7 515 |
| PSI-39 | CFI | droplet | [10.60555/m6pj-a914](https://doi.org/10.60555/m6pj-a914) | CC0-1.0 | 3 256 |
| PSI-159 | ACME CFI-G | gas | [10.60555/cyt1-kh64](https://doi.org/10.60555/cyt1-kh64) | CC0-1.0 | 3 756 |
| PSI-10 | ACME Flame Design | gas | [10.60555/w4zy-bt45](https://doi.org/10.60555/w4zy-bt45) | non renseignée dans les métadonnées | 3 807 |
| PSI-107 | SPICE | gas | [10.60555/9kbh-e962](https://doi.org/10.60555/9kbh-e962) | CC0-1.0 | 188 |
| PSI-26 | BASS | solid | [10.60555/58h4-dy80](https://doi.org/10.60555/58h4-dy80) | CC0-1.0 | 399 |
| PSI-25 | BASS-II | solid | [10.60555/4qc4-de67](https://doi.org/10.60555/4qc4-de67) | CC0-1.0 | 1 267 |
| PSI-98 | SAFFIRE-I | solid | [10.60555/0t15-1z43](https://doi.org/10.60555/0t15-1z43) | CC0-1.0 | 76 |
| PSI-99 | SAFFIRE-II | solid | [10.60555/2chp-m469](https://doi.org/10.60555/2chp-m469) | CC0-1.0 | 221 |
| PSI-100 | SAFFIRE-III | solid | [10.60555/040q-4h36](https://doi.org/10.60555/040q-4h36) | CC0-1.0 | 87 |
| PSI-101 | SAME-R | aerosol | [10.60555/2np7-jv14](https://doi.org/10.60555/2np7-jv14) | CC0-1.0 | 344 |
| PSI-102 | SAME | aerosol | [10.60555/gd4k-8h62](https://doi.org/10.60555/gd4k-8h62) | CC0-1.0 | 165 |

### Fichiers téléchargés

| Fichier (sous `data/raw/psi/`) | PSI | Notes |
|---|---|---|
| `PSI-69_FLEX/experimental_table/PSI-69_Experimental table_FLEX.csv` | PSI-69 | encodage cp1252 |
| `PSI-39_CFI/experimental_table/PSI-39_Experimental table_CFI.csv` | PSI-39 | |
| `PSI-159_ACME_CFI-G/experimental_table/PSI-159_Experimental table_CFI-G_Normal Flames.csv` | PSI-159 | |
| `PSI-159_ACME_CFI-G/experimental_table/PSI-159_Experimental table_CFI-G_Inverse Flames.csv` | PSI-159 | ~860 lignes vides en fin de fichier |
| `PSI-10_ACME_Flame_Design/experimental_table/PSI-10_Experimental table_Flame Design_Normal Flame.csv` | PSI-10 | valeurs `RAMPED` |
| `PSI-10_ACME_Flame_Design/experimental_table/PSI-10_Experimental table_Flame Design_Inverse Flame.csv` | PSI-10 | |
| `PSI-107_SPICE/experimental_table/PSI-107_Experimental table_Spice.csv` | PSI-107 | |
| `PSI-26_BASS/experimental_table/PSI-26_Experimental table_BASS.csv` | PSI-26 | |
| `PSI-26_BASS/documents/PSI-26_Science Documents_As Run_Test Matrix.xlsx` | PSI-26 | O2, pression, débit, observations par essai |
| `PSI-26_BASS/documents/PSI-26_Science Documents_Planned_Test Matrix.xlsx` | PSI-26 | |
| `PSI-25_BASS-II/experimental_table/PSI-25_Experimental table_BASS-II.csv` | PSI-25 | |
| `PSI-25_BASS-II/documents/PSI-25_Science Documents_BASS-II_Test.Matrices.xlsx` | PSI-25 | une feuille par PI |
| `PSI-25_BASS-II/documents/PSI-25_Reference Data_Fan calibration data.xlsx` | PSI-25 | conversion potentiomètre → vitesse d'air |
| `PSI-98_SAFFIRE-I/experimental_table/PSI-98_Experimental table_SAFFIRE-1.csv` | PSI-98 | |
| `PSI-99_SAFFIRE-II/experimental_table/PSI-99_Experimental table_SAFFIRE-2.csv` | PSI-99 | contient des valeurs 1g |
| `PSI-100_SAFFIRE-III/experimental_table/PSI-100_Experimental table_SAFFIRE-3.csv` | PSI-100 | |
| `PSI-101_SAME-R/experimental_table/PSI-101_Experimental table_SAME-R.csv` | PSI-101 | |
| `PSI-102_SAME/experimental_table/PSI-102_Experimental table_SAME.csv` | PSI-102 | |

## Fichiers produits (`data/processed/`, versionnés)

Générés par `python -m src.data.build_unified` à partir de `data/raw/psi/`. Ne pas éditer à la main, sauf `annotations/`.

| Fichier | Contenu | Sources |
|---|---|---|
| `unified.parquet` | table catalogue, une ligne par essai (schéma `src/common/schema.py`) | tables expérimentales PSI listées ci-dessus |
| `experiments_all.csv` | la table catalogue en CSV, lisible sur GitHub, avec liens PSI et DOI | idem |
| `families/droplets.parquet` | FLEX (CFI à venir) | PSI-69 |
| `families/gas.parquet` | ACME CFI-G, ACME Flame Design, SPICE | PSI-159, PSI-10, PSI-107 |
| `families/solids.parquet` | BASS, BASS-II, Saffire I–III (Saffire-II : vol + sol 1g) | PSI-26 (+ matrice As Run), PSI-25, PSI-98, PSI-99, PSI-100 |
| `campaigns.csv` | une ligne par investigation (DOI, plateforme, statut) | `psi_index.csv`, `investigation.json` |
| `skipped_rows.csv` | lignes sources écartées et raison | — |
| `data_dictionary.md`, `qc_report.md` | colonnes et unités ; contrôle qualité | — |
| `annotations/bass_outcomes.csv` | issues BASS / BASS-II saisies à la main (avec page) | NASA/TM-20210011385, annexe A |

## Documents NASA (NTRS)

| Document | NTRS | Utilisé pour | Notes |
|---|---|---|---|
| NASA/TP-2015-216046 — Detailed Results from the Flame Extinguishment Experiment (FLEX) | [20150023456](https://ntrs.nasa.gov/citations/20150023456) | sens des colonnes FLEX, unité de K (mm²/s), signification du « – » (Table IX, p. 19) | |
| NASA/TM-20210011385 — BASS-II Summary Report | [20210011385](https://ntrs.nasa.gov/citations/20210011385) | issues BASS-II (annexe A, pp. 103–113) ; pression nominale 1 atm (pp. 11, 41) ; tiges en PMMA coulé (p. 47) | pas de vitesses de propagation dans l'annexe A |
| The Spacecraft Fire Experiment (Saffire) — Objectives, Development and Status (2016) | [20170001636](https://ntrs.nasa.gov/citations/20170001636) | matériaux des échantillons Saffire-II (Table 1 : S6 = SIBAL, S9 = PMMA plat 10 mm), épaisseur SIBAL 0,33 mm | document d'avant le vol : débits prévus, pas forcément ceux réalisés |
