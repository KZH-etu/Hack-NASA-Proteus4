"""Recommandation de la prochaine expérience ISS (gouttelettes, modèle FLEX).

Idée : autour d'un scénario de mission (ex. habitat lunaire à 34 % d'O2 et ~55 kPa), chercher les conditions d'essai
qui apprendraient le plus au modèle sur ce scénario. Pour chaque condition candidate d'une grille autour du scénario :

    score = pertinence × (incertitude + nouveauté)

- pertinence : proximité avec le scénario, exp(-d²/2), d mesurée en unités physiques (SCENARIO_SCALES) ;
- incertitude : largeur de l'intervalle à 90 % de la probabilité d'extinction (ré-échantillonnage par jour d'essai) ;
- nouveauté : 1 - exp(-d / 2), d = distance au plus proche essai FLEX réel du même combustible (COVERAGE_SCALES).
  Nécessaire car l'incertitude du modèle ne grandit pas hors des données (ex. pression sous 70 kPa).

Les recommandations sont choisies une à une : chaque essai recommandé compte ensuite comme « couvert », pour que les
suivantes explorent d'autres zones. Chaque recommandation est expliquée (composantes du score, essai réel le plus proche).
"""

import numpy as np
import pandas as pd

from src.models.flex.model import FEATURES, FUELS, conditions_to_row, predict, trained_model

# Distance « couverture » : écart à partir duquel deux essais sont considérés comme vraiment différents
COVERAGE_SCALES = {"x_o2": 0.02, "pressure_kpa": 10.0, "x_co2": 0.05, "x_he": 0.05, "d0_mm": 0.5}
# Distance « pertinence » : à quel point un essai s'éloigne du scénario de mission
SCENARIO_SCALES = {"x_o2": 0.04, "pressure_kpa": 20.0, "x_co2": 0.10, "x_he": 0.10, "d0_mm": 1.0}
# Grille de candidats autour du scénario (écarts en points d'O2 et en kPa)
O2_SPAN, O2_STEP = (-8, 6), 1.0
P_SPAN, P_STEP = (-25, 50), 5.0
P_MIN = 30.0  # pas de candidat sous 30 kPa


def _scaled(values, scales):
    return np.column_stack([values[:, FEATURES.index(c)] / s for c, s in scales.items()])


def candidate_grid(scenario):
    """Conditions candidates : O2 et pression autour du scénario ; combustible, CO2, He et diamètre fixés."""
    base = conditions_to_row(scenario)[0]
    o2 = np.arange(scenario["o2_percent"] + O2_SPAN[0], scenario["o2_percent"] + O2_SPAN[1] + 1e-9, O2_STEP)
    p = np.arange(max(P_MIN, scenario["pressure_kpa"] + P_SPAN[0]), scenario["pressure_kpa"] + P_SPAN[1] + 1e-9, P_STEP)
    rows = []
    for o in o2[o2 > 0]:
        for pk in p:
            row = base.copy()
            row[FEATURES.index("x_o2")] = o / 100
            row[FEATURES.index("pressure_kpa")] = pk
            rows.append(row)
    return np.array(rows)


def nearest_tests(model, X_point, fuel_flag, k=3):
    """Essais FLEX réels les plus proches (même combustible) d'un point, en unités de couverture."""
    df = model.df[model.df["is_heptane"] == fuel_flag]
    d = np.sqrt(((_scaled(df[FEATURES].to_numpy(float), COVERAGE_SCALES) - _scaled(X_point[None, :], COVERAGE_SCALES)) ** 2).sum(1))
    order = np.argsort(d)[:k]
    return [{
        "test_id": str(df.iloc[i]["test_id"]),
        "o2_percent": round(float(df.iloc[i]["x_o2"]) * 100, 1),
        "pressure_kpa": round(float(df.iloc[i]["pressure_kpa"]), 1),
        "co2_percent": round(float(df.iloc[i]["x_co2"]) * 100, 1),
        "he_percent": round(float(df.iloc[i]["x_he"]) * 100, 1),
        "d0_mm": round(float(df.iloc[i]["d0_mm"]), 2),
        "outcome": str(df.iloc[i]["outcome"]),
        "distance": round(float(d[i]), 2),
    } for i in order]


def recommend_next_experiment(scenario, n=5):
    """Recommandations d'essais FLEX autour d'un scénario de mission. Exemple :
    recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0})
    Point d'entrée commun à toutes les familles : src/models/recommend.py.
    """
    fuel = scenario.get("fuel", "heptane").lower()
    if fuel not in FUELS:
        raise ValueError(f"FLEX n'a testé que {FUELS} ; « {fuel} » n'est pas couvert")
    model = trained_model()
    fuel_flag = 1.0 if fuel == "heptane" else 0.0
    X = candidate_grid(scenario)
    pred = model.predict_frame(X)
    target = conditions_to_row(scenario)[0]

    relevance = np.exp(-0.5 * ((_scaled(X, SCENARIO_SCALES) - _scaled(target[None, :], SCENARIO_SCALES)) ** 2).sum(1))
    uncertainty = (pred["p_high"] - pred["p_low"]).to_numpy()
    covered = _scaled(model.df.loc[model.df["is_heptane"] == fuel_flag, FEATURES].to_numpy(float), COVERAGE_SCALES)
    Xs = _scaled(X, COVERAGE_SCALES)

    picks, available = [], np.ones(len(X), dtype=bool)
    for _ in range(min(n, len(X))):
        nn = np.sqrt(((Xs[:, None, :] - covered[None, :, :]) ** 2).sum(-1)).min(axis=1)
        novelty = 1 - np.exp(-nn / 2)
        score = relevance * (uncertainty + novelty)
        score[~available] = -np.inf
        i = int(np.argmax(score))
        available[i] = False
        covered = np.vstack([covered, Xs[i]])  # l'essai recommandé compte comme couvert pour les suivants
        x = X[i]
        near = nearest_tests(model, x, fuel_flag, k=1)[0]
        picks.append({
            "rank": len(picks) + 1,
            "conditions": {"fuel": fuel, "o2_percent": round(float(x[1]) * 100, 1), "pressure_kpa": round(float(x[2]), 1),
                           "co2_percent": round(float(x[3]) * 100, 1), "he_percent": round(float(x[4]) * 100, 1),
                           "d0_mm": round(float(x[5]), 2)},
            "score": round(float(score[i]), 3),
            "relevance": round(float(relevance[i]), 3),
            "uncertainty": round(float(uncertainty[i]), 3),
            "novelty": round(float(novelty[i]), 3),
            "p_extinction": round(float(pred["p_extinction"].iloc[i]), 3),
            "p_extinction_interval_90": (round(float(pred["p_low"].iloc[i]), 3), round(float(pred["p_high"].iloc[i]), 3)),
            "nearest_flex_test": near,
            "why": _explain(x, near, model, uncertainty[i], novelty[i]),
        })
    return {
        "scenario": scenario,
        "scenario_prediction": predict(scenario),
        "nearest_flex_tests": nearest_tests(model, target, fuel_flag, k=3),
        "recommendations": picks,
        "method": "score = pertinence × (incertitude + nouveauté) ; voir src/models/flex/recommend.py",
    }


def _explain(x, near, model, uncertainty, novelty):
    reasons = []
    lo_p = model.ranges["pressure_kpa"][0]
    if x[2] < lo_p:
        reasons.append(f"aucun essai FLEX sous {lo_p:.0f} kPa")
    if novelty > 0.5:
        reasons.append(f"essai réel le plus proche loin (n° {near['test_id']} : {near['o2_percent']} % O2, "
                       f"{near['pressure_kpa']} kPa, issue {near['outcome']})")
    if uncertainty > 0.3:
        reasons.append(f"modèle incertain (intervalle de probabilité d'extinction large de {uncertainty:.2f})")
    return " ; ".join(reasons) or "proche du scénario, complète les essais existants"


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    scenario = {"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0}
    print(json.dumps(recommend_next_experiment(scenario), ensure_ascii=False, indent=1, default=str))
