"""Prochaine expérience FLEX recommandée autour d'un scénario.

    python -m src.models.model_rf.flex.recommend
"""
import warnings

import pandas as pd

from ..recommend import recommend
from . import FAMILY

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    pd.set_option("display.width", 200)
    for output in ("issue", "vitesse_combustion_mm2_s"):
        print(f"\n=== {FAMILY} — {output} ===")
        print(recommend(FAMILY, output=output).round(3).to_string(index=False))
