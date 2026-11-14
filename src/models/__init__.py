"""Registre des modèles : chaque dossier src/models/model_<nom>/ est un modèle complet (voir README.md).

    from src.models import available_models, load
    available_models()          # ['model_gp', ...]
    m = load("model_gp")        # m.FAMILIES, m.recommend_next_experiment(...)
    m.FAMILIES["droplets"].predict({...})
"""

import importlib
from pathlib import Path

DEFAULT_MODEL = "model_gp"


def available_models():
    """Noms des dossiers de modèles présents (model_<nom>/ avec un __init__.py)."""
    here = Path(__file__).parent
    return sorted(p.name for p in here.iterdir() if p.is_dir() and p.name.startswith("model_") and (p / "__init__.py").exists())


def load(name=DEFAULT_MODEL):
    """Importe un modèle par son nom de dossier (ex. 'model_gp')."""
    if name not in available_models():
        raise ValueError(f"modèle inconnu « {name} » ; disponibles : {available_models()}")
    return importlib.import_module(f"src.models.{name}")
