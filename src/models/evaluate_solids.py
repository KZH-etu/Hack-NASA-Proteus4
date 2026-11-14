"""Validation du modèle des solides (carte d'inflammabilité BASS / BASS-II) : validation croisée par jour d'essai,
comparée à des références naïves. Écrit docs/modele_solides_validation.md.

Usage :
    python -m src.models.evaluate_solids
"""

import datetime
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupKFold

from src.models.evaluate_flex import classification_metrics
from src.models.solids import FEATURES, MATERIAL_CLASSES, SolidsModel, features, observations

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "modele_solides_validation.md"
N_FOLDS = 5


def cross_validate(obs):
    out = obs.copy()
    out["p_sustained"] = np.nan
    out["base_p"] = np.nan
    for train_idx, test_idx in GroupKFold(n_splits=N_FOLDS).split(obs, groups=obs["session"]):
        train, test = obs.iloc[train_idx], obs.iloc[test_idx]
        model = SolidsModel(train, n_bootstrap=0)
        out.loc[test.index, "p_sustained"] = model.predict_frame(features(test))["p_sustained"].to_numpy()
        rates = train.groupby("material_class")["sustained"].mean()
        out.loc[test.index, "base_p"] = test["material_class"].map(rates).fillna(train["sustained"].mean()).to_numpy()
    return out


def main():
    obs = observations()
    cv = cross_validate(obs)
    y = cv["sustained"].to_numpy()
    model_c = classification_metrics(y, cv["p_sustained"].to_numpy())
    base_c = classification_metrics(y, cv["base_p"].to_numpy())
    majority = float(max(y.mean(), 1 - y.mean()))
    bins = np.linspace(0, 1, 6)
    cv["bin"] = np.clip(np.digitize(cv["p_sustained"], bins) - 1, 0, 4)
    calib = cv.groupby("bin").agg(n=("sustained", "size"), predite=("p_sustained", "mean"), observee=("sustained", "mean"))
    by_class = cv.groupby("material_class").agg(n=("sustained", "size"), tient=("sustained", "mean"))

    full = SolidsModel(obs, n_bootstrap=0)
    lengths = full.classifier[-1].kernel_.k2.length_scale
    fmt = lambda x: f"{x:.3f}"
    lines = [
        "# Validation du modèle des solides (carte d'inflammabilité BASS / BASS-II)",
        "",
        f"Généré par `python -m src.models.evaluate_solids` le {datetime.date.today().isoformat()}. Ne pas éditer à la main.",
        "",
        f"- Données : {len(obs)} observations « la flamme tient / ne tient pas » tirées de {obs['test_id'].nunique()} essais "
        f"({obs['session'].nunique()} jours d'essai) ; règles d'étiquetage dans `src/models/solids.py`.",
        f"- Variables : {', '.join(FEATURES)}.",
        f"- O2 de {obs['x_o2'].min():.1%} à {obs['x_o2'].max():.1%} ; vitesse d'air de {obs['flow_cm_s'].min():g} à {obs['flow_cm_s'].max():g} cm/s ; pression ~1 atm.",
        f"- Validation croisée **par jour d'essai** ({N_FOLDS} plis) : les observations d'un même essai (et d'un même jour) ne sont jamais séparées.",
        "",
        "## Verdict",
        "",
        f"**Fiabilité faible** : AUC {model_c['auc']:.2f} (0,5 = hasard), exactitude {model_c['accuracy']:.0%} contre "
        f"{majority:.0%} en répondant toujours la classe majoritaire. Les données BASS / BASS-II ne suffisent pas à prédire, "
        "d'un jour d'essai à l'autre, si une flamme tient. Variantes testées avec la même validation (matériau détaillé en "
        "6 classes, débit linéaire, longueur de corrélation libre : AUC 0,50 ; régression logistique avec log(débit)² : "
        "AUC 0,52–0,55) : aucune ne fait mieux. Le modèle retenu sert seulement d'indication ; la recommandation repose "
        "surtout sur la nouveauté (distance aux essais existants).",
        "",
        "## La flamme tient-elle ?",
        "",
        "| | AUC | Brier ↓ | Log loss ↓ | Exactitude (seuil 0,5) |",
        "|---|---:|---:|---:|---:|",
        f"| **Modèle (processus gaussien)** | {fmt(model_c['auc'])} | {fmt(model_c['brier'])} | {fmt(model_c['log_loss'])} | {fmt(model_c['accuracy'])} |",
        f"| Référence : taux par classe de matériau | {fmt(base_c['auc'])} | {fmt(base_c['brier'])} | {fmt(base_c['log_loss'])} | {fmt(base_c['accuracy'])} |",
        f"| Référence : toujours la classe majoritaire | — | — | — | {fmt(majority)} |",
        "",
        "Calibration (hors échantillon) :",
        "",
        "| Probabilité prédite | Observations | Moyenne prédite | Fréquence observée |",
        "|---|---:|---:|---:|",
    ]
    lines += [f"| {bins[b]:.1f}–{bins[b + 1]:.1f} | {int(r.n)} | {r.predite:.2f} | {r.observee:.2f} |" for b, r in calib.iterrows()]
    lines += ["", "Observations par classe de matériau :", "", "| Classe | Observations | Part « tient » |", "|---|---:|---:|"]
    lines += [f"| {c} | {int(by_class.loc[c, 'n'])} | {by_class.loc[c, 'tient']:.2f} |" for c in MATERIAL_CLASSES if c in by_class.index]
    lines += ["", "## Importance des variables (longueurs de corrélation, données normalisées ; petite = influente)", "",
              "| Variable | Longueur |", "|---|---:|"]
    lines += [f"| {f} | {v:.2f} |" for f, v in zip(FEATURES, lengths)]
    lines += [
        "",
        "## Limites",
        "",
        "- **Aucun essai solide au-dessus de 22,7 % d'O2** (BASS) / 22,2 % (observations utilisées) : toute prédiction en atmosphère enrichie est une extrapolation.",
        "- Les vitesses sont celles de l'anémomètre ; quand l'extinction a lieu à un réglage du potentiomètre sous la dernière vitesse affichée, "
        "seuls les points « tient » sont connus (la limite basse réelle est plus basse que la dernière vitesse affichée).",
        "- Peu d'observations « ne tient pas » ; les essais ont été conduits pour chercher les limites, ce n'est pas un échantillon uniforme.",
        "- Pression nominale 1 atm (BASS-II) : le modèle ne dit rien de l'effet de la pression.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
