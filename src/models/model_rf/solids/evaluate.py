"""Description des données de la famille « Solides (BASS-II, Saffire) » (pas de modèle, donc pas de score).

    python -m src.models.model_rf.solids.evaluate
"""
import pandas as pd

from ..data_only import DataExplorer
from . import FAMILY

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 20)
    ex = DataExplorer()
    rows = ex.rows[FAMILY]
    print(f"{FAMILY} : {len(rows)} essais en microgravité, {rows['session'].nunique()} sessions, "
          f"{rows['material'].nunique()} matériaux")
    if "outcome" in rows:
        print("Issues :", rows["outcome"].fillna("non renseigné").value_counts().to_dict())
    print(ex.summary(FAMILY).to_string())
    print("\nExemple de recherche (valeurs typiques) :")
    r = ex.find_tests(FAMILY, ex.default_scenario(FAMILY))
    print(r["essais_proches"].drop(columns=["source_file", "psi_id"], errors="ignore").round(3).to_string(index=False))
