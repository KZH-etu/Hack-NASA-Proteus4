"""Démonstration de bout en bout sur les vraies données (data/processed/*.parquet).

    python -m src.models.model_rf.experiments.run_demo
"""
import warnings

import pandas as pd

from ..service import MLService
from ..data_prep import load_tables
from ..metrics import compare
from ..forest import ForestModel, ForestModelBasic

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)

tables = load_tables()
print("Tables chargées :", {k: len(v) for k, v in tables.items()})

print("\n=== 1. Évaluation par session : version de base vs version améliorée ===")
res = compare(tables, model_classes=(ForestModelBasic, ForestModel))
cols = ["famille", "sortie", "modele", "n_essais", "validation", "exactitude_modele", "exactitude_reference",
        "exactitude_equilibree", "detection_par_issue", "ecart_fiabilite",
        "MAE_modele", "MAE_reference", "couverture_95", "bat_la_reference"]
print(res[[c for c in cols if c in res]].round(3).to_string(index=False))

ml = MLService(tables)
print("\n=== 2. Familles disponibles ===", ml.list_families(), "| ignorées :", ml.skipped)

for family in ml.list_families():
    scenario = ml.default_scenario(family)
    print(f"\n{'=' * 100}\n### {family}\nParamètres : ")
    for k, v in ml.get_parameters(family).items():
        print(f"   {k}: {v}")
    print(f"Scénario (valeurs typiques) : {scenario}")
    out = ml.predict(family, scenario)
    for name, r in out["resultats"].items():
        print(f"   -> {name}: {r}")
    print("   donnée proche :", out["donnee_proche"], out.get("avertissement", ""))
    print("   essais réels les plus proches :")
    print(out["essais_proches"].round(3).to_string(index=False))
    print("   prochaines expériences recommandées :")
    print(ml.recommend_next_experiment(family, scenario).round(3).to_string(index=False))
