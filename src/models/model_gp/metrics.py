"""Métriques communes aux validations des modèles (flex, solids, gas)."""

import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss, confusion_matrix, f1_score,
                             log_loss, matthews_corrcoef, precision_score, recall_score, roc_auc_score)


def classification_metrics(y, p):
    """AUC, Brier, log loss et exactitude (seuil 0,5) d'une probabilité p pour des étiquettes y (0 / 1)."""
    return {
        "n": int(len(y)),
        "auc": roc_auc_score(y, p) if len(set(y)) == 2 else float("nan"),
        "brier": brier_score_loss(y, p),
        "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]),
        "accuracy": float(((p >= 0.5) == y).mean()),
    }


def detailed_metrics(y, p, threshold=0.5):
    """Toutes les métriques d'un classifieur binaire (positif = 1) à partir de probabilités p."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    pred = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "accuracy": accuracy_score(y, pred),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "precision_pos": precision_score(y, pred, zero_division=0),
        "recall_pos": recall_score(y, pred, zero_division=0),
        "f1_pos": f1_score(y, pred, zero_division=0),
        "precision_neg": precision_score(1 - y, 1 - pred, zero_division=0),
        "recall_neg": recall_score(1 - y, 1 - pred, zero_division=0),
        "f1_neg": f1_score(1 - y, 1 - pred, zero_division=0),
        "f1_macro": f1_score(y, pred, average="macro", zero_division=0),
        "mcc": matthews_corrcoef(y, pred),
        "auc": roc_auc_score(y, p) if len(set(y)) == 2 else float("nan"),
        "brier": brier_score_loss(y, p),
        "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]),
        "confusion": {"vp": int(tp), "fn": int(fn), "fp": int(fp), "vn": int(tn)},
    }


def detailed_report_lines(y, p, base_p, pos_label, neg_label, threshold=0.5):
    """Lignes Markdown : tableau complet des métriques (modèle contre référence naïve) + matrices de confusion."""
    y = np.asarray(y).astype(int)
    model, base = detailed_metrics(y, p, threshold), detailed_metrics(y, base_p, threshold)
    majority = max(y.mean(), 1 - y.mean())
    rows = [
        ("Exactitude (accuracy)", "accuracy"), ("Exactitude équilibrée", "balanced_accuracy"),
        (f"Précision « {pos_label} »", "precision_pos"), (f"Rappel « {pos_label} »", "recall_pos"), (f"F1 « {pos_label} »", "f1_pos"),
        (f"Précision « {neg_label} »", "precision_neg"), (f"Rappel « {neg_label} »", "recall_neg"), (f"F1 « {neg_label} »", "f1_neg"),
        ("F1 macro", "f1_macro"), ("MCC (0 = hasard, 1 = parfait)", "mcc"), ("AUC", "auc"),
        ("Brier (plus bas = mieux)", "brier"), ("Log loss (plus bas = mieux)", "log_loss"),
    ]
    lines = [
        f"Métriques détaillées (hors échantillon, seuil {threshold:g}) : {len(y)} cas, {y.mean():.0%} « {pos_label} » ; "
        f"exactitude en répondant toujours la classe majoritaire : {majority:.3f}.",
        "",
        "| Métrique | Modèle | Référence naïve |",
        "|---|---:|---:|",
    ]
    lines += [f"| {label} | {model[key]:.3f} | {base[key]:.3f} |" for label, key in rows]
    lines += ["", f"Matrices de confusion (positif = « {pos_label} ») :", "",
              "| | Vrais positifs | Faux négatifs | Faux positifs | Vrais négatifs |", "|---|---:|---:|---:|---:|"]
    for name, m in (("Modèle", model), ("Référence naïve", base)):
        c = m["confusion"]
        lines.append(f"| {name} | {c['vp']} | {c['fn']} | {c['fp']} | {c['vn']} |")
    lines.append("")
    return lines
