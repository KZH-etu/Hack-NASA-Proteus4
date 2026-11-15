"""Prédictions pour l'interface HEPHAISTOS : traduit la requête de la page vers model_gp.

Requête (à plat, comme l'envoie la page) :
    {"fuel_type": "droplet" | "solid" | "gas", "material": ..., "o2_percent": ..., <champs du type>}
Réponse : la sortie de model_gp telle quelle (p_extinction, p_flame_sustained, p_hot_ignition, intervalles,
warnings...) + "sources" : essais NASA réels les plus proches, avec le lien vers leur source.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("hephaistos.predict")
ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = ROOT / "data" / "processed" / "experiments_all.csv"

FAMILIES = ("droplet", "gas", "solid")
# Champs propres à chaque type (en plus de fuel_type, material, o2_percent) et valeurs par défaut
FIELDS = {
    "droplet": {"pressure_kpa": None, "d0_mm": 3.0, "co2_percent": 0.0, "he_percent": 0.0},
    "solid": {"flow_cm_s": None},
    "gas": {"pressure_kpa": None, "x_fuel": None, "hc_rate_mg_s": None},
}
EXPERIMENTS = {"droplet": ("FLEX",), "gas": ("ACME CFI-G",), "solid": ("BASS-II", "BASS", "Saffire-II", "Saffire-I", "Saffire-III")}

_LOCKS = {family: threading.Lock() for family in FAMILIES}
STATUS = {family: {"status": "pending"} for family in FAMILIES}


class PredictionError(ValueError):
    """Requête invalide (champ manquant, valeur non couverte) : renvoyée à la page en 422."""


def _gp():
    from src.models import load
    return load("model_gp")


def _family_module(family):
    gp = _gp()
    return {"droplet": gp.flex, "gas": gp.gas, "solid": gp.solids}[family]


def ensure_loaded(family):
    """Charge le modèle de la famille une seule fois, même si plusieurs requêtes arrivent (rechargé depuis
    data/models/ en ~0,1 s, ou entraîné en ~10 à 20 s si les données ou le code ont changé)."""
    with _LOCKS[family]:
        if STATUS[family]["status"] == "ready":
            return
        STATUS[family] = {"status": "loading"}
        try:
            _family_module(family).trained_model()
            STATUS[family] = {"status": "ready"}
        except Exception as exc:  # noqa: BLE001 - l'erreur est montrée par /models/status
            LOGGER.exception("Chargement du modèle %s impossible", family)
            STATUS[family] = {"status": "error", "error": str(exc)}
            raise


def warm_up():
    """Préchauffe les trois modèles l'un après l'autre (appelé dans un fil au démarrage du serveur)."""
    for family in FAMILIES:
        try:
            ensure_loaded(family)
        except Exception:  # noqa: BLE001 - déjà journalisé
            pass


# ---------- Sources : lien vers la source NASA de chaque essai ----------

@lru_cache(maxsize=1)
def _catalogue():
    df = pd.read_csv(CATALOGUE, dtype={"test_id": str})
    return df.set_index(["experiment", "test_id"])[["psi_id", "psi_url", "doi_url", "material"]]


def _source(family, test, extra):
    """Essai proche au format attendu par la page (renderSource), avec psi_id et lien."""
    cat = _catalogue()
    test_id = str(test.get("test_id"))
    experiment, row = None, None
    for exp in EXPERIMENTS[family]:
        if (exp, test_id) in cat.index:
            experiment, row = exp, cat.loc[(exp, test_id)]
            break
    source = {"experiment": experiment or EXPERIMENTS[family][0], "test_id": test_id, **extra}
    if row is not None:
        source["psi_id"] = row["psi_id"]
        url = row["psi_url"] if isinstance(row["psi_url"], str) else row["doi_url"]
        if isinstance(url, str):
            source["url"] = url
    return {k: v for k, v in source.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}


def _require(conditions, keys):
    missing = [k for k in keys if conditions.get(k) is None]
    if missing:
        raise PredictionError(f"missing field(s): {', '.join(missing)}")


# ---------- Prédiction ----------

def predict(payload: dict[str, Any]) -> dict[str, Any]:
    family = str(payload.get("fuel_type", "")).strip().lower()
    if family not in FAMILIES:
        raise PredictionError("fuel_type must be droplet, gas or solid")
    material = str(payload.get("material", "")).strip().lower()
    c = {"o2_percent": payload.get("o2_percent")}
    for key, default in FIELDS[family].items():
        value = payload.get(key)
        c[key] = default if value is None or value == "" else value
    _require({**c, "material": material or None}, ["material", "o2_percent", *[k for k, d in FIELDS[family].items() if d is None]])
    c = {k: (float(v) if v is not None else None) for k, v in c.items()}

    ensure_loaded(family)
    module = _family_module(family)
    try:
        if family == "droplet":
            result = module.predict({"fuel": material, **c})
            from src.models.model_gp.flex.recommend import nearest_tests
            X = module.conditions_to_row({"fuel": material, **c})[0]
            near = nearest_tests(module.trained_model(), X, X[0], k=3)
            sources = [_source(family, t, {"material": material, "o2_percent": t["o2_percent"],
                                           "pressure_kpa": t["pressure_kpa"], "outcome": t["outcome"]}) for t in near]
        elif family == "solid":
            result = module.predict({"material": material, **c})
            from src.models.model_gp.solids.model import nearest_tests
            near = nearest_tests(module.trained_model(), material, c["o2_percent"] / 100, c["flow_cm_s"], k=3)
            sources = [_source(family, t, {"material": t["material_class"], "o2_percent": t["o2_percent"],
                                           "flow_cm_s": t["flow_cm_s"],
                                           "outcome": "flame sustained" if t["flame_sustained"] else "flame not sustained"})
                       for t in near]
        else:
            result = module.predict({"fuel": material, **c})
            sources = [_source(family, t, {"material": t["fuel"], "o2_percent": t["o2_percent"],
                                           "pressure_kpa": t["pressure_kpa"], "outcome": t["outcome"]})
                       for t in result.pop("nearest_tests", [])]
    except ValueError as exc:  # combustible ou matériau non couvert par le modèle
        raise PredictionError(str(exc)) from exc
    result["sources"] = sources
    return _jsonable(result)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj
