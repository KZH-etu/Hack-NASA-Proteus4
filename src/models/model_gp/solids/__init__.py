"""Modèle des solides (BASS / BASS-II) : model.py (carte d'inflammabilité, predict, prochaine expérience),
evaluate.py (validation).

    from src.models.model_gp import solids
    solids.predict({"material": "pmma_flat", "o2_percent": 21, "flow_cm_s": 10})
"""

from src.models.model_gp.solids.model import (FEATURES, MATERIAL_CLASSES, MATERIAL_GROUPS, SolidsModel, features, observations,
                                     predict, recommend_next_experiment, trained_model)

__all__ = ["FEATURES", "MATERIAL_CLASSES", "MATERIAL_GROUPS", "SolidsModel", "features", "observations", "predict",
           "recommend_next_experiment", "trained_model"]
