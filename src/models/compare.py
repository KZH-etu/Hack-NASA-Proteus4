"""Comparaison des modèles de src/models sur les mêmes essais et les mêmes plis.

Principe : les essais sont découpés en 5 plis par jour d'essai (`session`). Pour chaque pli, chaque modèle est
réentraîné avec son propre code et ses propres données, dont on retire tous les essais des jours de test ; il est
ensuite jugé sur les mêmes essais que les autres. Trois tâches communes :
- gouttelettes FLEX : la flamme s'éteint-elle (extinguished) ? et constante de combustion K (mm²/s) ;
- flammes gazeuses ACME CFI-G (normales, allumées) : s'éteignent-elles seules (extinguished) ou brûlent-elles ?
- solides : extinguished ou burned (model_gp et model_rf n'ont pas de modèle pour cette tâche).

Usage :
    python -m src.models.compare
Écrit src/models/comparaison.md.
"""

import datetime
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import (balanced_accuracy_score, brier_score_loss, f1_score, matthews_corrcoef,
                             mean_absolute_error, r2_score, roc_auc_score)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.data.build_unified import load_family

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent / "comparaison.md"
N_FOLDS = 5
MODELS = ["model_gp", "model_rf", "model_catboost", "model_catboost sans d_ext_mm", "model_thermo"]


def key(df):
    return df["experiment"].astype(str) + "|" + df["test_id"].astype(str)


# ---------- Tâches et plis communs ----------

def tasks():
    """Essais de chaque tâche (communs à tous les modèles qui la traitent) et plis par jour d'essai."""
    from src.models.model_gp.flex.model import load_data as gp_flex_data
    from src.models.model_gp.gas.model import load_data as gp_gas_data

    flex = gp_flex_data()  # essais FLEX avec toutes les variables (le plus restrictif des modèles)
    gas = gp_gas_data()
    gas = gas[(gas["ignited"] == 1) & gas["outcome"].isin(["burned", "extinguished"])]
    solids = load_family("solids")
    solids = solids[solids["outcome"].isin(["burned", "extinguished"])]
    out = {}
    for name, family, rows in (("droplets", "droplets", flex), ("gas", "gas", gas), ("solids", "solids", solids)):
        rows = rows.assign(key=key(rows)).drop_duplicates("key").reset_index(drop=True)
        table = load_family(family)
        table = table.assign(key=key(table))
        folds = []
        for _, test_idx in GroupKFold(n_splits=N_FOLDS).split(rows, groups=rows["session"].astype(str)):
            days = set(rows.loc[test_idx, "session"].astype(str))
            held_out = set(table.loc[table["session"].astype(str).isin(days), "key"])
            folds.append((set(rows.loc[test_idx, "key"]), held_out))
        out[name] = {"rows": rows, "folds": folds}
    return out


def all_held_out(T, fold):
    """Essais à retirer de tout entraînement pour le pli : jours de test de toutes les tâches."""
    return set().union(*(T[name]["folds"][fold][1] for name in T))


# ---------- Adaptateurs : chaque modèle, entraîné avec son propre code ----------

def run_gp(T):
    from src.models.model_gp.flex.model import FlexModel, features as flex_features, load_data as flex_data
    from src.models.model_gp.gas.model import GasModel, MIN_LENGTH_SCALE, features as gas_features, load_data as gas_data
    flex, gas = flex_data(), gas_data()
    flex["key"], gas["key"] = key(flex), key(gas)
    res = {"droplets": {}, "gas": {}, "k": {}}
    for f in range(N_FOLDS):
        out = all_held_out(T, f)
        m = FlexModel(flex[~flex["key"].isin(out)].reset_index(drop=True), n_bootstrap=0)
        test = flex[flex["key"].isin(T["droplets"]["folds"][f][0])]
        pred = m.predict_frame(flex_features(test))
        for k, p, kp, lo, hi in zip(test["key"], pred["p_extinction"], pred["k_mm2_s"], pred["k_low"], pred["k_high"]):
            res["droplets"][k] = (p, p >= 0.5)
            res["k"][k] = (kp, lo, hi)  # intervalle à 95 % calibré
        g = GasModel(gas[~gas["key"].isin(out)].reset_index(drop=True), n_bootstrap=0, min_length=MIN_LENGTH_SCALE)
        test = gas[gas["key"].isin(T["gas"]["folds"][f][0])]
        for k, p in zip(test["key"], g.predict_frame(gas_features(test))["p_self_extinguished"]):
            res["gas"][k] = (p, p >= 0.5)
    return res


def run_rf(T):
    from src.models.model_rf.data_prep import load_tables, prepare_xy
    from src.models.model_rf.families import FAMILIES, model_inputs
    from src.models.model_rf.forest import model_for
    from src.models.model_rf.metrics import fit_model
    tables = load_tables()
    res = {"droplets": {}, "gas": {}, "k": {}}
    specs = (("droplets", "Gouttelettes (FLEX)", "issue"), ("k", "Gouttelettes (FLEX)", "vitesse_combustion_mm2_s"),
             ("gas", "Gaz (ACME CFI-G)", "issue"))
    for task, family, output in specs:
        kind = FAMILIES[family]["sorties"][output]["type"]
        X, y, groups, rows = prepare_xy(tables, family, output)
        inputs = model_inputs(family)
        X = X[list(inputs)]
        keys = key(rows).to_numpy()
        eval_task = "droplets" if task == "k" else task
        for f in range(N_FOLDS):
            train = ~np.isin(keys, list(all_held_out(T, f)))
            test = np.isin(keys, list(T[eval_task]["folds"][f][0]))
            model = fit_model(model_for(family, output), kind, family, X[train], y[train],
                              groups[train] if groups is not None else None, inputs)
            mean, std = model.predict_with_uncertainty(X[test])
            for i, k in enumerate(keys[test]):
                if kind == "regression":
                    res[task][k] = (mean[i], mean[i] - 1.96 * std[i], mean[i] + 1.96 * std[i])
                else:
                    probas = dict(zip(model.classes_, mean[i]))
                    if task == "gas":  # essais allumés : extinction parmi {burned, extinguished}
                        s = probas.get("extinguished", 0) + probas.get("burned", 0)
                        p = probas.get("extinguished", 0) / s if s > 0 else 0.5
                    else:
                        p = probas.get("extinguished", 0)
                    res[task][k] = (p, max(probas, key=probas.get) == "extinguished")
    return res


def run_catboost(T, extra_excluded=()):
    from src.models.model_catboost.model import fit_with_early_stopping, groups_by_test, load_data, prepare_features
    data = load_data()
    X, y, cat_features, _ = prepare_features(data, extra_excluded=extra_excluded)
    keys, groups = key(data).to_numpy(), groups_by_test(data)
    res = {"droplets": {}, "gas": {}, "solids": {}}
    for f in range(N_FOLDS):
        train = ~np.isin(keys, list(all_held_out(T, f)))
        model, _ = fit_with_early_stopping(X[train], y[train], groups[train], cat_features)
        for task in res:
            test = np.isin(keys, list(T[task]["folds"][f][0]))
            proba = pd.DataFrame(model.predict_proba(X[test]), columns=model.classes_)
            for k, (_, row) in zip(keys[test], proba.iterrows()):
                p = row["extinction"]
                if task != "droplets":  # gaz et solides : extinction parmi {extinction, combustion}
                    p = row["extinction"] / (row["extinction"] + row["combustion"])
                res[task][k] = (p, row.idxmax() == "extinction")
    return res


def nicolas_frames():
    """Préparation des données de model_thermo/train.py, à l'identique."""
    from src.models.model_thermo.train import DATA_PATH, DEFAULT_THERMO, THERMO_PROPERTIES
    df = pd.read_csv(DATA_PATH, dtype={"test_id": str})
    valid_outcomes = ['burned', 'completion', 'disruption', 'extinguished', 'no_ignition']
    clf_df = df[df['outcome'].isin(valid_outcomes)].copy()
    clf_df['target'] = clf_df['outcome'].apply(lambda x: 1 if x in ['burned', 'completion', 'disruption'] else 0)
    reg_df = df[df['burning_rate'].notnull() & (df['burning_rate'] > 0)].copy()
    for frame in (clf_df, reg_df):
        frame['o2_percent'] = frame['o2_percent'].fillna(21.0)
        frame['pressure_kpa'] = frame['pressure_kpa'].fillna(101.3)
        frame['flow_cm_s'] = frame['flow_cm_s'].fillna(0.0)
    clf_df['material'] = clf_df['material'].fillna('unknown')
    for frame in (clf_df, reg_df):
        for prop in ['delta_hc', 't_auto_ign_c', 'l_gas_kj_g', 'is_solid']:
            frame[prop] = frame['material'].apply(lambda m: THERMO_PROPERTIES.get(str(m).lower(), DEFAULT_THERMO)[prop])
    return clf_df, reg_df


def run_nicolas(T):
    clf_df, reg_df = nicolas_frames()
    features_clf = ['o2_percent', 'pressure_kpa', 'flow_cm_s', 'delta_hc', 't_auto_ign_c', 'l_gas_kj_g', 'is_solid']
    features_reg = ['o2_percent', 'pressure_kpa', 'delta_hc', 't_auto_ign_c', 'l_gas_kj_g']
    threshold = 0.35  # seuil de décision du modèle d'origine (probabilité de feu)
    ck, rk = key(clf_df).to_numpy(), key(reg_df).to_numpy()
    res = {"droplets": {}, "gas": {}, "solids": {}, "k": {}}
    for f in range(N_FOLDS):
        out = list(all_held_out(T, f))
        clf = Pipeline([('scaler', StandardScaler()),
                        ('gbc', GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.08, random_state=42))])
        train = ~np.isin(ck, out)
        clf.fit(clf_df.loc[train, features_clf], clf_df.loc[train, 'target'])
        reg = Pipeline([('scaler', StandardScaler()),
                        ('gbr', GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.08, random_state=42))])
        train_r = ~np.isin(rk, out)
        reg.fit(reg_df.loc[train_r, features_reg], reg_df.loc[train_r, 'burning_rate'])
        for task in ("droplets", "gas", "solids"):
            test = np.isin(ck, list(T[task]["folds"][f][0]))
            p_fire = clf.predict_proba(clf_df.loc[test, features_clf])[:, 1]
            for k, pf in zip(ck[test], p_fire):
                res[task][k] = (1 - pf, pf < threshold)
        test = np.isin(rk, list(T["droplets"]["folds"][f][0]))
        for k, v in zip(rk[test], reg.predict(reg_df.loc[test, features_reg])):
            res["k"][k] = (v, np.nan, np.nan)
    return res


# ---------- Métriques ----------

def naive(T, task):
    """Référence naïve : taux d'extinction des jours d'entraînement de la tâche."""
    rows = T[task]["rows"]
    y = (rows["outcome"] == "extinguished").astype(int)
    res = {}
    for test_keys, held_out in T[task]["folds"]:
        rate = y[~rows["key"].isin(held_out)].mean()
        for k in test_keys:
            res[k] = (rate, rate >= 0.5)
    return res


def binary_scores(T, task, preds):
    rows = T[task]["rows"]
    truth = dict(zip(rows["key"], (rows["outcome"] == "extinguished").astype(int)))
    keys = [k for k in rows["key"] if k in preds]
    y = np.array([truth[k] for k in keys])
    p = np.clip(np.array([preds[k][0] for k in keys], dtype=float), 0, 1)
    d = np.array([bool(preds[k][1]) for k in keys]).astype(int)
    return {"n": len(keys), "auc": roc_auc_score(y, p), "brier": brier_score_loss(y, p),
            "mcc": matthews_corrcoef(y, d), "f1_macro": f1_score(y, d, average="macro"),
            "balanced_accuracy": balanced_accuracy_score(y, d), "accuracy": float((y == d).mean())}


def k_scores(T, preds):
    rows = T["droplets"]["rows"].dropna(subset=["burning_rate_mm2_s"])
    truth = dict(zip(rows["key"], rows["burning_rate_mm2_s"].astype(float)))
    keys = [k for k in rows["key"] if k in preds]
    y = np.array([truth[k] for k in keys])
    m = np.array([preds[k][0] for k in keys], dtype=float)
    lo, hi = np.array([preds[k][1] for k in keys], dtype=float), np.array([preds[k][2] for k in keys], dtype=float)
    cover = float(((y >= lo) & (y <= hi)).mean()) if not np.isnan(lo).all() else float("nan")
    return {"n": len(keys), "r2": r2_score(y, m), "mae": mean_absolute_error(y, m), "coverage_95": cover}


def naive_k(T):
    rows = T["droplets"]["rows"].dropna(subset=["burning_rate_mm2_s"])
    res = {}
    for test_keys, held_out in T["droplets"]["folds"]:
        train = rows[~rows["key"].isin(held_out)]
        means = train.groupby("fuel")["burning_rate_mm2_s"].mean()
        for _, r in rows[rows["key"].isin(test_keys)].iterrows():
            res[r["key"]] = (means.get(r["fuel"], train["burning_rate_mm2_s"].mean()), np.nan, np.nan)
    return res


# ---------- Scénario de mission : prédictions des modèles livrés ----------

def scenario_lines():
    from src.models.model_catboost import predict as cb_predict
    from src.models.model_gp import flex
    from src.models.model_thermo import predict_fire_safety
    from src.models.model_rf.service import MLService
    rf = MLService.load_or_train()
    cases = [("Air de l'ISS : 21 % O2, 101,3 kPa", 21.0, 101.3), ("Habitat lunaire : 34 % O2, 55 kPa", 34.0, 55.0),
             ("Bas O2 : 15 % O2, 101,3 kPa", 15.0, 101.3)]
    flex_rows = load_family("droplets")
    flex_rows = flex_rows[(flex_rows["experiment"] == "FLEX") & (flex_rows["fuel"] == "heptane")]
    lines = ["| Conditions (gouttelette d'heptane, 3 mm) | Essais FLEX proches : part d'extinctions | model_gp | model_rf | "
             "model_catboost | model_thermo |", "|---|---:|---:|---:|---:|---:|"]
    for label, o2, p in cases:
        gp = flex.predict({"fuel": "heptane", "o2_percent": o2, "pressure_kpa": p, "d0_mm": 3.0})
        gp_txt = f"{gp['p_extinction']:.2f} [{gp['p_extinction_interval_90'][0]:.2f}–{gp['p_extinction_interval_90'][1]:.2f}]" \
            if "p_extinction_interval_90" in gp else f"{gp['p_extinction']:.2f}"
        r = rf.ask("Gouttelettes (FLEX)", {"fuel": "heptane", "x_o2": o2 / 100, "pressure_kpa": p, "x_co2": 0.0,
                                           "x_he": 0.0, "d0_mm": 3.0})
        issue = _find_issue(r)
        rf_txt = f"{issue.get('extinguished', float('nan')):.2f}" if issue else "?"
        cb = cb_predict("droplets", {"fuel": "heptane", "o2_percent": o2, "pressure_kpa": p, "d0_mm": 3.0})
        nic = predict_fire_safety(o2, p, 0.0, "heptane")
        near = flex_rows[((flex_rows["x_o2"].astype(float) - o2 / 100).abs() <= 0.015)
                         & ((flex_rows["pressure_kpa"].astype(float) - p).abs() <= 15)
                         & ((flex_rows["d0_mm"].astype(float) - 3.0).abs() <= 0.75)]
        obs = f"{(near['outcome'] == 'extinguished').mean():.2f} ({len(near)} essais)" if len(near) else "aucun essai"
        lines.append(f"| {label} | {obs} | {gp_txt} | {rf_txt} | {cb['p_extinction']:.2f} | {1 - nic['fire_probability']:.2f} |")
    return lines + ["", "Probabilité d'extinction de la flamme ; entre crochets, l'intervalle à 90 % annoncé par model_gp "
                    "quand il en donne un. Essais proches : heptane, O2 à ± 1,5 point, pression à ± 15 kPa, diamètre à ± 0,75 mm. Le scénario lunaire (55 kPa) est sous la plus basse pression testée par FLEX "
                    "(≈ 70 kPa) : tous les modèles extrapolent.", ""]


def _find_issue(obj):
    """Probabilités des issues dans la réponse de MLService.ask (structure imbriquée)."""
    if isinstance(obj, dict):
        if "toutes_les_issues" in obj:
            return obj["toutes_les_issues"]
        for v in obj.values():
            found = _find_issue(v)
            if found:
                return found
    return None


# ---------- Rapport ----------

def main():
    T = tasks()
    results = {"model_gp": run_gp(T), "model_rf": run_rf(T), "model_catboost": run_catboost(T),
               "model_catboost sans d_ext_mm": run_catboost(T, extra_excluded=["d_ext_mm"]),
               "model_thermo": run_nicolas(T)}
    titles = {"droplets": "Gouttelettes FLEX : extinction de la flamme",
              "gas": "Flammes gazeuses ACME CFI-G (normales, allumées) : extinction",
              "solids": "Solides : extinction ou combustion"}
    lines = [
        "# Comparaison des modèles",
        "",
        f"Généré par `python -m src.models.compare` le {datetime.date.today().isoformat()}. Ne pas éditer à la main.",
        "",
        f"Mêmes essais et mêmes {N_FOLDS} plis par **jour d'essai** pour tous les modèles : à chaque pli, chaque modèle "
        "est réentraîné avec son propre code et ses propres données, dont on retire tous les essais des jours de test, "
        "puis jugé sur les mêmes essais. Décision « extinction » : seuil 0,5 (model_gp), classe la plus probable "
        "(model_rf, model_catboost), probabilité de feu < 0,35 (model_thermo, son seuil d'origine). "
        "« model_catboost sans d_ext_mm » : même modèle sans le diamètre à l'extinction, mesuré après l'essai "
        "(diagnostic : c'est la version qu'on pourrait utiliser avant un essai).",
        "",
    ]
    summary = {}
    for task in ("droplets", "gas", "solids"):
        lines += [f"## {titles[task]}", "",
                  f"{len(T[task]['rows'])} essais, {(T[task]['rows']['outcome'] == 'extinguished').mean():.0%} d'extinctions.", "",
                  "| Modèle | Essais | AUC | Brier ↓ | MCC | F1 macro | Exactitude équilibrée | Exactitude |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for name in MODELS:
            if task not in results[name]:
                lines.append(f"| {name} | — | pas de modèle pour cette tâche | | | | | |")
                continue
            s = binary_scores(T, task, results[name][task])
            summary[(task, name)] = s
            lines.append(f"| {name} | {s['n']} | {s['auc']:.3f} | {s['brier']:.3f} | {s['mcc']:.3f} | {s['f1_macro']:.3f} | "
                         f"{s['balanced_accuracy']:.3f} | {s['accuracy']:.3f} |")
        s = binary_scores(T, task, naive(T, task))
        lines += [f"| Référence naïve (taux d'extinction) | {s['n']} | {s['auc']:.3f} | {s['brier']:.3f} | {s['mcc']:.3f} | "
                  f"{s['f1_macro']:.3f} | {s['balanced_accuracy']:.3f} | {s['accuracy']:.3f} |", ""]
        if task == "droplets":
            lines += ["### Constante de combustion K (mm²/s)", "",
                      "| Modèle | Essais | R² | Erreur absolue moyenne | Couverture de l'intervalle à 95 % |",
                      "|---|---:|---:|---:|---:|"]
            for name in MODELS:
                if "k" not in results[name]:
                    lines.append(f"| {name} | — | pas de prédiction de K | | |")
                    continue
                s = k_scores(T, results[name]["k"])
                summary[("k", name)] = s
                cov = "pas d'intervalle" if np.isnan(s["coverage_95"]) else f"{s['coverage_95']:.1%}"
                lines.append(f"| {name} | {s['n']} | {s['r2']:.3f} | {s['mae']:.3f} | {cov} |")
            s = k_scores(T, naive_k(T))
            lines += [f"| Référence naïve (K moyen par combustible) | {s['n']} | {s['r2']:.3f} | {s['mae']:.3f} | — |", ""]
    lines += ["## Scénario de mission (modèles livrés)", ""] + scenario_lines()
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return summary


if __name__ == "__main__":
    main()
