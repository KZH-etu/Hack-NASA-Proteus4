"""Précision, rappel, F1, accuracy par famille (prédictions hors échantillon, sessions mises de côté).

    python -m src.models.model_rf.experiments.rapport_classification
"""
import warnings

import pandas as pd

from ..data_prep import load_tables
from ..metrics import classification_report_fr
from ..families import FAMILIES
from ..forest import model_for

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)

tables = load_tables()
for family, fiche in FAMILIES.items():
    for output, spec in fiche["sorties"].items():
        if spec["type"] != "classification":
            continue
        rep = classification_report_fr(tables, family, output, model_for(family, output))
        lo, hi = rep.attrs["f1_macro_IC95"]
        print(f"\n=== {family} / {output} — {model_for(family, output).name} ===")
        print(rep.round(3).fillna("").to_string(index=False))
        print(f"F1 macro, IC 95 % : [{lo:.3f} ; {hi:.3f}]")
        print("Matrice de confusion (lignes = vraie issue, colonnes = issue prédite) :")
        print(rep.attrs["confusion"].to_string())
