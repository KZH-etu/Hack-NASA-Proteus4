"""model_gp : modèles à processus gaussien, un sous-dossier par famille de données.

- flex   : gouttelettes FLEX (probabilité d'extinction, K) ;
- solids : solides BASS / BASS-II (la flamme tient-elle ; fiabilité faible, annoncée) ;
- gas    : flammes gazeuses ACME CFI-G (allumage, auto-extinction).

    from src.models.model_gp import flex, solids, gas, recommend_next_experiment
    flex.predict({"fuel": "heptane", "o2_percent": 21, "pressure_kpa": 101.3, "d0_mm": 3.0})
    recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0})

Validation : python -m src.models.model_gp.<famille>.evaluate (rapport dans <famille>/validation.md).
"""

from src.models.model_gp import flex, gas, solids
from src.models.model_gp.recommend import recommend_next_experiment

NAME = "model_gp"
DESCRIPTION = "Processus gaussiens (FLEX, BASS / BASS-II, ACME CFI-G), validés par jour d'essai"
FAMILIES = {"droplets": flex, "solids": solids, "gas": gas}

__all__ = ["DESCRIPTION", "FAMILIES", "NAME", "flex", "gas", "recommend_next_experiment", "solids"]
