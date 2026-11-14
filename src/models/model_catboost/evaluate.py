"""Validation du modèle CatBoost à 3 classes : découpage d'origine (20 % des essais) et validation croisée par
jour d'essai (comme model_gp), comparées à une référence naïve. Écrit src/models/model_catboost/validation.md.

Usage :
    python -m src.models.model_catboost.evaluate
"""

import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, log_loss,
                             matthews_corrcoef, precision_recall_fscore_support, roc_auc_score)
from sklearn.model_selection import GroupKFold

from src.models.model_catboost.model import (CLASSES, fit_with_early_stopping, groups_by_test, holdout_split,
                                             load_data, prepare_features)
from src.models.model_gp.metrics import detailed_report_lines

REPORT = Path(__file__).resolve().parent / "validation.md"
N_FOLDS = 5
FAMILY_LABELS = {'droplet': 'Gouttelettes', 'solid': 'Solides', 'gas': 'Gaz'}


def baseline_proba(train_types, train_y, test_types):
    """Référence naïve : fréquence des classes par famille dans l'entraînement."""
    freq = pd.crosstab(train_types, train_y, normalize='index').reindex(columns=CLASSES, fill_value=0.0)
    overall = train_y.value_counts(normalize=True).reindex(CLASSES, fill_value=0.0)
    return np.vstack([freq.loc[t].to_numpy() if t in freq.index else overall.to_numpy() for t in test_types])


def holdout(data, X, y, cat_features):
    idx_dev, idx_test = holdout_split(X, y, groups_by_test(data))
    groups = groups_by_test(data)
    model, _ = fit_with_early_stopping(X.iloc[idx_dev], y.iloc[idx_dev], groups.iloc[idx_dev], cat_features)
    proba = pd.DataFrame(model.predict_proba(X.iloc[idx_test]), columns=model.classes_)[CLASSES].to_numpy()
    types = data['material_type'].to_numpy()
    base = baseline_proba(pd.Series(types[idx_dev]), y.iloc[idx_dev].reset_index(drop=True), types[idx_test])
    return y.iloc[idx_test].to_numpy(), proba, base, types[idx_test], model.best_iteration_


def cross_validate_by_day(data, X, y, cat_features):
    """Validation croisée par jour d'essai : un jour n'est jamais à la fois en entraînement et en test.
    Dans chaque pli, l'entraînement suit la procédure d'origine (25 % des jours d'entraînement pour l'arrêt anticipé)."""
    sessions = data['material_type'].astype(str) + '_' + data['session'].astype(str)
    types = data['material_type'].to_numpy()
    proba, base = np.zeros((len(X), len(CLASSES))), np.zeros((len(X), len(CLASSES)))
    iterations = []
    for train_idx, test_idx in GroupKFold(n_splits=N_FOLDS).split(X, y, sessions):
        model, _ = fit_with_early_stopping(X.iloc[train_idx], y.iloc[train_idx], sessions.iloc[train_idx], cat_features)
        proba[test_idx] = pd.DataFrame(model.predict_proba(X.iloc[test_idx]), columns=model.classes_)[CLASSES].to_numpy()
        base[test_idx] = baseline_proba(pd.Series(types[train_idx]), y.iloc[train_idx].reset_index(drop=True), types[test_idx])
        iterations.append(model.best_iteration_)
    return y.to_numpy(), proba, base, types, iterations, sessions.nunique()


def multiclass_metrics(y, proba):
    pred = np.array(CLASSES)[proba.argmax(axis=1)]
    y = np.asarray(y)
    precision, recall, f1, support = precision_recall_fscore_support(y, pred, labels=CLASSES, zero_division=0)
    # AUC « une classe contre les autres », moyenne sur les classes présentes avec les deux issues
    aucs = [roc_auc_score(y == c, proba[:, i]) for i, c in enumerate(CLASSES) if 0 < (y == c).sum() < len(y)]
    auc = float(np.mean(aucs)) if aucs else float('nan')
    return {
        "accuracy": accuracy_score(y, pred), "balanced_accuracy": balanced_accuracy_score(y, pred),
        "f1_macro": f1_score(y, pred, labels=CLASSES, average='macro', zero_division=0),
        "f1_weighted": f1_score(y, pred, labels=CLASSES, average='weighted', zero_division=0),
        "mcc": matthews_corrcoef(y, pred),
        "log_loss": log_loss(y, np.clip(proba, 1e-6, 1), labels=CLASSES),
        "auc_ovr": auc,
        "per_class": {c: (precision[i], recall[i], f1[i], int(support[i])) for i, c in enumerate(CLASSES)},
        "confusion": confusion_matrix(y, pred, labels=CLASSES),
    }


def multiclass_lines(y, proba, base):
    m, b = multiclass_metrics(y, proba), multiclass_metrics(y, base)
    majority = pd.Series(y).value_counts(normalize=True).max()
    rows = [("Exactitude (accuracy)", "accuracy"), ("Exactitude équilibrée", "balanced_accuracy"),
            ("F1 macro", "f1_macro"), ("F1 pondéré", "f1_weighted"), ("MCC (0 = hasard, 1 = parfait)", "mcc"),
            ("AUC (une classe contre les autres, moyenne)", "auc_ovr"), ("Log loss (plus bas = mieux)", "log_loss")]
    lines = [f"{len(y)} cas ; exactitude en répondant toujours la classe majoritaire : {majority:.3f}.", "",
             "| Métrique | Modèle | Référence naïve (fréquences par famille) |", "|---|---:|---:|"]
    lines += [f"| {label} | {m[key]:.3f} | {b[key]:.3f} |" for label, key in rows]
    lines += ["", "Par classe (modèle) :", "", "| Classe | Précision | Rappel | F1 | Cas |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {c} | {p:.3f} | {r:.3f} | {f:.3f} | {n} |" for c, (p, r, f, n) in m["per_class"].items()]
    lines += ["", "Matrice de confusion du modèle (lignes = réel, colonnes = prédit) :", "",
              "| | " + " | ".join(CLASSES) + " |", "|---|" + "---:|" * len(CLASSES)]
    lines += [f"| {c} | " + " | ".join(str(v) for v in m["confusion"][i]) + " |" for i, c in enumerate(CLASSES)]
    lines.append("")
    return lines, m


def per_family_lines(y, proba, types):
    lines = ["| Famille | Cas | Exactitude | Exactitude équilibrée | F1 macro | MCC |", "|---|---:|---:|---:|---:|---:|"]
    for t, label in FAMILY_LABELS.items():
        mask = types == t
        if mask.any():
            m = multiclass_metrics(y[mask], proba[mask])
            lines.append(f"| {label} | {int(mask.sum())} | {m['accuracy']:.3f} | {m['balanced_accuracy']:.3f} | "
                         f"{m['f1_macro']:.3f} | {m['mcc']:.3f} |")
    return lines + [""]


def main():
    data = load_data()
    X, y, cat_features, _ = prepare_features(data)
    h_y, h_p, h_b, _, h_iter = holdout(data, X, y, cat_features)
    cv_y, cv_p, cv_b, cv_types, cv_iter, n_days = cross_validate_by_day(data, X, y, cat_features)
    # Diagnostic : même procédure sans d_ext_mm (diamètre à l'extinction, mesuré après l'essai)
    X2, y2, cat2, _ = prepare_features(data, extra_excluded=['d_ext_mm'])
    d_y, d_p, d_b, _, _, _ = cross_validate_by_day(data, X2, y2, cat2)

    lines = [
        "# Validation du modèle CatBoost (3 classes, toutes familles)",
        "",
        f"Généré par `python -m src.models.model_catboost.evaluate` le {datetime.date.today().isoformat()}. Ne pas éditer à la main.",
        "",
        f"- Données : {len(data)} essais (gouttelettes, solides, gaz) dont le résultat est extinction (`extinguished`), "
        "combustion (`burned`, `completion`) ou intermédiaire (`disruption`) ; " + ", ".join(
            f"{FAMILY_LABELS[t].lower()} {n}" for t, n in data['material_type'].value_counts().items() if t in FAMILY_LABELS) + ".",
        f"- {X.shape[1]} variables : {', '.join(X.columns)}.",
        "- Logique du modèle inchangée par rapport au script d'origine (voir `model.py`).",
        "",
        "## 1. Découpage d'origine (20 % des essais en test, une seule fois)",
        "",
        f"Résultat du script d'origine, reproduit à l'identique (meilleure itération : {h_iter}).",
        "",
    ]
    lines += multiclass_lines(h_y, h_p, h_b)[0]
    lines += [
        "## 2. Validation croisée par jour d'essai (comparable à model_gp)",
        "",
        f"{N_FOLDS} plis, `GroupKFold` sur le jour d'essai ({n_days} jours) : tous les essais d'un même jour sont du même "
        "côté. Le découpage d'origine sépare les essais mais pas les jours ; or les essais d'un même jour se ressemblent "
        "(même montage, même gaz, réglages voisins), ce qui rend un test par essai plus optimiste.",
        f"Meilleures itérations par pli : {', '.join(map(str, cv_iter))}.",
        "",
    ]
    cv_lines, cv_m = multiclass_lines(cv_y, cv_p, cv_b)
    lines += cv_lines
    lines += ["Par famille (modèle, validation par jour d'essai) :", ""] + per_family_lines(cv_y, cv_p, cv_types)
    lines += ["Par famille (référence naïve) :", ""] + per_family_lines(cv_y, cv_b, cv_types)

    lines += ["### Vue binaire « extinction » contre le reste, par famille", "",
              "Probabilité d'extinction du modèle, mêmes métriques que les rapports de model_gp. Attention : les tâches "
              "ne sont pas identiques à celles de model_gp (ici tous les essais de la famille, résultat de l'essai ; "
              "model_gp/flex : essais FLEX complets ; model_gp/solids : observations « la flamme tient » à chaque "
              "réglage ; model_gp/gas : allumage puis auto-extinction des flammes normales).", ""]
    for t, label in FAMILY_LABELS.items():
        mask = cv_types == t
        y_bin = (cv_y[mask] == 'extinction').astype(int)
        lines += [f"#### {label}", ""]
        lines += detailed_report_lines(y_bin, cv_p[mask, 0], cv_b[mask, 0], "extinction", "pas d'extinction")

    d_m = multiclass_metrics(d_y, d_p)
    lines += [
        "## 3. Diagnostic : sans `d_ext_mm`",
        "",
        "`d_ext_mm` (diamètre de la gouttelette à l'extinction) est mesuré **après** l'essai et n'est renseigné que s'il y "
        "a eu extinction ; il fait partie des entrées du modèle. Même validation par jour d'essai, cette variable retirée "
        "(diagnostic seulement, le modèle livré la garde) :",
        "",
        "| | Exactitude | Exactitude équilibrée | F1 macro | MCC | Log loss |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Modèle tel quel | {cv_m['accuracy']:.3f} | {cv_m['balanced_accuracy']:.3f} | {cv_m['f1_macro']:.3f} | {cv_m['mcc']:.3f} | {cv_m['log_loss']:.3f} |",
        f"| Sans `d_ext_mm` | {d_m['accuracy']:.3f} | {d_m['balanced_accuracy']:.3f} | {d_m['f1_macro']:.3f} | {d_m['mcc']:.3f} | {d_m['log_loss']:.3f} |",
        "",
        "Par famille, sans `d_ext_mm` :",
        "",
    ]
    lines += per_family_lines(d_y, d_p, cv_types)
    lines += [
        "## Limites",
        "",
        "- Pas d'intervalle d'incertitude (probabilité ponctuelle).",
        "- Un seul modèle pour des familles aux variables différentes : les variables d'une famille sont vides pour les "
        "autres ; `material_type` et `gravity` sont des entrées (la gravité 1g ne concerne que des essais de solides).",
        "- Avant un essai, `d_ext_mm` est inconnu : la prédiction se fait avec cette entrée vide (voir section 3).",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
