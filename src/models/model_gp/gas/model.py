"""Modèle des flammes gazeuses ACME CFI-G (PSI-159) : jet de gaz combustible dans une atmosphère contenant l'O2.

Seules les flammes « normales » sont utilisées (combustible dans le jet du brûleur, O2 dans la chambre) : c'est le cas
d'une fuite de gaz dans un habitat. Les flammes inverses (O2 injecté dans du combustible) sont exclues.

Deux probabilités, chacune avec un processus gaussien (classification) :
- allumage : une flamme chaude s'établit (Hot ignition = yes) ;
- auto-extinction, sachant qu'elle s'est allumée : la flamme s'éteint d'elle-même (SE), contre une flamme encore
  présente quand l'équipe coupe le débit (FT).
Variables : combustible (éthane, propane, n-butane), O2 de la chambre, pression, part de combustible dans le jet,
débit d'hydrocarbure. Incertitude : ré-échantillonnage par jour d'essai (intervalle à 90 %).

ACME CFI-G est la seule famille avec des essais réels près de l'atmosphère d'exploration (51 kPa, 33–39 % d'O2).
Limites : 11 jours d'essai seulement ; l'O2 de la chambre baisse au fil des essais d'une même journée ; pas de vitesse
d'air ambiant (brûleur sphérique en chambre calme). Validation : python -m src.models.model_gp.gas.evaluate.
"""

from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.data.build_unified import load_family

FUELS = ("ethane", "propane", "n-butane")
FEATURES = [f"is_{f.replace('-', '_')}" for f in FUELS] + ["x_o2", "pressure_kpa", "x_fuel", "hc_rate_mg_s"]
N_BOOTSTRAP = 20
SEED = 0
MIN_LENGTH_SCALE = 1.0  # contrainte : un peu meilleure en validation par jour d'essai (voir evaluate.py)
RELIABILITY = {
    "ignited": "low: AUC ≈ 0.66 in validation on unseen test days, accuracy below the majority class",
    "self_extinguished": "medium: AUC ≈ 0.76 in validation on unseen test days (accuracy 82% vs 77%)",
}
# Distance aux essais réels (unités physiques) pour montrer les essais les plus proches
NEAR_SCALES = {"x_o2": 0.02, "pressure_kpa": 10.0, "x_fuel": 0.1, "hc_rate_mg_s": 0.5}


def load_data():
    """Flammes normales ACME CFI-G avec une issue et toutes les variables (essais sans combustible exclus)."""
    g = load_family("gas")
    d = g[(g["experiment"] == "ACME CFI-G") & (g["flame_type"] == "normal") & g["outcome"].notna()].copy()
    for f in FUELS:
        d[f"is_{f.replace('-', '_')}"] = (d["fuel"] == f).astype(float)
    num = ["x_o2", "pressure_kpa", "x_fuel", "hc_rate_mg_s"]
    d[num] = d[num].astype(float)
    d = d.dropna(subset=num)
    d = d[(d["x_fuel"] > 0) & (d["hc_rate_mg_s"] > 0)]
    d["ignited"] = (d["hot_ignition_raw"] == "yes").astype(int)
    d["self_extinguished"] = np.where(d["ignited"] == 1, (d["end_mode_raw"] == "SE").astype(float), np.nan)
    return d.reset_index(drop=True)


def features(df):
    return df[FEATURES].to_numpy(dtype=float)


def make_classifier(min_length=None):
    low = MIN_LENGTH_SCALE if min_length is None else min_length
    kernel = ConstantKernel(1.0) * RBF(length_scale=np.ones(len(FEATURES)), length_scale_bounds=(low, 1e2))
    return make_pipeline(StandardScaler(), GaussianProcessClassifier(kernel=kernel, random_state=SEED))


def bootstrap_by_session(df, target, n=N_BOOTSTRAP, seed=SEED):
    rng = np.random.default_rng(seed)
    sessions = df["session"].unique()
    for _ in range(n):
        picked = rng.choice(sessions, size=len(sessions), replace=True)
        sample = pd.concat([df[df["session"] == s] for s in picked], ignore_index=True)
        if sample[target].nunique() == 2:
            yield sample


class GasModel:
    """Deux classifieurs : allumage (tous les essais) et auto-extinction (essais allumés)."""

    TARGETS = ("ignited", "self_extinguished")

    def __init__(self, df, n_bootstrap=N_BOOTSTRAP, min_length=None):
        self.df = df
        self.models, self.ensembles = {}, {}
        for target in self.TARGETS:
            data = df.dropna(subset=[target])
            self.models[target] = make_classifier(min_length).fit(features(data), data[target].astype(int))
            self.ensembles[target] = [make_classifier(min_length).fit(features(s), s[target].astype(int))
                                      for s in bootstrap_by_session(data, target, n_bootstrap)]
        self.ranges = {c: (float(df[c].min()), float(df[c].max())) for c in FEATURES[len(FUELS):]}

    def predict_frame(self, X):
        out = {}
        for target in self.TARGETS:
            p = self.models[target].predict_proba(X)[:, 1]
            ens = self.ensembles[target]
            boot = np.array([m.predict_proba(X)[:, 1] for m in ens]) if ens else p[None, :]
            out[f"p_{target}"] = p
            out[f"p_{target}_low"] = np.minimum(np.quantile(boot, 0.05, axis=0), p)  # l'intervalle contient la valeur annoncée
            out[f"p_{target}_high"] = np.maximum(np.quantile(boot, 0.95, axis=0), p)
        return pd.DataFrame(out)


@lru_cache(maxsize=1)
def trained_model():
    return GasModel(load_data())


def conditions_to_row(conditions):
    """conditions : fuel (ethane / propane / n-butane), o2_percent, pressure_kpa, x_fuel (0–1), hc_rate_mg_s."""
    fuel = conditions.get("fuel", "propane").lower().replace("butane", "n-butane").replace("n-n-", "n-")
    if fuel not in FUELS:
        raise ValueError(f"ACME CFI-G only tested {FUELS}; '{fuel}' is not covered")
    return np.array([[float(fuel == f) for f in FUELS]
                     + [conditions["o2_percent"] / 100, conditions["pressure_kpa"],
                        conditions.get("x_fuel", 0.3), conditions.get("hc_rate_mg_s", 1.0)]]), fuel


def predict(conditions):
    """Fuite de gaz dans une atmosphère donnée. Exemple :
    predict({"fuel": "propane", "o2_percent": 34, "pressure_kpa": 55, "x_fuel": 0.3, "hc_rate_mg_s": 1.0})
    """
    model = trained_model()
    X, fuel = conditions_to_row(conditions)
    r = model.predict_frame(X).iloc[0]
    warnings = []
    for key, value in zip(FEATURES[len(FUELS):], X[0, len(FUELS):]):
        lo, hi = model.ranges[key]
        if not lo - 1e-9 <= value <= hi + 1e-9:
            warnings.append(f"{key} = {value:g} is outside the range tested by ACME CFI-G ({lo:g} to {hi:g}): extrapolation")
    interval = lambda t: (round(float(r[f"p_{t}_low"]), 3), round(float(r[f"p_{t}_high"]), 3))
    return {
        "experiment": "ACME CFI-G (flammes normales)",
        "fuel": fuel,
        "p_hot_ignition": round(float(r["p_ignited"]), 3),
        "p_hot_ignition_interval_90": interval("ignited"),
        "p_hot_ignition_reliability": RELIABILITY["ignited"],
        "p_self_extinction_if_ignited": round(float(r["p_self_extinguished"]), 3),
        "p_self_extinction_interval_90": interval("self_extinguished"),
        "p_self_extinction_reliability": RELIABILITY["self_extinguished"],
        "nearest_tests": nearest_tests(model, X[0], k=5),
        "n_training_tests": len(model.df),
        "warnings": warnings,
    }


def nearest_tests(model, x, k=5):
    """Essais ACME CFI-G réels les plus proches (tous combustibles), en unités physiques (NEAR_SCALES)."""
    df = model.df
    cols = list(NEAR_SCALES)
    target = np.array([x[FEATURES.index(c)] for c in cols])
    d = np.sqrt(sum(((df[c].to_numpy(float) - t) / NEAR_SCALES[c]) ** 2 for c, t in zip(cols, target)))
    return [{"test_id": str(df.iloc[i]["test_id"]), "fuel": df.iloc[i]["fuel"], "o2_percent": round(float(df.iloc[i]["x_o2"]) * 100, 1),
             "pressure_kpa": round(float(df.iloc[i]["pressure_kpa"]), 1), "x_fuel": float(df.iloc[i]["x_fuel"]),
             "hc_rate_mg_s": float(df.iloc[i]["hc_rate_mg_s"]), "outcome": df.iloc[i]["outcome"],
             "distance": round(float(d[i]), 2)} for i in np.argsort(d)[:k]]
