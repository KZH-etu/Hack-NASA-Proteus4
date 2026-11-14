"""COMPARAISON ÉQUITABLE DES MODÈLES DE L'ÉQUIPE.

    python -m src.models.model_rf.experiments.compare_models

Tous les modèles passent EXACTEMENT le même examen :
mêmes données, mêmes fiches (entrées/sorties), mêmes sessions mises de côté, mêmes mesures.
Résultats enregistrés dans src/models/model_rf/results/comparaison_modeles.csv (à joindre au README / pitch).

Pour ajouter un modèle : l'importer ci-dessous et l'ajouter à MODELES.
"""
import warnings
from pathlib import Path

import pandas as pd

from ..data_prep import load_tables
from ..metrics import compare
from ..forest import ForestModel
from .modele_exemple import KNNModel

from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
# from ..modele_collegue import ModeleCollegue   # <- décommenter

MODELES = (ForestModel, KNNModel)                          # <- ajouter ModeleCollegue ici

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 80)

res = compare(load_tables(), model_classes=MODELES)
out = RESULTS; out.mkdir(exist_ok=True)
res.to_csv(out / "comparaison_modeles.csv", index=False)

cols = ["famille", "sortie", "modele", "exactitude_modele", "exactitude_reference", "exactitude_equilibree", "equilibree_IC95",
        "detection_par_issue", "ecart_fiabilite", "MAE_modele", "MAE_IC95", "MAE_reference", "couverture_95",
        "bat_la_reference"]
print(res[[c for c in cols if c in res]].round(3).to_string(index=False))

print("\n=== Gagnant par famille et par sortie ===")
print("Règle : d'abord battre la référence ; puis exactitude équilibrée (issues) ou MAE (valeurs) ;")
print("une couverture loin de 95 % est un défaut à signaler même chez le gagnant.\n")
for (fam, sortie), g in res.groupby(["famille", "sortie"], sort=False):
    ok = g[g["bat_la_reference"]]
    if ok.empty:
        print(f"{fam} / {sortie} : aucun modèle ne bat la référence -> afficher les essais réels")
        continue
    if "MAE_modele" in ok and ok["MAE_modele"].notna().any():
        best = ok.loc[ok["MAE_modele"].idxmin()]
        detail = f"MAE {best['MAE_modele']:.3f} (réf. {best['MAE_reference']:.3f}), couverture {best['couverture_95']:.0%}"
    else:
        best = ok.loc[ok["exactitude_equilibree"].idxmax()]
        detail = f"exactitude équilibrée {best['exactitude_equilibree']:.0%}, exactitude {best['exactitude_modele']:.0%}"
    print(f"{fam} / {sortie} : {best['modele']} — {detail}")

print("\nAvant de déclarer un gagnant, vérifier que l'écart est réel (même examen, IC du gain) :")
print("  from ..metrics import paired_gain")
print("  paired_gain(load_tables(), famille, sortie, (ForestModel, False), (ModeleCollegue, False))")
print("  -> verdict « pas de différence démontrée » = garder le plus simple.")
