"""Modèles de la famille « Gouttelettes (FLEX) ».

La fiche (entrées, sorties, filtres) est dans src/models/model_rf/families.py ;
le choix du modèle (forêt pondérée ou forêt + SMOTE) dans MODEL_OVERRIDES du même fichier.

    from src.models.model_rf.flex.model import build
    modeles = build()              # {sortie: modèle entraîné}
"""
from ..family_tools import build_models
from . import FAMILY


def build(tables=None) -> dict:
    return build_models(FAMILY, tables)
