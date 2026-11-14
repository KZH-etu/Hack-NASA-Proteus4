"""Fonctions communes aux sous-dossiers de famille (flex, gas, solids, aerosols)."""
import warnings

import pandas as pd

from .data_prep import load_tables, prepare_xy
from .families import FAMILIES
from .forest import model_for
from .metrics import evaluate, fit_model


def build_models(family: str, tables: dict | None = None) -> dict:
    """Entraîne les modèles d'une famille sur toutes ses données : {sortie: modèle}."""
    tables = tables if tables is not None else load_tables()
    models = {}
    for output, spec in FAMILIES[family]["sorties"].items():
        X, y, groups, _ = prepare_xy(tables, family, output)
        models[output] = fit_model(model_for(family, output), spec["type"], family, X, y, groups)
    return models


def print_family_report(family: str):
    """Toutes les mesures de la famille, sur des sessions jamais vues par le modèle."""
    import numpy as np
    from sklearn.metrics import mean_squared_error, r2_score

    from .metrics import _bootstrap, classification_report_fr, oof_predictions

    warnings.filterwarnings("ignore")
    pd.set_option("display.width", 200)
    tables = load_tables()
    for output, spec in FAMILIES[family]["sorties"].items():
        cls = model_for(family, output)
        ev = evaluate(tables, family, output, cls)
        print(f"\n=== {family} — {output} — {cls.name} ===")
        print(f"{ev['n_essais']} essais, validation {ev['validation']}, bat la référence : {ev['bat_la_reference']}")
        if spec["type"] == "classification":
            rep = classification_report_fr(tables, family, output, cls)
            lo, hi = rep.attrs["f1_macro_IC95"]
            print(rep.round(3).fillna("").to_string(index=False))
            print(f"F1 macro IC 95 % : [{lo:.3f} ; {hi:.3f}]")
            print(f"Accuracy référence naïve : {ev['exactitude_reference']:.3f}")
            print(f"Écart de fiabilité : {ev['ecart_fiabilite']:.3f}")
            print("Matrice de confusion (lignes = vraie issue, colonnes = prédite) :")
            print(rep.attrs["confusion"].to_string())
        else:
            df, _, _ = oof_predictions(tables, family, output, cls)
            rmse = lambda d: np.sqrt(mean_squared_error(d["truth"], d["pred"]))
            lo, hi = _bootstrap([df], "regression", lambda d: r2_score(d["truth"], d["pred"]))
            print(f"MAE  : {ev['MAE_modele']:.4f}  IC {ev['MAE_IC95']}  | référence {ev['MAE_reference']:.4f}")
            print(f"RMSE : {rmse(df):.4f}")
            print(f"R²   : {r2_score(df['truth'], df['pred']):.3f}  IC [{lo:.3f} ; {hi:.3f}]")
            print(f"Couverture de l'intervalle 95 % : {ev['couverture_95']:.1%}")
