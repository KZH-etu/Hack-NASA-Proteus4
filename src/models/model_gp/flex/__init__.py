"""Modèle FLEX (gouttelettes) : model.py (modèle, predict), recommend.py (prochaine expérience), evaluate.py (validation).

    from src.models.model_gp import flex
    flex.predict({"fuel": "heptane", "o2_percent": 21, "pressure_kpa": 101.3, "d0_mm": 3.0})
"""

from src.models.model_gp.flex.model import FEATURES, FUELS, FlexModel, conditions_to_row, features, load_data, predict, trained_model
from src.models.model_gp.flex.recommend import recommend_next_experiment

__all__ = ["FEATURES", "FUELS", "FlexModel", "conditions_to_row", "features", "load_data", "predict",
           "recommend_next_experiment", "trained_model"]
