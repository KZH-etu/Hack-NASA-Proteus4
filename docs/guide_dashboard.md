# Guide du dashboard : prédictions

Ce qu'il faut entrer pour obtenir une prédiction, et ce qu'il faut afficher. Modèle à utiliser : **`model_gp`** (le meilleur d'après `src/models/comparaison.md`).

## 1. Appeler le modèle

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # pour que « import src » marche
import streamlit as st
from src.models import load

@st.cache_resource(show_spinner="Chargement des modèles (environ 1 min 30 au premier lancement)…")
def get_gp():
    return load("model_gp")

gp = get_gp()
r = gp.flex.predict({...})        # ou gp.solids.predict / gp.gas.predict
```

Le premier appel de chaque famille prend environ 30 s, les suivants sont instantanés.

## 2. Données à entrer

**L'O2 se donne en %** (21 = air) et la pression en kPa (101,3 = 1 atm).

### Gouttelettes : `gp.flex.predict`

| Entrée | Valeurs | Plage testée par la NASA |
|---|---|---|
| `fuel` | `"heptane"` ou `"methanol"` | — |
| `o2_percent` | % d'O2 | 12 à 34 |
| `pressure_kpa` | kPa | 70 à 309 |
| `d0_mm` | diamètre de la goutte (mm), 3 par défaut | 1,1 à 4,7 |
| `co2_percent`, `he_percent` | % de CO2 / d'hélium, 0 par défaut | 0 à 70 / 0 à 45 |

### Solides : `gp.solids.predict`

| Entrée | Valeurs | Plage testée |
|---|---|---|
| `material` | `"pmma_flat"` (plaque), `"pmma_rod_sphere"` (tige, sphère), `"fabric_other"` (tissu, autre) | — |
| `o2_percent` | % d'O2 | 14,2 à 22,2 |
| `flow_cm_s` | vitesse de l'air (cm/s) | 0,5 à 53 |

### Gaz : `gp.gas.predict`

| Entrée | Valeurs | Plage testée |
|---|---|---|
| `fuel` | `"ethane"`, `"propane"` ou `"n-butane"` | — |
| `o2_percent` | % d'O2 | 18 à 40 |
| `pressure_kpa` | kPa | 51 à 304 |
| `x_fuel` | part de combustible dans le jet (0 à 1) | 0,02 à 1 |
| `hc_rate_mg_s` | débit de combustible (mg/s) | 0,1 à 3,2 |

En dehors des plages testées, le modèle répond quand même, mais il ajoute une alerte : c'est une extrapolation.

## 3. Ce qu'il faut afficher

### Gouttelettes

| Clé | À afficher | Texte conseillé |
|---|---|---|
| `p_extinction` + `p_extinction_interval_90` | grande valeur + fourchette | « Probabilité que la flamme s'éteigne : 41 % (entre 6 % et 64 %) » |
| `burning_rate_k_mm2_s` + `burning_rate_k_interval_95` | valeur + fourchette | « Vitesse de combustion : 0,54 mm²/s (entre 0,38 et 0,70) » |
| `warnings` | un `st.warning` par message | tel quel |

### Solides

| Clé | À afficher | Texte conseillé |
|---|---|---|
| `p_flame_sustained` + `p_flame_sustained_interval_90` | valeur + fourchette | « Probabilité que la flamme tienne : 81 % (entre 49 % et 95 %) » |
| `p_flame_sustained` = `None` | pas de chiffre | « Pas de donnée NASA dans ces conditions » |
| `warnings` | `st.warning` | toujours affiché : ce modèle est peu fiable |

### Gaz

| Clé | À afficher | Texte conseillé |
|---|---|---|
| `p_hot_ignition` + intervalle | valeur + fourchette | « Probabilité d'allumage : 98 % » |
| `p_self_extinction_if_ignited` + intervalle | valeur + fourchette | « Si elle s'allume, probabilité qu'elle s'éteigne seule : 57 % » |
| `nearest_tests` | petit tableau | « Essais NASA les plus proches » |
| `warnings` | `st.warning` | tel quel |

### Fiabilité à écrire à côté de chaque résultat

| Prédiction | Fiabilité |
|---|---|
| Extinction d'une gouttelette | **bonne** |
| Vitesse de combustion (gouttelette) | **bonne** |
| Auto-extinction d'une flamme de gaz | **moyenne** |
| Allumage d'une flamme de gaz | **faible** |
| Solides | **faible** (indication seulement) |

## 4. Prochaine expérience recommandée

```python
rec = gp.recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0}, n=5)
# solides : {"material": "pmma_flat", "o2_percent": 34, "flow_cm_s": 10}
```

Afficher `rec["recommendations"]` sous forme de tableau : `rank`, `conditions`, `p_extinction` (solides : `p_flame_sustained`) avec son intervalle, et surtout **`why`**, la phrase qui explique le choix. Exemple : *« aucun essai FLEX sous 70 kPa ; essai réel le plus proche loin (n° 39 : 34 % O2, 71,3 kPa) ; modèle incertain »*.

## 5. Scénarios à proposer en boutons

| Scénario | Entrées |
|---|---|
| Cabine ISS | heptane, 21 % O2, 101,3 kPa, goutte de 3 mm |
| Habitat lunaire | heptane, 34 % O2, 55 kPa, goutte de 3 mm |
| Atmosphère pauvre en O2 | heptane, 15 % O2, 101,3 kPa, goutte de 3 mm |

## 6. Trois règles

1. Toujours montrer la fourchette à côté du chiffre.
2. Toujours afficher les `warnings`.
3. Ne jamais remplacer une valeur absente par un chiffre : écrire « pas de donnée ».

Pour la liste des essais (onglet Explorer), le fichier à lire est `data/processed/experiments_all.csv` : 1 720 essais, avec le lien vers la source NASA dans les colonnes `psi_url` et `doi_url`.
