"""Modèle FLEX : gouttelettes en microgravité (PSI-69, 274 essais sur l'ISS).

Deux modèles à processus gaussien, entraînés sur families/droplets.parquet (experiment == "FLEX") :
- extinction : probabilité que la flamme s'éteigne d'elle-même avant la fin de la combustion de la gouttelette
  (outcome == "extinguished") ; l'alternative est une flamme qui tient jusqu'au bout (completion ou disruption) ;
- K : constante de combustion (mm²/s), avec son écart-type.

Incertitude :
- extinction : intervalle à 90 % obtenu en ré-entraînant le modèle sur des tirages des jours d'essai (bootstrap par jour) ;
- K : écart-type du processus gaussien (bruit de mesure compris) ;
- « pas de donnée proche » si les conditions demandées sont loin de tous les essais (distance au plus proche voisin
  dans l'espace normalisé) ; alerte d'extrapolation hors des plages mesurées.

Limites : les essais FLEX ont été choisis pour encadrer les limites d'extinction (pas un plan d'expérience
uniforme) ; uniquement heptane et méthanol ; pression de 70 à 309 kPa ; aucune donnée en gravité partielle.
Dans ces données, la pression n'influence presque pas l'extinction (longueur de corrélation au maximum) : sous 70 kPa
(atmosphère d'exploration ≈ 55 kPa), le modèle prolonge cette absence d'effet sans pouvoir la vérifier.

Validation : python -m src.models.evaluate_flex (résultats dans docs/modele_flex_validation.md).
L'entraînement complet prend ~25 s (20 ré-échantillonnages) : à mettre en cache dans l'app (st.cache_resource).
"""

from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessClassifier, GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.data.build_unified import load_family

FEATURES = ["is_heptane", "x_o2", "pressure_kpa", "x_co2", "x_he", "d0_mm"]
FUELS = ("heptane", "methanol")
N_BOOTSTRAP = 20
SEED = 0


# ---------- Données ----------

def load_data():
    """Essais FLEX utilisables : toutes les variables présentes (les valeurs manquantes ne sont pas remplies)."""
    d = load_family("droplets")
    f = d[d["experiment"] == "FLEX"].copy()
    f["is_heptane"] = (f["fuel"] == "heptane").astype(float)
    f["extinguished"] = (f["outcome"] == "extinguished").astype(int)
    num = FEATURES[1:]
    f[num] = f[num].astype(float)
    f["burning_rate_mm2_s"] = f["burning_rate_mm2_s"].astype(float)
    return f.dropna(subset=FEATURES + ["outcome"]).reset_index(drop=True)


def features(df):
    return df[FEATURES].to_numpy(dtype=float)


# ---------- Modèles ----------

def make_classifier():
    kernel = ConstantKernel(1.0) * RBF(length_scale=np.ones(len(FEATURES)), length_scale_bounds=(1e-2, 1e2))
    return make_pipeline(StandardScaler(), GaussianProcessClassifier(kernel=kernel, random_state=SEED))


def make_regressor():
    kernel = (ConstantKernel(1.0) * RBF(length_scale=np.ones(len(FEATURES)), length_scale_bounds=(1e-2, 1e2))
              + WhiteKernel(1e-2, noise_level_bounds=(1e-5, 1.0)))
    return make_pipeline(StandardScaler(), GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=SEED))


def bootstrap_by_session(df, n=N_BOOTSTRAP, seed=SEED):
    """Tirages avec remise des jours d'essai (les essais d'un même jour restent ensemble)."""
    rng = np.random.default_rng(seed)
    sessions = df["session"].unique()
    for _ in range(n):
        picked = rng.choice(sessions, size=len(sessions), replace=True)
        sample = pd.concat([df[df["session"] == s] for s in picked], ignore_index=True)
        if sample["extinguished"].nunique() == 2:
            yield sample


class FlexModel:
    """Modèles entraînés sur un ensemble d'essais FLEX."""

    def __init__(self, df, n_bootstrap=N_BOOTSTRAP):
        self.df = df
        X = features(df)
        self.classifier = make_classifier().fit(X, df["extinguished"])
        self.ensemble = [make_classifier().fit(features(s), s["extinguished"]) for s in bootstrap_by_session(df, n_bootstrap)]
        k = df.dropna(subset=["burning_rate_mm2_s"])
        self.regressor = make_regressor().fit(features(k), k["burning_rate_mm2_s"])
        # Distance de référence : plus proche voisin de chaque essai parmi les autres (espace normalisé)
        self.scaler = StandardScaler().fit(X)
        Z = self.scaler.transform(X)
        dist = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(-1))
        np.fill_diagonal(dist, np.inf)
        self.nn_reference = float(np.quantile(dist.min(axis=1), 0.95))
        self.Z = Z
        self.ranges = {c: (float(df[c].min()), float(df[c].max())) for c in FEATURES[1:]}

    def predict_frame(self, X):
        """Pour chaque ligne de X : probabilité d'extinction, intervalle à 90 %, K et écart-type, distance aux données."""
        p = self.classifier.predict_proba(X)[:, 1]
        boot = np.array([m.predict_proba(X)[:, 1] for m in self.ensemble]) if self.ensemble else p[None, :]
        k_mean, k_std = self.regressor.predict(X, return_std=True)
        Z = self.scaler.transform(X)
        nn = np.sqrt(((Z[:, None, :] - self.Z[None, :, :]) ** 2).sum(-1)).min(axis=1)
        return pd.DataFrame({
            "p_extinction": p,
            "p_low": np.quantile(boot, 0.05, axis=0),
            "p_high": np.quantile(boot, 0.95, axis=0),
            "k_mm2_s": k_mean,
            "k_std": k_std,
            "nn_distance": nn,
            "near_data": nn <= self.nn_reference,
        })


@lru_cache(maxsize=1)
def trained_model():
    """Modèle entraîné sur tous les essais FLEX (gardé en mémoire)."""
    return FlexModel(load_data())


# ---------- Prédiction pour l'app ----------

def conditions_to_row(conditions):
    """conditions : fuel ('heptane' / 'methanol'), o2_percent, pressure_kpa, co2_percent=0, he_percent=0, d0_mm=3.0."""
    fuel = conditions.get("fuel", "heptane").lower()
    if fuel not in FUELS:
        raise ValueError(f"FLEX n'a testé que {FUELS} ; « {fuel} » n'est pas couvert")
    return np.array([[
        1.0 if fuel == "heptane" else 0.0,
        conditions["o2_percent"] / 100,
        conditions["pressure_kpa"],
        conditions.get("co2_percent", 0.0) / 100,
        conditions.get("he_percent", 0.0) / 100,
        conditions.get("d0_mm", 3.0),
    ]])


def predict(conditions):
    """Prédiction FLEX pour des conditions d'ambiance. Exemple :
    predict({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0})
    """
    model = trained_model()
    X = conditions_to_row(conditions)
    r = model.predict_frame(X).iloc[0]
    warnings = []
    for c, value in zip(FEATURES[1:], X[0, 1:]):
        lo, hi = model.ranges[c]
        if not lo - 1e-9 <= value <= hi + 1e-9:
            warnings.append(f"{c} = {value:g} hors de la plage mesurée par FLEX ({lo:g} à {hi:g}) : extrapolation ; "
                            "l'intervalle affiché ne tient pas compte de cette extrapolation (il est sous-estimé)")
    if not r["near_data"]:
        warnings.append("pas de donnée proche : aucun essai FLEX dans des conditions voisines, la prédiction est peu fiable")
    return {
        "experiment": "FLEX",
        "p_extinction": round(float(r["p_extinction"]), 3),
        "p_extinction_interval_90": (round(float(r["p_low"]), 3), round(float(r["p_high"]), 3)),
        "burning_rate_k_mm2_s": round(float(r["k_mm2_s"]), 3),
        "burning_rate_k_std": round(float(r["k_std"]), 3),
        "nearest_data_distance": round(float(r["nn_distance"]), 2),
        "near_data": bool(r["near_data"]),
        "warnings": warnings,
        "n_training_tests": len(model.df),
    }
