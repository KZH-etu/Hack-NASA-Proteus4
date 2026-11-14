"""Recommandation de la prochaine expérience, pour toute famille avec modèle.

    python -m src.models.model_rf.recommend "Gouttelettes (FLEX)"

Principe : autour du scénario de mission, on cherche les conditions où le modèle doute le plus
ET où aucun essai NASA réel n'existe (moitié incertitude, moitié nouveauté), en préférant les
conditions proches du scénario. Les paramètres texte (carburant, matériau…) restent ceux du scénario.
"""
import sys
import warnings

import pandas as pd

from .service import MLService


def recommend(family: str, scenario: dict | None = None, output: str | None = None,
              top_k: int = 5, ml: MLService | None = None) -> pd.DataFrame:
    ml = ml or MLService.load_or_train()
    scenario = {**ml.default_scenario(family), **(scenario or {})}
    return ml.recommend_next_experiment(family, scenario, output=output, top_k=top_k)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    pd.set_option("display.width", 200)
    family = sys.argv[1] if len(sys.argv) > 1 else "Gouttelettes (FLEX)"
    print(recommend(family).round(3).to_string(index=False))
