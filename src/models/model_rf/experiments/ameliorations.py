"""Mesure l'effet de chaque amélioration, séparément puis ensemble.

    python -m src.models.model_rf.experiments.ameliorations

RÈGLE FIXÉE AVANT DE LANCER (anti-surapprentissage) :
- toutes les variantes passent le même examen (mêmes sessions mises de côté) ;
- une amélioration n'est retenue QUE si l'IC 95 % de son gain est entièrement au-dessus de 0 ;
- sinon on garde la version la plus simple ;
- on ne relance pas avec d'autres réglages après avoir vu ces résultats.
"""
import warnings

import pandas as pd

from ..data_prep import load_tables
from ..metrics import _bootstrap, _main_score, oof_predictions
from ..families import FAMILIES
from ..forest import ForestModel, TunedForestModel

from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)

VARIANTS = {
    "v4 (base)":            (ForestModel, False),
    "+ variables physiques": (ForestModel, True),
    "+ réglage imbriqué":    (TunedForestModel, False),
    "v5 (les deux)":         (TunedForestModel, True),
}

tables = load_tables()
rows = []
for family, fiche in FAMILIES.items():
    for output in fiche["sorties"]:
        oof = {name: oof_predictions(tables, family, output, *v) for name, v in VARIANTS.items()}
        kind = oof["v4 (base)"][2]
        base = oof["v4 (base)"][0]
        sign = -1 if kind == "regression" else 1
        for name, (df, _, _) in oof.items():
            row = {"famille": family, "sortie": output, "variante": name,
                   "score": round(_main_score(df, kind), 4),
                   "mesure": "MAE (bas = mieux)" if kind == "regression" else "exact. équilibrée"}
            if kind == "regression":
                t = df["truth"]
                row["couverture_95"] = round(float(((t >= df["low"]) & (t <= df["high"])).mean()), 3)
            if name != "v4 (base)":
                gain = lambda a, b: sign * (_main_score(b, kind) - _main_score(a, kind))
                lo, hi = _bootstrap([base, df], kind, gain)
                row["gain_vs_v4"] = round(gain(base, df), 4)
                row["IC95_gain"] = f"[{lo:+.4f} ; {hi:+.4f}]"
                row["verdict"] = "MIEUX" if lo > 0 else ("MOINS BIEN" if hi < 0 else "pas de diff. démontrée")
            rows.append(row)
        print(f"fait : {family} / {output}")

res = pd.DataFrame(rows)
res.to_csv(RESULTS / "ameliorations.csv", index=False)
print()
print(res.fillna("").to_string(index=False))
