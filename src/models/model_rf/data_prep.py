"""Chargement et préparation des données (ne dépend d'aucune famille en particulier)."""
from pathlib import Path

import numpy as np
import pandas as pd

from .families import FAMILIES

def _find_data_dir() -> Path:
    """Remonte depuis ce fichier jusqu'au dossier des tables par famille (data/processed/families, racine du dépôt)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "processed" / "families").is_dir():
            return parent / "data" / "processed" / "families"
    return Path.cwd() / "data" / "processed" / "families"


DATA_DIR = _find_data_dir()
TABLES = ["droplets", "solids", "gas", "aerosols"]


def load_tables(folder: Path | str = DATA_DIR) -> dict:
    """Charge les tables traitées : {"droplets": DataFrame, ...}."""
    folder = Path(folder)
    return {name: pd.read_parquet(folder / f"{name}.parquet")
            for name in TABLES if (folder / f"{name}.parquet").exists()}


def family_rows(tables: dict, family: str) -> pd.DataFrame:
    """Lignes de la famille, microgravité uniquement (règle d'équipe : pas de mélange avec le 1g)."""
    fiche = FAMILIES[family]
    df = tables[fiche["fichier"]]
    mask = df["gravity"] == "micro"
    for col, values in fiche["filtre"].items():
        mask &= df[col].isin(values)
    rows = df[mask].copy()
    if "filtre_extra" in fiche:
        rows = fiche["filtre_extra"](rows)
    return rows


def prepare_xy(tables: dict, family: str, output: str):
    """Retourne X (entrées du modèle), y (sortie), groups (validation) et les lignes d'origine.

    Les lignes sans valeur de sortie sont retirées : on n'invente jamais de résultat.
    Les entrées manquantes sont gérées dans le modèle (valeur typique, pour le calcul seulement).
    """
    fiche = FAMILIES[family]
    target = fiche["sorties"][output]
    rows = family_rows(tables, family).dropna(subset=[target["colonne"]])

    X = model_features(rows, family)
    y = rows[target["colonne"]]
    y = pd.to_numeric(y, errors="coerce").astype(float) if target["type"] == "regression" else y.astype(str)
    groups = rows[fiche["groupe"]].astype(str) if fiche["groupe"] in rows.columns else None
    return X, y, groups, rows


def to_features(rows: pd.DataFrame, entrees: dict) -> pd.DataFrame:
    """Met les colonnes d'entrée au bon format (nombres en float, texte en chaîne)."""
    X = pd.DataFrame(index=rows.index)
    for col, kind in entrees.items():
        values = rows[col] if col in rows.columns else pd.Series(index=rows.index, dtype=object)
        if kind == "nombre":
            X[col] = pd.to_numeric(values, errors="coerce").astype(float)
        else:
            X[col] = values.astype(object).where(values.notna(), "inconnu").astype(str)
    return X


def model_features(rows: pd.DataFrame, family: str) -> pd.DataFrame:
    """Entrées de l'utilisateur + variables physiques calculées (voir « derivees » dans la fiche)."""
    fiche = FAMILIES[family]
    X = to_features(rows, fiche["entrees"])
    for name, formula in fiche.get("derivees", {}).items():
        X[name] = formula(X).astype(float).replace([np.inf, -np.inf], np.nan)
    return X
