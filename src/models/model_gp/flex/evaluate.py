"""Validation du modèle FLEX : validation croisée par jour d'essai (les essais d'un même jour ne sont jamais
à la fois en entraînement et en test), comparée à des références naïves. Écrit src/models/model_gp/flex/validation.md.

Usage :
    python -m src.models.model_gp.flex.evaluate
"""

import datetime
from pathlib import Path

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold

from src.models.model_gp.flex.model import FEATURES, FlexModel, features, load_data
from src.models.model_gp.metrics import classification_metrics, detailed_report_lines

REPORT = Path(__file__).resolve().parent / "validation.md"
N_FOLDS = 5


def cross_validate(df):
    """Prédictions hors échantillon pour chaque essai (5 plis, regroupés par jour d'essai)."""
    out = df.copy()
    for col in ("p_extinction", "k_pred", "k_std", "base_p", "base_k"):
        out[col] = np.nan
    for train_idx, test_idx in GroupKFold(n_splits=N_FOLDS).split(df, groups=df["session"]):
        train, test = df.iloc[train_idx], df.iloc[test_idx]
        model = FlexModel(train, n_bootstrap=0)
        pred = model.predict_frame(features(test))
        out.loc[test.index, "p_extinction"] = pred["p_extinction"].to_numpy()
        out.loc[test.index, "k_pred"] = pred["k_mm2_s"].to_numpy()
        out.loc[test.index, "k_std"] = pred["k_std"].to_numpy()
        # Références naïves : taux d'extinction et K moyen du combustible dans le pli d'entraînement
        for fuel, flag in (("heptane", 1.0), ("methanol", 0.0)):
            rows = test.index[test["is_heptane"] == flag]
            same = train[train["is_heptane"] == flag]
            out.loc[rows, "base_p"] = same["extinguished"].mean()
            out.loc[rows, "base_k"] = same["burning_rate_mm2_s"].mean()
    return out


def main():
    df = load_data()
    cv = cross_validate(df)
    y = cv["extinguished"].to_numpy()

    model_c = classification_metrics(y, cv["p_extinction"].to_numpy())
    base_c = classification_metrics(y, cv["base_p"].to_numpy())
    majority = float(max(y.mean(), 1 - y.mean()))
    by_fuel = {fuel: classification_metrics(cv.loc[cv["is_heptane"] == flag, "extinguished"].to_numpy(),
                                            cv.loc[cv["is_heptane"] == flag, "p_extinction"].to_numpy())
               for fuel, flag in (("heptane", 1.0), ("methanol", 0.0))}

    # Calibration : probabilité prédite contre fréquence observée
    bins = np.linspace(0, 1, 6)
    cv["bin"] = np.clip(np.digitize(cv["p_extinction"], bins) - 1, 0, 4)
    calib = cv.groupby("bin").agg(n=("extinguished", "size"), predite=("p_extinction", "mean"), observee=("extinguished", "mean"))

    k = cv.dropna(subset=["burning_rate_mm2_s"])
    yk, mk, sk = k["burning_rate_mm2_s"].to_numpy(), k["k_pred"].to_numpy(), k["k_std"].to_numpy()
    k_metrics = {
        "n": int(len(k)),
        "r2": r2_score(yk, mk), "mae": mean_absolute_error(yk, mk),
        "r2_base": r2_score(yk, k["base_k"]), "mae_base": mean_absolute_error(yk, k["base_k"]),
        "coverage_90": float((np.abs(yk - mk) <= 1.645 * sk).mean()),
        "coverage_68": float((np.abs(yk - mk) <= 1.0 * sk).mean()),
        "coverage_95": float((np.abs(yk - mk) <= 1.96 * sk).mean()),
        "rmse": float(mean_squared_error(yk, mk) ** 0.5), "rmse_base": float(mean_squared_error(yk, k["base_k"]) ** 0.5),
        "mean_std": float(sk.mean()),
    }

    full = FlexModel(df, n_bootstrap=0)
    lengths = full.classifier[-1].kernel_.k2.length_scale
    lengths_k = full.regressor[-1].kernel_.k1.k2.length_scale

    fmt = lambda x: f"{x:.3f}"
    lines = [
        "# Validation du modèle FLEX",
        "",
        f"Généré par `python -m src.models.model_gp.flex.evaluate` le {datetime.date.today().isoformat()}. Ne pas éditer à la main.",
        "",
        f"- Données : {len(df)} essais FLEX utilisables (toutes les variables présentes) sur {df['session'].nunique()} jours d'essai ; "
        f"variables : {', '.join(FEATURES)}.",
        f"- Validation croisée **par jour d'essai** ({N_FOLDS} plis, `GroupKFold` sur `session`) : un jour n'est jamais à la fois en entraînement et en test.",
        "- Références naïves : taux d'extinction (ou K moyen) du même combustible dans les données d'entraînement ; classe majoritaire.",
        "",
        "## Extinction (la flamme s'éteint avant la fin de la combustion)",
        "",
        "| | AUC | Brier ↓ | Log loss ↓ | Exactitude (seuil 0,5) |",
        "|---|---:|---:|---:|---:|",
        f"| **Modèle (processus gaussien)** | {fmt(model_c['auc'])} | {fmt(model_c['brier'])} | {fmt(model_c['log_loss'])} | {fmt(model_c['accuracy'])} |",
        f"| Référence : taux par combustible | {fmt(base_c['auc'])} | {fmt(base_c['brier'])} | {fmt(base_c['log_loss'])} | {fmt(base_c['accuracy'])} |",
        f"| Référence : toujours la classe majoritaire | — | — | — | {fmt(majority)} |",
        "",
        "Par combustible (modèle) :",
        "",
        "| Combustible | Essais | AUC | Brier | Exactitude |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [f"| {fuel} | {m['n']} | {fmt(m['auc'])} | {fmt(m['brier'])} | {fmt(m['accuracy'])} |" for fuel, m in by_fuel.items()]
    lines += ["", "Calibration (hors échantillon) :", "", "| Probabilité prédite | Essais | Moyenne prédite | Fréquence observée |", "|---|---:|---:|---:|"]
    lines += [f"| {bins[b]:.1f}–{bins[b + 1]:.1f} | {int(r.n)} | {r.predite:.2f} | {r.observee:.2f} |" for b, r in calib.iterrows()]
    lines += [""] + detailed_report_lines(y, cv["p_extinction"].to_numpy(), cv["base_p"].to_numpy(), "extinction", "la flamme tient")
    lines += [
        "## Constante de combustion K (mm²/s)",
        "",
        "| | R² | Erreur absolue moyenne | RMSE |",
        "|---|---:|---:|---:|",
        f"| **Modèle (processus gaussien)** | {fmt(k_metrics['r2'])} | {fmt(k_metrics['mae'])} | {fmt(k_metrics['rmse'])} |",
        f"| Référence : K moyen par combustible | {fmt(k_metrics['r2_base'])} | {fmt(k_metrics['mae_base'])} | {fmt(k_metrics['rmse_base'])} |",
        "",
        f"Intervalle à 90 % (± 1,645 écart-type) : la vraie valeur est dedans dans **{k_metrics['coverage_90']:.0%}** des cas "
        f"(attendu : 90 %) ; écart-type moyen {k_metrics['mean_std']:.3f} mm²/s ; {k_metrics['n']} essais avec K.",
        "",
        "| Intervalle | Part des essais dedans | Attendu |",
        "|---|---:|---:|",
        f"| ± 1 écart-type (68 %) | {k_metrics['coverage_68']:.1%} | 68 % |",
        f"| ± 1,645 écart-type (90 %) | {k_metrics['coverage_90']:.1%} | 90 % |",
        f"| ± 1,96 écart-type (95 %) | {k_metrics['coverage_95']:.1%} | 95 % |",
        "",
        "## Importance des variables (longueurs de corrélation du noyau, données normalisées ; petite = influente)",
        "",
        "| Variable | Extinction | K |",
        "|---|---:|---:|",
    ]
    lines += [f"| {f} | {a:.2f} | {b:.2f} |" for f, a, b in zip(FEATURES, lengths, lengths_k)]
    lines += [
        "",
        "## Limites",
        "",
        "- Les essais FLEX ont été choisis pour encadrer les limites d'extinction : ce n'est pas un échantillon uniforme des conditions possibles.",
        "- Heptane et méthanol seulement ; pression de 70 à 309 kPa (aucun essai sous 0,69 atm) ; O2 de 12 à 34 %.",
        "- Une prédiction hors de ces plages est une extrapolation : `predict()` le signale, ainsi que l'absence d'essai proche.",
        "- La pression n'a presque aucun effet appris sur l'extinction (longueur de corrélation à la borne) : sous 70 kPa, "
        "l'intervalle d'incertitude est sous-estimé ; c'est précisément la zone de l'atmosphère d'exploration (≈ 55 kPa).",
        "- La zone de probabilité 0,4–0,6 est un peu surestimée (voir calibration).",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
