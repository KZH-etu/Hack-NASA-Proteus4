"""Modèle des flammes gazeuses (ACME CFI-G, flammes normales) : model.py (modèle, predict), evaluate.py (validation).

    from src.models import gas
    gas.predict({"fuel": "propane", "o2_percent": 34, "pressure_kpa": 55, "x_fuel": 0.3, "hc_rate_mg_s": 1.0})
"""

from src.models.gas.model import FEATURES, FUELS, GasModel, MIN_LENGTH_SCALE, features, load_data, predict, trained_model

__all__ = ["FEATURES", "FUELS", "GasModel", "MIN_LENGTH_SCALE", "features", "load_data", "predict", "trained_model"]
