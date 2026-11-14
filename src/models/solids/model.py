"""Modèle des solides (BASS, BASS-II) : carte d'inflammabilité en microgravité et prochaine expérience.

Pourquoi pas l'issue de l'essai comme cible : la plupart des essais BASS-II ont été menés jusqu'à l'extinction en
baissant volontairement le débit ; « éteint » décrit la procédure, pas un risque. L'information utile est dans la
séquence des vitesses d'air affichées pendant l'essai (« 10 5 3 2 ext ») : la flamme a tenu à 10, 5 et 3 cm/s, puis
s'est éteinte à 2. Chaque essai donne donc plusieurs observations (matériau, O2, vitesse d'air) -> la flamme tient ou non.

Règles d'étiquetage (essais dont l'issue est connue ; vitesses lues par src.data.solids.flow_sequence) :
- flamme qui tient : chaque vitesse affichée avant l'extinction (0 exclu : débit coupé) ; toutes si l'issue est `burned` ;
- flamme qui ne tient pas : vitesse suivie de « ext » / « blowoff », vitesse d'extinction écrite en cm/s, et toutes les
  vitesses des essais où la flamme ne s'établit pas (`brief_flame`, `no_ignition`) ;
- extinction à un réglage du potentiomètre sous la dernière vitesse affichée : on garde seulement les points « tient »
  (la vitesse d'extinction n'est pas connue en cm/s, elle n'est pas inventée) ;
- essai éteint sans mode connu : non utilisé.

Modèle : processus gaussien (classification) P(la flamme tient | groupe de matériau, O2, log de la vitesse d'air),
longueurs de corrélation ≥ 1 (en données normalisées) pour que l'O2, qui varie un peu chaque jour, ne serve pas
d'identifiant du jour. Incertitude : ré-échantillonnage par jour d'essai (intervalle à 90 %).

**Fiabilité faible** : en validation par jour d'essai, AUC ≈ 0,59 (meilleure variante testée ; détail dans
src/models/solids/validation.md). Les données BASS-II ne suffisent pas à prédire si une flamme tient d'un jour à
l'autre. `predict()` le dit ; la recommandation repose surtout sur la nouveauté (distance aux essais existants).
Limite majeure : O2 de 14 à 22 % seulement ; pression ~1 atm ; aucun essai solide en atmosphère enrichie en O2.
"""

from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF, ConstantKernel
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.data.build_unified import load_family
from src.data.solids import flow_sequence

MATERIAL_CLASSES = ("pmma_thin", "pmma_thick", "pmma_rod", "pmma_sphere", "sibal", "other")
# Groupes utilisés par le modèle (trop peu d'observations pour 6 classes)
MATERIAL_GROUPS = {"pmma_flat": ("pmma_thin", "pmma_thick"), "pmma_rod_sphere": ("pmma_rod", "pmma_sphere"),
                   "fabric_other": ("sibal", "other")}
FEATURES = [f"is_{g}" for g in MATERIAL_GROUPS] + ["x_o2", "log_flow"]
N_BOOTSTRAP = 20
SEED = 0
THIN_MM = 0.5  # PMMA « mince » : film ou plaque jusqu'à 0,5 mm
MIN_LENGTH_SCALE = 1.0
RELIABILITY = ("faible : en validation par jour d'essai, AUC ≈ 0,59 (0,5 = hasard) ; "
               "à ne pas utiliser pour décider (voir src/models/solids/validation.md)")

# Recommandation : unités de couverture et de pertinence (O2 en fraction, débit en log)
COVERAGE_SCALES = {"x_o2": 0.02, "log_flow": 0.4}
SCENARIO_SCALES = {"x_o2": 0.04, "log_flow": 0.7}
O2_SPAN, O2_STEP = (-14, 6), 1.0
FLOWS = (1, 2, 3, 5, 7, 10, 15, 20, 30, 40)


def material_class(row):
    if row["material"] == "pmma":
        if row["geometry"] == "rod":
            return "pmma_rod"
        if row["geometry"] in ("sphere", "spherical section"):
            return "pmma_sphere"
        thickness = row["thickness_mm"]
        return "pmma_thin" if pd.notna(thickness) and thickness <= THIN_MM else "pmma_thick"
    return "sibal" if row["material"] == "sibal" else "other"


def material_group(cls):
    return next(g for g, members in MATERIAL_GROUPS.items() if cls in members)


def observations():
    """Une ligne par (essai, vitesse d'air affichée) avec l'étiquette « la flamme tient » (1) ou non (0)."""
    s = load_family("solids")
    s = s[s["experiment"].isin(["BASS", "BASS-II"]) & s["outcome"].notna() & s["x_o2"].notna()]
    rows = []
    for _, t in s.iterrows():
        raw = t["flow_raw"] if pd.notna(t["flow_raw"]) else ""
        seq = [(speed, words) for speed, words, upper in flow_sequence(raw) if not upper]
        na_free = lambda v: None if pd.isna(v) else v
        mode, outcome, ext_flow = na_free(t["extinction_mode"]), t["outcome"], na_free(t["extinction_flow_cm_s"])
        if not seq or (outcome == "extinguished" and mode is None):
            continue
        base = {"test_id": t["test_id"], "experiment": t["experiment"], "session": t["session"],
                "material_class": material_class(t), "flow_direction": t["flow_direction"], "x_o2": float(t["x_o2"]),
                "mode": mode, "outcome": outcome}
        last_ext = max((i for i, (v, _) in enumerate(seq) if v == ext_flow), default=None) if ext_flow is not None else None
        for k, (speed, words) in enumerate(seq):
            text = " ".join(words)
            if outcome == "no_ignition" or mode == "brief_flame":
                label = 0
            elif outcome == "burned":
                label = 1
            elif "ext" in text or "blow" in text or k == last_ext:
                label = 0
            else:
                label = 1
            if speed > 0:  # 0 : débit coupé, pas une condition d'essai
                rows.append({**base, "flow_cm_s": speed, "sustained": label})
        # Vitesse d'extinction écrite seulement dans les observations (« extinguished at 18 cm/s »)
        if ext_flow is not None and ext_flow > 0 and last_ext is None:
            rows.append({**base, "flow_cm_s": float(ext_flow), "sustained": 0})
    obs = pd.DataFrame(rows)
    obs["material_group"] = obs["material_class"].map(material_group)
    for g in MATERIAL_GROUPS:
        obs[f"is_{g}"] = (obs["material_group"] == g).astype(float)
    obs["log_flow"] = np.log(obs["flow_cm_s"])
    return obs


def features(df):
    return df[FEATURES].to_numpy(dtype=float)


def make_classifier():
    kernel = ConstantKernel(1.0) * RBF(length_scale=np.ones(len(FEATURES)), length_scale_bounds=(MIN_LENGTH_SCALE, 1e2))
    return make_pipeline(StandardScaler(), GaussianProcessClassifier(kernel=kernel, random_state=SEED))


def bootstrap_by_session(df, n=N_BOOTSTRAP, seed=SEED):
    rng = np.random.default_rng(seed)
    sessions = df["session"].unique()
    for _ in range(n):
        picked = rng.choice(sessions, size=len(sessions), replace=True)
        sample = pd.concat([df[df["session"] == s] for s in picked], ignore_index=True)
        if sample["sustained"].nunique() == 2:
            yield sample


class SolidsModel:
    def __init__(self, df, n_bootstrap=N_BOOTSTRAP):
        self.df = df
        self.classifier = make_classifier().fit(features(df), df["sustained"])
        self.ensemble = [make_classifier().fit(features(s), s["sustained"]) for s in bootstrap_by_session(df, n_bootstrap)]
        self.ranges = {"x_o2": (float(df["x_o2"].min()), float(df["x_o2"].max())),
                       "flow_cm_s": (float(df["flow_cm_s"].min()), float(df["flow_cm_s"].max()))}

    def predict_frame(self, X):
        p = self.classifier.predict_proba(X)[:, 1]
        boot = np.array([m.predict_proba(X)[:, 1] for m in self.ensemble]) if self.ensemble else p[None, :]
        # l'intervalle contient toujours la valeur annoncée
        return pd.DataFrame({"p_sustained": p, "p_low": np.minimum(np.quantile(boot, 0.05, axis=0), p),
                             "p_high": np.maximum(np.quantile(boot, 0.95, axis=0), p)})


@lru_cache(maxsize=1)
def trained_model():
    return SolidsModel(observations())


def conditions_to_row(conditions):
    """conditions : material (groupe de MATERIAL_GROUPS ou classe de MATERIAL_CLASSES), o2_percent, flow_cm_s."""
    material = conditions.get("material", "pmma_flat")
    group = material if material in MATERIAL_GROUPS else material_group(material) if material in MATERIAL_CLASSES else None
    if group is None:
        raise ValueError(f"matériau inconnu « {material} » ; groupes : {tuple(MATERIAL_GROUPS)} ; classes : {MATERIAL_CLASSES}")
    return np.array([[float(group == g) for g in MATERIAL_GROUPS]
                     + [conditions["o2_percent"] / 100, np.log(max(conditions["flow_cm_s"], 0.1))]]), group


def predict(conditions):
    """Probabilité que la flamme tienne sur un solide en microgravité (fiabilité faible, voir RELIABILITY). Exemple :
    predict({"material": "pmma_flat", "o2_percent": 21, "flow_cm_s": 10})
    """
    model = trained_model()
    X, group = conditions_to_row(conditions)
    r = model.predict_frame(X).iloc[0]
    warnings = [f"fiabilité du modèle {RELIABILITY}"]
    for key, value in (("x_o2", conditions["o2_percent"] / 100), ("flow_cm_s", conditions["flow_cm_s"])):
        lo, hi = model.ranges[key]
        if not lo - 1e-9 <= value <= hi + 1e-9:
            warnings.append(f"{key} = {value:g} hors de la plage mesurée par BASS / BASS-II ({lo:g} à {hi:g}) : extrapolation")
    no_data = not _o2_in_range(model, conditions["o2_percent"] / 100)
    if no_data:
        warnings.append("pas de donnée : aucun essai solide à ce niveau d'O2 ; loin des données, le modèle revient à 0,5 "
                        "(absence d'information, pas une prédiction) : aucune probabilité n'est donnée")
    return {
        "experiment": "BASS / BASS-II",
        "material_group": group,
        "p_flame_sustained": None if no_data else round(float(r["p_sustained"]), 3),
        "p_flame_sustained_interval_90": None if no_data else (round(float(r["p_low"]), 3), round(float(r["p_high"]), 3)),
        "reliable": False,
        "n_observations_same_group": int((model.df["material_group"] == group).sum()),
        "warnings": warnings,
    }


def _o2_in_range(model, x_o2):
    lo, hi = model.ranges["x_o2"]
    return lo - 1e-9 <= x_o2 <= hi + 1e-9


# ---------- Prochaine expérience ----------

def _scaled(o2, log_flow, scales):
    return np.column_stack([np.asarray(o2) / scales["x_o2"], np.asarray(log_flow) / scales["log_flow"]])


def nearest_tests(model, group, o2, flow, k=3):
    """Observations réelles les plus proches (même groupe de matériau) en unités de couverture."""
    df = model.df[model.df["material_group"] == group]
    d = np.sqrt(((_scaled(df["x_o2"], df["log_flow"], COVERAGE_SCALES) - _scaled([o2], [np.log(flow)], COVERAGE_SCALES)) ** 2).sum(1))
    order = np.argsort(d)[:k]
    return [{"test_id": str(df.iloc[i]["test_id"]), "material_class": df.iloc[i]["material_class"],
             "o2_percent": round(float(df.iloc[i]["x_o2"]) * 100, 1), "flow_cm_s": float(df.iloc[i]["flow_cm_s"]),
             "flame_sustained": bool(df.iloc[i]["sustained"]), "distance": round(float(d[i]), 2)} for i in order]


def recommend_next_experiment(scenario, n=5):
    """Essais solides recommandés autour d'un scénario. Exemple :
    recommend_next_experiment({"material": "pmma_flat", "o2_percent": 34, "flow_cm_s": 10})
    score = pertinence × (incertitude + nouveauté), comme pour FLEX (src/models/flex/recommend.py) ; la nouveauté domine
    car le modèle est peu fiable.
    """
    model = trained_model()
    _, group = conditions_to_row(scenario)
    o2_target, flow_target = scenario["o2_percent"] / 100, scenario["flow_cm_s"]
    o2 = np.arange(scenario["o2_percent"] + O2_SPAN[0], scenario["o2_percent"] + O2_SPAN[1] + 1e-9, O2_STEP) / 100
    grid = [(o, f) for o in o2[o2 > 0] for f in FLOWS]
    X = np.array([[float(group == g) for g in MATERIAL_GROUPS] + [o, np.log(f)] for o, f in grid])
    pred = model.predict_frame(X)
    G = _scaled(X[:, -2], X[:, -1], SCENARIO_SCALES)
    relevance = np.exp(-0.5 * ((G - _scaled([o2_target], [np.log(flow_target)], SCENARIO_SCALES)) ** 2).sum(1))
    uncertainty = (pred["p_high"] - pred["p_low"]).to_numpy()
    same = model.df[model.df["material_group"] == group]
    covered = _scaled(same["x_o2"], same["log_flow"], COVERAGE_SCALES)
    Xs = _scaled(X[:, -2], X[:, -1], COVERAGE_SCALES)
    picks, available = [], np.ones(len(X), dtype=bool)
    for _ in range(min(n, len(X))):
        nn = np.sqrt(((Xs[:, None, :] - covered[None, :, :]) ** 2).sum(-1)).min(axis=1)
        novelty = 1 - np.exp(-nn / 2)
        score = relevance * (uncertainty + novelty)
        score[~available] = -np.inf
        i = int(np.argmax(score))
        available[i] = False
        covered = np.vstack([covered, Xs[i]])
        o, f = grid[i]
        near = nearest_tests(model, group, o, f, k=1)[0]
        why = []
        if o > model.ranges["x_o2"][1]:
            why.append(f"aucun essai solide au-dessus de {model.ranges['x_o2'][1]:.1%} d'O2")
        why.append(f"observation réelle la plus proche : essai {near['test_id']} ({near['material_class']}, "
                   f"{near['o2_percent']} % O2, {near['flow_cm_s']:g} cm/s, flamme {'tenue' if near['flame_sustained'] else 'non tenue'})")
        picks.append({
            "rank": len(picks) + 1,
            "conditions": {"material": group, "o2_percent": round(float(o) * 100, 1), "flow_cm_s": float(f)},
            "score": round(float(score[i]), 3), "relevance": round(float(relevance[i]), 3),
            "uncertainty": round(float(uncertainty[i]), 3), "novelty": round(float(novelty[i]), 3),
            # Hors de la plage d'O2 mesurée : pas de probabilité (le modèle reviendrait à 0,5 sans information)
            "p_flame_sustained": round(float(pred["p_sustained"].iloc[i]), 3) if _o2_in_range(model, o) else None,
            "p_flame_sustained_interval_90": (round(float(pred["p_low"].iloc[i]), 3), round(float(pred["p_high"].iloc[i]), 3))
            if _o2_in_range(model, o) else None,
            "nearest_observation": near, "why": " ; ".join(why),
        })
    return {
        "scenario": scenario,
        "scenario_prediction": predict(scenario),
        "nearest_observations": nearest_tests(model, group, o2_target, flow_target, k=3),
        "recommendations": picks,
        "method": "score = pertinence × (incertitude + nouveauté) ; modèle peu fiable, la nouveauté domine",
    }
