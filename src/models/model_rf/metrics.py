"""Évaluation honnête, famille par famille.

Principe : on met de côté une session entière, on entraîne sur le reste, on prédit
la session cachée. On compare toujours à une « référence naïve » :
- classification : toujours répondre l'issue la plus fréquente
- régression : toujours répondre la valeur médiane
Un modèle qui ne bat pas la référence naïve n'apporte rien.

Intervalles de confiance (IC 95 %) : on retire au hasard des sessions entières (bootstrap)
et on recalcule le score 1000 fois. Si l'IC de l'écart entre deux modèles contient 0,
la différence peut être due au hasard : on ne conclut pas.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, mean_absolute_error
from sklearn.model_selection import GroupKFold, KFold

from .data_prep import prepare_xy
from .families import FAMILIES, model_inputs
from .forest import ForestModel

N_BOOT = 1000


def _splits(X, groups, n_splits=5):
    if groups is not None and groups.nunique() >= 3:
        k = min(n_splits, groups.nunique())
        return list(GroupKFold(n_splits=k).split(X, groups=groups)), f"par groupe ({k} plis)"
    k = min(n_splits, len(X))
    return list(KFold(n_splits=k, shuffle=True, random_state=0).split(X)), "aléatoire (pas assez de groupes !)"


def fit_model(model_class, kind, family, X, y, groups=None, inputs=None):
    """Crée et entraîne un modèle ; passe les sessions aux modèles qui savent s'en servir."""
    model = model_class(kind, inputs or model_inputs(family))
    if getattr(model_class, "uses_groups", False):
        return model.fit(X, y, groups=groups)
    return model.fit(X, y)


def oof_predictions(tables, family, output, model_class=ForestModel, use_derivees=True):
    """Prédictions « hors échantillon » : chaque essai est prédit par un modèle qui ne l'a jamais vu.

    Les découpages sont déterministes : deux modèles différents passent EXACTEMENT le même examen.
    """
    fiche = FAMILIES[family]
    kind = fiche["sorties"][output]["type"]
    X, y, groups, _ = prepare_xy(tables, family, output)
    inputs = model_inputs(family) if use_derivees else dict(fiche["entrees"])
    X = X[list(inputs)]
    splits, how = _splits(X, groups)

    parts = []
    for train, test in splits:
        g_tr = groups.iloc[train] if groups is not None else None
        model = fit_model(model_class, kind, family, X.iloc[train], y.iloc[train], g_tr, inputs)
        mean, std = model.predict_with_uncertainty(X.iloc[test])
        part = pd.DataFrame({"truth": y.iloc[test].to_numpy(),
                             "group": (groups.iloc[test] if groups is not None
                                       else pd.Series(test, index=X.index[test]).astype(str)).to_numpy()},
                            index=X.index[test])
        if kind == "regression":
            part["pred"] = mean
            part["low"], part["high"] = mean - 1.96 * std, mean + 1.96 * std
            part["naive"] = y.iloc[train].median()
        else:
            part["pred"] = [model.classes_[i] for i in mean.argmax(axis=1)]
            part["conf"] = mean.max(axis=1)              # confiance annoncée pour l'issue choisie
            part["naive"] = y.iloc[train].mode()[0]
        parts.append(part)
    return pd.concat(parts).sort_index(), how, kind


def _main_score(df, kind):
    """Score principal : MAE (plus bas = mieux) ou exactitude équilibrée (plus haut = mieux)."""
    if kind == "regression":
        return mean_absolute_error(df["truth"], df["pred"])
    return balanced_accuracy_score(df["truth"], df["pred"])


def _bootstrap(dfs, kind, func, seed=0):
    """IC 95 % en tirant des sessions entières avec remise (mêmes tirages pour tous les dfs)."""
    rng = np.random.default_rng(seed)
    groups = dfs[0]["group"].unique()
    index_by_group = {g: np.flatnonzero(dfs[0]["group"].to_numpy() == g) for g in groups}
    values = []
    for _ in range(N_BOOT):
        pick = rng.choice(groups, size=len(groups), replace=True)
        idx = np.concatenate([index_by_group[g] for g in pick])
        try:
            values.append(func(*[d.iloc[idx] for d in dfs]))
        except ValueError:
            continue
    return np.percentile(values, [2.5, 97.5])


def evaluate(tables, family, output, model_class=ForestModel, use_derivees=True):
    res = {"famille": family, "sortie": output, "modele": model_class.name}
    _, y, _, _ = prepare_xy(tables, family, output)
    res["n_essais"] = len(y)
    if len(y) < 15:
        return {**res, "remarque": "trop peu d'essais"}
    df, how, kind = oof_predictions(tables, family, output, model_class, use_derivees)
    res["validation"] = how
    t, p = df["truth"].to_numpy(), df["pred"].to_numpy()

    if kind == "regression":
        res["MAE_modele"] = mean_absolute_error(t, p)
        res["MAE_reference"] = mean_absolute_error(t, df["naive"])
        lo, hi = _bootstrap([df], kind, lambda d: _main_score(d, kind))
        res["MAE_IC95"] = f"[{lo:.3f} ; {hi:.3f}]"
        res["couverture_95"] = float(np.mean((t >= df["low"]) & (t <= df["high"])))
    else:
        res["exactitude_modele"] = accuracy_score(t, p)
        res["exactitude_reference"] = accuracy_score(t, df["naive"])
        res["exactitude_equilibree"] = balanced_accuracy_score(t, p)
        lo, hi = _bootstrap([df], kind, lambda d: _main_score(d, kind))
        res["equilibree_IC95"] = f"[{lo:.0%} ; {hi:.0%}]"
        # Détection par issue : parmi les vrais cas de chaque issue, combien le modèle en a trouvé ?
        res["detection_par_issue"] = ", ".join(
            f"{c} {np.mean(p[t == c] == c):.0%} ({(t == c).sum()})" for c in sorted(set(t)))
        # Écart de fiabilité : quand le modèle annonce « 80 % sûr », a-t-il raison ~80 % du temps ?
        c, right = df["conf"].to_numpy(), (t == p).astype(float)
        bins = np.minimum((c * 5).astype(int), 4)
        res["ecart_fiabilite"] = float(sum(
            abs(c[bins == b].mean() - right[bins == b].mean()) * (bins == b).mean()
            for b in np.unique(bins)))
    res["bat_la_reference"] = beats_reference(res)
    return res


def beats_reference(res: dict) -> bool:
    """Le modèle fait-il nettement mieux qu'une réponse fixe ? (au moins 5 % de mieux)"""
    if "MAE_modele" in res:
        return res["MAE_modele"] < 0.95 * res["MAE_reference"]
    if "exactitude_equilibree" in res:
        n_classes = res["detection_par_issue"].count(",") + 1
        # Une réponse fixe a une exactitude équilibrée de 1 / nombre d'issues.
        return (res["exactitude_equilibree"] > 1.05 / n_classes
                and res["exactitude_modele"] >= res["exactitude_reference"])
    return False


def paired_gain(tables, family, output, variant_a, variant_b):
    """Gain de B par rapport à A, sur exactement les mêmes essais, avec son IC 95 %.

    Chaque variante = (classe_de_modele, use_derivees). Gain positif = B meilleur.
    Conclusion « B meilleur » seulement si tout l'IC est au-dessus de 0.
    """
    da, _, kind = oof_predictions(tables, family, output, *variant_a)
    db, _, _ = oof_predictions(tables, family, output, *variant_b)
    sign = -1 if kind == "regression" else 1          # MAE : plus bas = mieux
    gain = lambda a, b: sign * (_main_score(b, kind) - _main_score(a, kind))
    lo, hi = _bootstrap([da, db], kind, gain)
    g = gain(da, db)
    verdict = "B meilleur" if lo > 0 else ("A meilleur" if hi < 0 else "pas de différence démontrée")
    unit = "MAE" if kind == "regression" else "exactitude équilibrée"
    return {"famille": family, "sortie": output, "mesure": unit, "gain": round(g, 4),
            "IC95": f"[{lo:.4f} ; {hi:.4f}]", "verdict": verdict}


def compare(tables, model_classes=(ForestModel,)):
    """Tableau de résultats pour toutes les familles, sorties et modèles."""
    rows = [evaluate(tables, fam, out, mc)
            for fam, fiche in FAMILIES.items()
            for out in fiche["sorties"]
            for mc in model_classes]
    return pd.DataFrame(rows)


def classification_report_fr(tables, family, output, model_class=ForestModel):
    """Précision, rappel, F1 et support pour chaque issue, + moyennes, sur les prédictions hors échantillon.

    - précision : quand le modèle annonce cette issue, combien de fois a-t-il raison ?
    - rappel    : parmi les vrais cas de cette issue, combien le modèle en trouve-t-il ?
    - F1        : moyenne harmonique des deux (punit un déséquilibre entre précision et rappel)
    - support   : nombre de vrais cas de cette issue
    Moyenne « macro » : chaque issue compte autant (sensible aux issues rares).
    Moyenne « pondérée » : chaque issue compte selon son nombre de cas.
    """
    from sklearn.metrics import precision_recall_fscore_support

    df, _, kind = oof_predictions(tables, family, output, model_class)
    if kind != "classification":
        raise ValueError("Rapport réservé aux sorties de type classification.")
    t, p = df["truth"].to_numpy(), df["pred"].to_numpy()
    labels = sorted(set(t))
    prec, rec, f1, sup = precision_recall_fscore_support(t, p, labels=labels, zero_division=0)
    rows = [{"issue": l, "precision": pr, "rappel": rc, "f1": f, "support": int(s)}
            for l, pr, rc, f, s in zip(labels, prec, rec, f1, sup)]
    for avg, name in (("macro", "moyenne macro"), ("weighted", "moyenne pondérée")):
        pr, rc, f, _ = precision_recall_fscore_support(t, p, labels=labels, average=avg, zero_division=0)
        rows.append({"issue": name, "precision": pr, "rappel": rc, "f1": f, "support": len(t)})
    rows.append({"issue": "accuracy", "precision": None, "rappel": None,
                 "f1": accuracy_score(t, p), "support": len(t)})
    # IC 95 % du F1 macro, en tirant des sessions entières
    from sklearn.metrics import f1_score
    lo, hi = _bootstrap([df], kind, lambda d: f1_score(d["truth"], d["pred"], average="macro", zero_division=0))
    report = pd.DataFrame(rows)
    report.attrs["f1_macro_IC95"] = (lo, hi)
    report.attrs["confusion"] = pd.crosstab(pd.Series(t, name="vrai"), pd.Series(p, name="prédit"))
    return report
