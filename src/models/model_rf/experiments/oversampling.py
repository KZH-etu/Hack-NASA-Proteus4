"""Faut-il de l'oversampling ? Comparaison des façons de traiter les issues rares.

    python -m src.models.model_rf.experiments.oversampling

RÈGLE FIXÉE AVANT DE LANCER :
- référence = version actuelle (pondération des issues rares, class_weight) ;
- critère = F1 macro (chaque issue compte autant), mêmes sessions mises de côté pour tous ;
- une variante n'est adoptée QUE si l'IC 95 % de son gain sur le F1 macro est entièrement > 0.
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

from ..data_prep import load_tables
from ..metrics import _bootstrap, oof_predictions
from ..families import FAMILIES
from ..forest import ForestModel, ForestModelBasic, OversampledForest, SmoteForest

from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)

VARIANTS = {
    "aucun rééquilibrage": ForestModelBasic,
    "pondération (actuel)": ForestModel,
    "oversampling aléatoire": OversampledForest,
    "SMOTE": SmoteForest,
}
REF = "pondération (actuel)"
f1m = lambda d: f1_score(d["truth"], d["pred"], average="macro", zero_division=0)

tables = load_tables()
rows = []
for family, fiche in FAMILIES.items():
    for output, spec in fiche["sorties"].items():
        if spec["type"] != "classification":
            continue
        oof = {name: oof_predictions(tables, family, output, cls)[0] for name, cls in VARIANTS.items()}
        ref = oof[REF]
        for name, d in oof.items():
            t, p = d["truth"].to_numpy(), d["pred"].to_numpy()
            labels = sorted(set(t))
            rec = precision_recall_fscore_support(t, p, labels=labels, zero_division=0)[1]
            row = {"famille": family, "variante": name, "F1_macro": round(f1m(d), 3),
                   "accuracy": round(accuracy_score(t, p), 3),
                   "rappel par issue": ", ".join(f"{l} {r:.0%}" for l, r in zip(labels, rec))}
            if name != REF:
                gain = lambda a, b: f1m(b) - f1m(a)
                lo, hi = _bootstrap([ref, d], "classification", gain)
                row["gain F1 vs actuel"] = round(gain(ref, d), 3)
                row["IC95 du gain"] = f"[{lo:+.3f} ; {hi:+.3f}]"
                row["verdict"] = "MIEUX" if lo > 0 else ("MOINS BIEN" if hi < 0 else "pas de diff. démontrée")
            rows.append(row)

res = pd.DataFrame(rows)
res.to_csv(RESULTS / "oversampling.csv", index=False)
print(res.fillna("").to_string(index=False))
