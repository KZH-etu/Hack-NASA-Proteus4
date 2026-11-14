"""Famille « Solides (BASS-II, Saffire) » : AUCUN modèle de prédiction (raisons : validation.md).

À la place, recherche des essais NASA réels les plus proches de la demande.

    from src.models.model_rf.solids.model import find_tests
    find_tests({...})
"""
from ..data_only import DataExplorer
from . import FAMILY


def find_tests(params: dict, k: int = 5, tables=None) -> dict:
    return DataExplorer(tables).find_tests(FAMILY, params, k)


def summary(tables=None):
    return DataExplorer(tables).summary(FAMILY)
