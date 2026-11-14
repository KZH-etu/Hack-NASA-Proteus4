"""model_catboost : un seul classifieur CatBoost à 3 classes (extinction / combustion / intermédiaire)
pour les gouttelettes, les solides et les flammes gazeuses réunis.

    from src.models import load
    m = load("model_catboost")
    m.FAMILIES["droplets"].predict({"fuel": "heptane", "o2_percent": 21, "pressure_kpa": 101.3, "d0_mm": 3.0})

Entraînement : python -m src.models.model_catboost.train ; validation : python -m src.models.model_catboost.evaluate.
"""

from src.models.model_catboost.model import CLASSES, FAMILY_TYPES, predict

NAME = "model_catboost"
DESCRIPTION = "CatBoost à 3 classes (extinction / combustion / intermédiaire), toutes familles réunies"


class FamilyPredictor:
    """Même interface que les familles de model_gp : predict(conditions) -> dict."""

    def __init__(self, family):
        self.family = family

    def predict(self, conditions):
        return predict(self.family, conditions)


FAMILIES = {family: FamilyPredictor(family) for family in FAMILY_TYPES}

__all__ = ["CLASSES", "DESCRIPTION", "FAMILIES", "NAME", "predict"]
