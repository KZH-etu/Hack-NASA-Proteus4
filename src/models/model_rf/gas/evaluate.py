"""Toutes les mesures de la famille « Gaz (ACME CFI-G) » (sessions mises de côté).

    python -m src.models.model_rf.gas.evaluate
"""
from ..family_tools import print_family_report
from . import FAMILY

if __name__ == "__main__":
    print_family_report(FAMILY)
