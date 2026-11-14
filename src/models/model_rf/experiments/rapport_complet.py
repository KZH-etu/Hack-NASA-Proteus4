"""Toutes les mesures, pour chaque famille.

    python -m src.models.model_rf.experiments.rapport_complet       -> affiche + src/models/model_rf/results/rapport_complet.txt

Familles avec modèle : mesures sur des sessions JAMAIS vues par le modèle.
Familles sans modèle : description des données (il n'y a rien à mesurer côté prédiction).
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ..data_only import DataExplorer
from ..data_prep import load_tables
from ..metrics import _bootstrap, classification_report_fr, evaluate, oof_predictions
from ..families import FAMILIES
from ..forest import model_for

from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"

warnings.filterwarnings("ignore")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

tables = load_tables()
lines = []
say = lambda s="": (print(s), lines.append(str(s)))

for family, fiche in FAMILIES.items():
    for output, spec in fiche["sorties"].items():
        cls = model_for(family, output)
        ev = evaluate(tables, family, output, cls)
        say(f"\n{'=' * 90}\n{family} — {output} — {cls.name}\n{ev['n_essais']} essais, validation {ev['validation']}")
        if spec["type"] == "classification":
            rep = classification_report_fr(tables, family, output, cls)
            lo, hi = rep.attrs["f1_macro_IC95"]
            say(rep.round(3).fillna("").to_string(index=False))
            say(f"F1 macro IC 95 %             : [{lo:.3f} ; {hi:.3f}]")
            say(f"Exactitude équilibrée        : {ev['exactitude_equilibree']:.3f}  IC {ev['equilibree_IC95']}")
            say(f"Accuracy référence naïve     : {ev['exactitude_reference']:.3f}  (toujours « l'issue la plus fréquente »)")
            n = len(rep) - 3
            say(f"F1 macro référence naïve     : {2 * ev['exactitude_reference'] / (1 + ev['exactitude_reference']) / n:.3f}")
            say(f"Écart de fiabilité (0 = parfait) : {ev['ecart_fiabilite']:.3f}")
            say("Matrice de confusion (lignes = vraie issue, colonnes = prédite) :")
            say(rep.attrs["confusion"].to_string())
        else:
            df, _, _ = oof_predictions(tables, family, output, cls)
            t, p = df["truth"].to_numpy(), df["pred"].to_numpy()
            rmse = lambda d: np.sqrt(mean_squared_error(d["truth"], d["pred"]))
            r2 = lambda d: r2_score(d["truth"], d["pred"])
            lo_r, hi_r = _bootstrap([df], "regression", rmse)
            lo_2, hi_2 = _bootstrap([df], "regression", r2)
            naive = df["naive"].to_numpy()
            say(f"MAE (erreur moyenne)         : {ev['MAE_modele']:.4f}  IC {ev['MAE_IC95']}   | référence {ev['MAE_reference']:.4f}")
            say(f"RMSE (punit les grosses erreurs) : {rmse(df):.4f}  IC [{lo_r:.4f} ; {hi_r:.4f}] | référence {np.sqrt(mean_squared_error(t, naive)):.4f}")
            say(f"R² (1 = parfait, 0 = référence)  : {r2(df):.3f}  IC [{lo_2:.3f} ; {hi_2:.3f}]")
            say(f"Erreur relative moyenne      : {np.mean(np.abs(t - p) / np.abs(t)):.1%}")
            say(f"Couverture de l'intervalle 95 % : {ev['couverture_95']:.1%}")
            say(f"Largeur moyenne de l'intervalle : {np.mean(df['high'] - df['low']):.4f}  (valeurs de {t.min():.2f} à {t.max():.2f})")

ex = DataExplorer(tables)
for family in ex.list_families():
    rows = ex.rows[family]
    say(f"\n{'=' * 90}\n{family} — PAS DE MODÈLE (données réelles seulement)")
    say(f"{len(rows)} essais en microgravité, {rows['session'].nunique()} sessions, "
        f"{rows['material'].nunique()} matériaux")
    if "outcome" in rows:
        say("Issues : " + str(rows["outcome"].fillna("non renseigné").value_counts().to_dict()))
    if "extinction_flow_cm_s" in rows:
        say(f"Vitesse d'air à l'extinction connue : {rows['extinction_flow_cm_s'].notna().sum()} essais")
    say(ex.summary(family).to_string())

open(RESULTS / "rapport_complet.txt", "w").write("\n".join(lines))
