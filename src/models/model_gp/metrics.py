"""Métriques communes aux validations des modèles (flex, solids, gas)."""

import numpy as np
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


def classification_metrics(y, p):
    """AUC, Brier, log loss et exactitude (seuil 0,5) d'une probabilité p pour des étiquettes y (0 / 1)."""
    return {
        "n": int(len(y)),
        "auc": roc_auc_score(y, p) if len(set(y)) == 2 else float("nan"),
        "brier": brier_score_loss(y, p),
        "log_loss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]),
        "accuracy": float(((p >= 0.5) == y).mean()),
    }
