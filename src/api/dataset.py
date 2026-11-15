"""Étude du jeu de données pour la page « Étude des données » de l'interface (GET /dataset/summary).

Tout est calculé à partir des tables de data/processed (aucune valeur saisie à la main) :
chiffres clés, essais par expérience, issues, oxygène testé, carte O₂ × pression, données manquantes,
campagnes et quelques constats.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
CATALOG = ROOT / "data" / "raw" / "ntrs" / "catalog.csv"

FAMILY_LABELS = {"droplet": "Droplets", "gas": "Gases", "solid": "Solids"}
OUTCOME_LABELS = {"extinguished": "Extinguished", "burned": "Burned", "no_ignition": "No ignition",
                  "disruption": "Droplet disruption", "completion": "Burned to completion", "other": "Other"}
COMPLETENESS = {"o2_percent": "O₂", "pressure_kpa": "Pressure", "flow_cm_s": "Air flow speed", "outcome": "Outcome",
                "burning_rate": "Burning rate", "spread_rate_mm_s": "Flame spread rate"}
O2_BINS = list(range(10, 95, 5))  # 10-15 %, 15-20 %, ..., 85-90 %
SCENARIOS = [{"label": "ISS cabin", "o2": 21, "p": 101.3}, {"label": "Lunar habitat", "o2": 34, "p": 55}]


def _pct(part, total):
    return float(round(100 * part / total, 1)) if total else 0.0


@lru_cache(maxsize=1)
def summary():
    df = pd.read_csv(PROCESSED / "experiments_all.csv")
    campaigns = pd.read_csv(PROCESSED / "campaigns.csv")
    n = len(df)
    with_outcome = df["outcome"].notna()
    families = [f for f in FAMILY_LABELS if f in set(df["fuel_type"])]

    kpis = {
        "tests": n,
        "experiments": int(df["experiment"].nunique()),
        "campaigns": int(len(campaigns)),
        "documents": int(len(pd.read_csv(CATALOG))) if CATALOG.exists() else None,
        "micro_pct": _pct((df["gravity"] == "micro").sum(), n),
        "with_outcome_pct": _pct(with_outcome.sum(), n),
    }

    by_exp = (df.groupby(["experiment", "fuel_type"]).size().reset_index(name="n")
              .sort_values("n", ascending=False))
    by_experiment = [{"experiment": r.experiment, "family": r.fuel_type, "n": int(r.n)} for r in by_exp.itertuples()]

    counts = df["outcome"].value_counts()
    outcomes = [{"outcome": k, "label": OUTCOME_LABELS.get(k, k), "n": int(v)} for k, v in counts.items()]
    outcomes.append({"outcome": None, "label": "Not measured", "n": int((~with_outcome).sum())})

    hist = {}
    for fam in families:
        o2 = df.loc[df["fuel_type"] == fam, "o2_percent"].dropna()
        hist[fam] = np.histogram(o2.clip(upper=O2_BINS[-1] - 0.01), bins=O2_BINS)[0].tolist()

    pts = df.dropna(subset=["o2_percent", "pressure_kpa"])
    coverage = {fam: pts.loc[pts["fuel_type"] == fam, ["o2_percent", "pressure_kpa"]].round(2).values.tolist()
                for fam in families}

    completeness = [{"column": col, "label": label,
                     "pct": {fam: _pct(df.loc[df["fuel_type"] == fam, col].notna().sum(), (df["fuel_type"] == fam).sum())
                             for fam in families}}
                    for col, label in COMPLETENESS.items() if col in df]

    camp = campaigns.sort_values("n_rows", ascending=False)
    campaign_rows = [{"experiment": r.experiment, "family": r.family, "title": r.title, "start": _date(r.start),
                      "end": _date(r.end), "n": int(r.n_rows), "status": r.status} for r in camp.itertuples()]

    return {
        "kpis": kpis,
        "families": {f: FAMILY_LABELS[f] for f in families},
        "family_counts": {f: int((df["fuel_type"] == f).sum()) for f in families},
        "by_experiment": by_experiment,
        "outcomes": outcomes,
        "o2_hist": {"bins": O2_BINS, "series": hist},
        "coverage": coverage,
        "scenarios": SCENARIOS,
        "completeness": completeness,
        "campaigns": campaign_rows,
        "insights": _insights(df),
    }


def _date(value):
    """Dates de campaigns.csv au format MM-JJ-AAAA -> AAAA-MM (ou None)."""
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = pd.to_datetime(value, format="%m-%d-%Y", errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m")


def _insights(df):
    """Constats chiffrés, recalculés à chaque démarrage à partir des données."""
    out = []
    flex = df[(df["experiment"] == "FLEX") & df["pressure_kpa"].notna()]
    if len(flex):
        out.append(f"Droplets: no FLEX test below {flex['pressure_kpa'].min():.0f} kPa, "
                   "so a 55 kPa lunar habitat is outside the measured data.")
    solid = df[(df["fuel_type"] == "solid") & (df["gravity"] == "micro") & df["o2_percent"].notna()]
    if len(solid):
        out.append(f"Solids: at most {solid['o2_percent'].max():.1f}% O₂ in microgravity, "
                   "while planned exploration atmospheres target about 34%.")
    gas = df[(df["fuel_type"] == "gas") & df["o2_percent"].between(30, 40) & (df["pressure_kpa"] <= 70)]
    out.append(f"Gases: {len(gas)} tests close to the lunar scenario (30 to 40% O₂, 70 kPa or less).")
    no_outcome = df[df["outcome"].isna()]
    if len(no_outcome):
        main = ", ".join(no_outcome["experiment"].value_counts().index[:2])
        out.append(f"{_pct(len(no_outcome), len(df)):.0f}% of the tests have no measured flame outcome "
                   f"({main}: soot and flame shape measurements).")
    return out
