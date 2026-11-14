"""Validation du modèle ACME CFI-G (flammes normales) : validation croisée par jour d'essai, références naïves,
comparaison longueur de corrélation libre / contrainte. Écrit docs/modele_gaz_validation.md.

Usage :
    python -m src.models.evaluate_gas
"""

import datetime
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupKFold

from src.models.evaluate_flex import classification_metrics
from src.models.gas import FEATURES, GasModel, MIN_LENGTH_SCALE, features, load_data

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "modele_gaz_validation.md"
N_FOLDS = 5
LABELS = {"ignited": "Allumage d'une flamme chaude", "self_extinguished": "Auto-extinction (essais allumés)"}


def cross_validate(df, min_length):
    preds = {t: np.full(len(df), np.nan) for t in GasModel.TARGETS}
    base = {t: np.full(len(df), np.nan) for t in GasModel.TARGETS}
    for train_idx, test_idx in GroupKFold(n_splits=N_FOLDS).split(df, groups=df["session"]):
        train, test = df.iloc[train_idx], df.iloc[test_idx]
        model = GasModel(train, n_bootstrap=0, min_length=min_length)
        pred = model.predict_frame(features(test))
        for t in GasModel.TARGETS:
            preds[t][test_idx] = pred[f"p_{t}"].to_numpy()
            rates = train.dropna(subset=[t]).groupby("fuel")[t].mean()
            base[t][test_idx] = test["fuel"].map(rates).fillna(train[t].mean()).to_numpy()
    return preds, base


def metrics(df, preds, target):
    mask = df[target].notna().to_numpy()
    y = df.loc[mask, target].astype(int).to_numpy()
    return classification_metrics(y, preds[target][mask]), y


def main():
    df = load_data()
    results = {ml: cross_validate(df, ml) for ml in (1e-2, 1.0)}
    fmt = lambda x: f"{x:.3f}"
    lines = [
        "# Validation du modèle ACME CFI-G (flammes normales)",
        "",
        f"Généré par `python -m src.models.evaluate_gas` le {datetime.date.today().isoformat()}. Ne pas éditer à la main.",
        "",
        f"- Données : {len(df)} flammes normales (jet de gaz dans une atmosphère contenant l'O2) sur {df['session'].nunique()} jours d'essai ; "
        f"variables : {', '.join(FEATURES)}.",
        f"- O2 de {df['x_o2'].min():.0%} à {df['x_o2'].max():.0%} ; pression de {df['pressure_kpa'].min():.0f} à {df['pressure_kpa'].max():.0f} kPa.",
        f"- Validation croisée **par jour d'essai** ({N_FOLDS} plis) ; référence : taux observé par combustible dans l'entraînement.",
        f"- Deux réglages comparés : longueur de corrélation libre (≥ 0,01) et contrainte (≥ 1, pour que l'O2, qui baisse au fil "
        f"d'une journée, ne serve pas d'identifiant du jour). Réglage retenu dans `src/models/gas.py` : ≥ {MIN_LENGTH_SCALE:g}.",
        "",
    ]
    for target in GasModel.TARGETS:
        lines += [f"## {LABELS[target]}", "", "| | AUC | Brier ↓ | Exactitude (seuil 0,5) |", "|---|---:|---:|---:|"]
        for ml, (preds, base) in results.items():
            m, y = metrics(df, preds, target)
            lines.append(f"| Modèle, longueur ≥ {ml:g} | {fmt(m['auc'])} | {fmt(m['brier'])} | {fmt(m['accuracy'])} |")
        mb, y = metrics(df, results[1e-2][1], target)
        lines.append(f"| Référence : taux par combustible | {fmt(mb['auc'])} | {fmt(mb['brier'])} | {fmt(mb['accuracy'])} |")
        lines.append(f"| Référence : toujours la classe majoritaire | — | — | {fmt(max(y.mean(), 1 - y.mean()))} |")
        lines += ["", f"{len(y)} essais ; part positive {y.mean():.2f}.", ""]
    near = df[(df["x_o2"] >= 0.30) & (df["pressure_kpa"] <= 70)]
    lines += [
        "## Données près de l'atmosphère d'exploration",
        "",
        f"{len(near)} flammes normales à ≤ 70 kPa et ≥ 30 % d'O2 (jours {', '.join(sorted(near['session'].unique()))}) : "
        f"{int(near['ignited'].sum())} allumages ; parmi eux {int(near['self_extinguished'].sum())} auto-extinctions.",
        "",
        "## Limites",
        "",
        "- 11 jours d'essai seulement : la validation par jour repose sur peu de groupes.",
        "- L'O2 de la chambre baisse au fil des essais d'une journée (combustion) : O2 et ordre des essais sont liés.",
        "- « Auto-extinction » inclut des passages en flamme froide ; « flamme maintenue » (FT) = l'équipe a coupé le débit.",
        "- Brûleur sphérique en chambre calme : rien sur l'effet d'une ventilation.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
