"""Schéma de la table unifiée : source de vérité partagée par data, ml, rag et app.

Règles :
- chaque ligne provient d'une source NASA identifiée (psi_id / doi / source_doc + source_page) ;
- une valeur inconnue reste vide (None / NaN), jamais inventée ;
- 1g et microgravité ne sont jamais mélangés dans un même entraînement (colonne `gravity`).
"""

from dataclasses import dataclass, fields
from typing import Optional

# Valeurs autorisées pour les colonnes catégorielles
FUEL_TYPES = ("solid", "droplet", "gas")
GRAVITY_LEVELS = ("micro", "1g")
OUTCOMES = ("burned", "extinguished", "no_ignition", "disruption", "completion", "other")


@dataclass
class UnifiedRow:
    """Une ligne = un essai expérimental (ou une condition d'essai) d'une source NASA."""

    experiment: str                          # ex. "BASS-II", "FLEX", "Saffire-II"
    psi_id: Optional[str] = None             # ex. "PSI-25"
    doi: Optional[str] = None                # ex. "10.60555/4qc4-de67"
    test_id: Optional[str] = None            # identifiant de l'essai dans la source
    fuel_type: Optional[str] = None          # un de FUEL_TYPES
    material: Optional[str] = None           # ex. "PMMA", "cotton-fiberglass", "heptane"
    geometry: Optional[str] = None           # ex. "flat sample", "rod", "droplet"
    o2_percent: Optional[float] = None       # fraction molaire d'O2, en %
    pressure_kpa: Optional[float] = None     # pression, en kPa
    flow_cm_s: Optional[float] = None        # vitesse d'écoulement imposé, en cm/s
    gravity: Optional[str] = None            # un de GRAVITY_LEVELS
    outcome: Optional[str] = None            # un de OUTCOMES
    spread_rate_mm_s: Optional[float] = None # vitesse de propagation de flamme, en mm/s
    burning_rate: Optional[float] = None     # taux de combustion (unité à préciser dans notes)
    source_doc: Optional[str] = None         # ex. "NASA/TM-20210011385" ou fichier PSI
    source_page: Optional[str] = None        # page / tableau / annexe dans source_doc
    notes: Optional[str] = None              # remarques libres (unités, hypothèses...)


# Colonnes et types pandas correspondants (pour construire / valider un DataFrame)
COLUMNS = {
    "experiment": "string",
    "psi_id": "string",
    "doi": "string",
    "test_id": "string",
    "fuel_type": "string",
    "material": "string",
    "geometry": "string",
    "o2_percent": "Float64",
    "pressure_kpa": "Float64",
    "flow_cm_s": "Float64",
    "gravity": "string",
    "outcome": "string",
    "spread_rate_mm_s": "Float64",
    "burning_rate": "Float64",
    "source_doc": "string",
    "source_page": "string",
    "notes": "string",
}

assert list(COLUMNS) == [f.name for f in fields(UnifiedRow)], "COLUMNS et UnifiedRow doivent rester alignés"
